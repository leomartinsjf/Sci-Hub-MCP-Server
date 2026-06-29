from __future__ import annotations

import functools
import logging
import os
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import urllib3

from oa_resolver import OpenAccessResult, resolve_open_access

LOGGER = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CROSSREF_API_URL = "https://api.crossref.org/works"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15
SCIHUB_RETRY_TIMES = 3
SCIHUB_MIRRORS = ("sci-hub.ru",)
SCIHUB_MIRRORS_ENV = "SCIHUB_MCP_SCIHUB_MIRRORS"
SCIHUB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:149.0) Gecko/20100101 Firefox/149.0"
}
MAX_KEYWORD_RESULTS = 20
DEFAULT_DOWNLOAD_DIR = "downloads"
DOWNLOAD_DIR_ENV = "SCIHUB_MCP_DOWNLOAD_DIR"
MAX_DOWNLOAD_BYTES_ENV = "SCIHUB_MCP_MAX_DOWNLOAD_BYTES"
DEFAULT_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
ENABLE_SCIHUB_FALLBACK_ENV = "SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK"
_FALSEY_VALUES = {"0", "false", "no", "off", ""}


def _configured_scihub_mirrors() -> tuple[str, ...]:
    configured_value = os.getenv(SCIHUB_MIRRORS_ENV, "")
    if not configured_value.strip():
        return SCIHUB_MIRRORS

    mirrors = []
    for raw_mirror in configured_value.split(","):
        mirror = _normalize_scihub_mirror(raw_mirror)
        if mirror:
            mirrors.append(mirror)

    unique_mirrors = tuple(dict.fromkeys(mirrors))
    return unique_mirrors or SCIHUB_MIRRORS


def _normalize_scihub_mirror(raw_mirror: str) -> str:
    value = raw_mirror.strip().strip("/")
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else f"https://{value}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.netloc


class _SciHubPdfSourceParser(HTMLParser):
    """Extract PDF source and citation metadata from a Sci-Hub response page."""

    def __init__(self) -> None:
        super().__init__()
        self.citation_pdf_url: str | None = None
        self.container_source: str | None = None
        self.link_source: str | None = None
        self.metadata: dict[str, str] = {}
        self.authors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = {name.lower(): value.strip() for name, value in attrs if value}

        if normalized_tag == "meta":
            self._handle_meta_tag(attr_map)
            return

        if normalized_tag in {"iframe", "object", "embed"} and not self.container_source:
            self.container_source = attr_map.get("src") or attr_map.get("data")
            return

        if normalized_tag == "a" and not self.link_source:
            href = attr_map.get("href", "")
            if ".pdf" in href.lower():
                self.link_source = href

    @property
    def source(self) -> str | None:
        return self.citation_pdf_url or self.container_source or self.link_source

    def normalized_metadata(self) -> dict[str, str]:
        metadata = self.metadata.copy()
        if self.authors:
            metadata["author"] = ", ".join(dict.fromkeys(self.authors))
        if metadata.get("publication_date") and not metadata.get("year"):
            metadata["year"] = _year_from_publication_date(metadata["publication_date"])
        return metadata

    def _handle_meta_tag(self, attr_map: dict[str, str]) -> None:
        name = (attr_map.get("name") or attr_map.get("property") or "").lower()
        content = attr_map.get("content", "")
        if not name or not content:
            return

        if name == "citation_pdf_url" and not self.citation_pdf_url:
            self.citation_pdf_url = content
        elif name == "citation_doi":
            self.metadata.setdefault("doi", content)
        elif name == "citation_title":
            self.metadata.setdefault("title", content)
        elif name == "citation_author":
            self.authors.append(content)
        elif name == "citation_publication_date":
            self.metadata.setdefault("publication_date", content)
        elif name == "citation_year":
            self.metadata.setdefault("year", content)


@dataclass(frozen=True)
class SciHubOpenAccessResult(OpenAccessResult):
    """OpenAccessResult with optional metadata scraped from a Sci-Hub response."""

    metadata: dict[str, str] = field(default_factory=dict)


class SciHub:
    """Minimal Sci-Hub client used only as the gated last-resort fallback."""

    def __init__(self, mirrors: tuple[str, ...] | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update(SCIHUB_HEADERS)
        self.urls = mirrors or _configured_scihub_mirrors()
        self.current_idx = 0
        self.tries = 0

    @property
    def base_url(self) -> str:
        return f"https://{self.urls[self.current_idx].strip('/')}/"

    def fetch(self, identifier: str, retries: int = SCIHUB_RETRY_TIMES) -> dict[str, Any]:
        normalized_identifier = identifier.strip()
        if not normalized_identifier:
            raise ValueError("identifier is required")

        for _attempt in range(retries):
            self.tries += 1
            LOGGER.info("%s Downloading with %s", self.tries, self.base_url)

            try:
                lookup = self._get_direct_url(normalized_identifier)
                if lookup is None:
                    self._next_url()
                    continue

                pdf_url, metadata = lookup
                LOGGER.info("direct_url = %s", pdf_url)
                response = self.session.get(pdf_url, verify=False)
                if not self._is_pdf_response(response):
                    LOGGER.error("Sci-Hub response did not contain a PDF")
                    self._next_url()
                    continue

                return {"pdf": response.content, "url": pdf_url, "metadata": metadata}
            except requests.exceptions.ConnectionError:
                LOGGER.exception("%s cannot access, changing", self.urls[self.current_idx])
                self._next_url()
            except requests.exceptions.RequestException as exc:
                return {"err": f"Failed to fetch {normalized_identifier}: {exc}"}

        raise RuntimeError(f"Failed after {retries} retries")

    def _next_url(self) -> None:
        self.current_idx += 1
        if self.current_idx >= len(self.urls):
            raise RuntimeError("No more Sci-Hub mirrors available")

    def _get_direct_url(self, identifier: str) -> tuple[str, dict[str, str]] | None:
        if self._classify(identifier) == "url-direct":
            return identifier, {}
        return self._search_direct_url(identifier)

    def _search_direct_url(self, identifier: str) -> tuple[str, dict[str, str]] | None:
        LOGGER.debug("Pinging %s", self.base_url)
        try:
            ping = self.session.get(self.base_url, verify=False)
            if ping.status_code != requests.codes.ok:
                LOGGER.error("Server %s is down", self.base_url)
                return None
        except requests.exceptions.RequestException:
            LOGGER.exception("Server %s is down", self.base_url)
            return None

        lookup_url = f"{self.base_url}{identifier}"
        LOGGER.info("scihub url %s", lookup_url)
        response = self.session.get(lookup_url, verify=False)

        LOGGER.debug("Scraping scihub site")
        parser = _SciHubPdfSourceParser()
        parser.feed(response.text)
        if not parser.source:
            return None

        return self._normalize_source_url(parser.source), parser.normalized_metadata()

    def _normalize_source_url(self, source: str) -> str:
        if source.startswith("//"):
            return f"https:{source}"
        if source.startswith("/"):
            return f"https://{self.urls[self.current_idx].strip('/')}{source}"
        return source if urlparse(source).scheme else urljoin(self.base_url, source)

    def _classify(self, identifier: str) -> str:
        parsed = urlparse(identifier)
        if parsed.scheme in {"http", "https"}:
            return "url-direct" if parsed.path.lower().endswith(".pdf") else "url-non-direct"
        if identifier.isdigit():
            return "pmid"
        return "doi"

    def _is_pdf_response(self, response: requests.Response) -> bool:
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type in {
            "application/pdf",
            "application/octet-stream",
        }:
            return True
        return response.content.startswith(b"%PDF-")


def create_scihub_instance() -> SciHub:
    """Create a SciHub client instance with a request timeout.

    A hung mirror would block the worker thread and risk the whole MCP server
    indefinitely. Inject a default timeout on the session so the last-resort
    fallback fails fast.
    """
    sci_hub = SciHub()
    session = getattr(sci_hub, "session", None)
    if session is not None:
        _apply_default_timeout(session, DEFAULT_REQUEST_TIMEOUT_SECONDS)
    return sci_hub


def _apply_default_timeout(session: Any, timeout: int) -> None:
    """Make ``session.request`` default to ``timeout`` when none is supplied."""
    original_request = session.request

    @functools.wraps(original_request)
    def request_with_timeout(method: str, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", timeout)
        return original_request(method, url, **kwargs)

    session.request = request_with_timeout


def scihub_fallback_enabled() -> bool:
    """Whether the Sci-Hub last-resort fallback is enabled (default: enabled)."""
    return os.getenv(ENABLE_SCIHUB_FALLBACK_ENV, "1").strip().lower() not in _FALSEY_VALUES


def _resolve_via_scihub(doi: str) -> OpenAccessResult | None:
    """Last-resort Sci-Hub lookup, used only when no open-access copy is found."""
    sci_hub = create_scihub_instance()
    try:
        result = sci_hub.fetch(doi)
    except Exception:
        LOGGER.exception("Sci-Hub fallback failed")
        return None

    pdf_url = result.get("url") if isinstance(result, dict) else None
    if not pdf_url:
        return None

    metadata = result.get("metadata") if isinstance(result, dict) else None
    return SciHubOpenAccessResult(
        source="scihub",
        pdf_url=pdf_url,
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def search_paper_by_doi(doi: str, *, allow_scihub_fallback: bool = True) -> dict[str, Any]:
    """Resolve a DOI to a full-text URL, preferring legal open-access sources.

    The open-access provider chain (see ``oa_resolver``) runs first. Sci-Hub is
    consulted only as a last resort: when no open-access copy is found and the
    fallback is both requested by the caller and enabled through
    ``SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK`` (enabled by default).
    """
    normalized_doi = doi.strip()
    if not normalized_doi:
        return {"doi": doi, "status": "not_found", "error": "DOI is required"}

    metadata = get_crossref_metadata_by_doi(normalized_doi)

    resolution = resolve_open_access(normalized_doi)
    if resolution is None and allow_scihub_fallback and scihub_fallback_enabled():
        resolution = _resolve_via_scihub(normalized_doi)

    fallback_metadata = getattr(resolution, "metadata", {}) if resolution is not None else {}
    if isinstance(fallback_metadata, dict):
        metadata = _merge_metadata(metadata, fallback_metadata)

    if resolution is None:
        return {
            "doi": normalized_doi,
            "status": "not_found",
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "year": metadata.get("year", ""),
        }

    return {
        "doi": normalized_doi,
        "pdf_url": resolution.best_url,
        "landing_url": resolution.landing_url,
        "status": "success",
        "source": resolution.source,
        "oa_status": resolution.oa_status,
        "license": resolution.license,
        "is_open_access": resolution.source != "scihub",
        "title": metadata.get("title", ""),
        "author": metadata.get("author", ""),
        "year": metadata.get("year", ""),
    }


def search_paper_by_title(title: str) -> dict[str, Any]:
    """Find the best CrossRef DOI match for a title, then resolve it on Sci-Hub."""
    normalized_title = title.strip()
    if not normalized_title:
        return {"title": title, "status": "not_found", "error": "Title is required"}

    item = _get_first_crossref_item({"query.title": normalized_title, "rows": 1})
    if not item:
        return {"title": normalized_title, "status": "not_found"}

    doi = item.get("DOI")
    if not doi:
        return {"title": normalized_title, "status": "not_found"}

    metadata = _metadata_from_crossref_item(item)
    result = search_paper_by_doi(doi)
    return _merge_metadata(result, metadata)


def search_papers_by_keyword(keyword: str, num_results: int = 10) -> list[dict[str, Any]]:
    """Search CrossRef by keyword and return papers with an open-access copy.

    Bulk keyword resolution runs open-access providers only; the Sci-Hub
    fallback is intentionally disabled here to avoid automated bulk scraping.
    """
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        return []

    rows = _normalize_result_count(num_results)
    data = _request_crossref({"query": normalized_keyword, "rows": rows})
    items = data.get("message", {}).get("items", [])

    papers: list[dict[str, Any]] = []
    for item in items:
        doi = item.get("DOI")
        if not doi:
            continue

        result = search_paper_by_doi(doi, allow_scihub_fallback=False)
        if result.get("status") == "success":
            papers.append(_merge_metadata(result, _metadata_from_crossref_item(item)))

    return papers


def get_crossref_metadata_by_doi(doi: str) -> dict[str, Any]:
    """Get paper metadata from CrossRef without requiring Sci-Hub availability."""
    normalized_doi = doi.strip()
    if not normalized_doi:
        return {}

    data = _request_crossref({"filter": f"doi:{normalized_doi}", "rows": 1})
    items = data.get("message", {}).get("items", [])
    if not items:
        return {}

    return _metadata_from_crossref_item(items[0])


def download_paper(pdf_url: str, output_path: str) -> bool:
    """Download a PDF URL into the configured download directory."""
    url = _validate_pdf_url(pdf_url)
    target_path = _resolve_output_path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    bytes_written = 0
    max_download_bytes = _max_download_bytes()

    try:
        with requests.get(url, stream=True, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if content_type and content_type not in {"application/pdf", "application/octet-stream"}:
                raise ValueError(f"URL did not return a PDF: {content_type}")

            with temp_path.open("wb") as output_file:
                saw_content = False
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue

                    if not saw_content:
                        saw_content = True
                        if not chunk.startswith(b"%PDF-"):
                            raise ValueError("Downloaded content is not a PDF")

                    bytes_written += len(chunk)
                    if bytes_written > max_download_bytes:
                        raise ValueError("PDF exceeds maximum allowed download size")

                    output_file.write(chunk)

        if bytes_written == 0:
            raise ValueError("Downloaded PDF is empty")

        temp_path.replace(target_path)
        return True
    except Exception:
        temp_path.unlink(missing_ok=True)
        LOGGER.exception("PDF download failed")
        raise


def _request_crossref(params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(
            CROSSREF_API_URL,
            params=params,
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": "Sci-Hub-MCP-Server/0.1"},
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        LOGGER.exception("CrossRef request failed")
        return {}


def _get_first_crossref_item(params: dict[str, Any]) -> dict[str, Any] | None:
    data = _request_crossref(params)
    items = data.get("message", {}).get("items", [])
    if not items:
        return None
    return items[0]


def _metadata_from_crossref_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "doi": item.get("DOI", ""),
        "title": _first_value(item.get("title")),
        "author": _format_authors(item.get("author", [])),
        "year": _extract_year(item),
    }


def _merge_metadata(result: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    merged = result.copy()
    for key in ("doi", "title", "author", "year"):
        if not merged.get(key) and metadata.get(key):
            merged[key] = metadata[key]
    return merged


def _first_value(values: Any) -> str:
    if isinstance(values, list) and values:
        return str(values[0])
    if isinstance(values, str):
        return values
    return ""


def _format_authors(authors: Any) -> str:
    if not isinstance(authors, list):
        return ""

    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        given = author.get("given", "")
        family = author.get("family", "")
        name = " ".join(part for part in (given, family) if part).strip()
        if name:
            names.append(name)

    return ", ".join(names)


def _extract_year(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        date_parts = item.get(key, {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def _year_from_publication_date(publication_date: str) -> str:
    normalized_date = publication_date.strip()
    year = normalized_date[:4]
    return year if year.isdigit() else ""


def _normalize_result_count(num_results: int) -> int:
    try:
        requested_count = int(num_results)
    except (TypeError, ValueError):
        requested_count = 10

    return max(1, min(requested_count, MAX_KEYWORD_RESULTS))


def _validate_pdf_url(pdf_url: str) -> str:
    url = pdf_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("pdf_url must be an HTTP or HTTPS URL")
    return url


def _resolve_output_path(output_path: str) -> Path:
    if not output_path.strip():
        raise ValueError("output_path is required")

    download_dir = _download_dir()
    raw_path = Path(output_path).expanduser()
    target_path = raw_path if raw_path.is_absolute() else download_dir / raw_path
    target_path = target_path.resolve()

    try:
        target_path.relative_to(download_dir)
    except ValueError as exc:
        raise ValueError(f"output_path must be inside {download_dir}") from exc

    if target_path.suffix.lower() != ".pdf":
        raise ValueError("output_path must end with .pdf")

    return target_path


def _download_dir() -> Path:
    return Path(os.getenv(DOWNLOAD_DIR_ENV, DEFAULT_DOWNLOAD_DIR)).expanduser().resolve()


def _max_download_bytes() -> int:
    configured_value = os.getenv(MAX_DOWNLOAD_BYTES_ENV)
    if not configured_value:
        return DEFAULT_MAX_DOWNLOAD_BYTES

    try:
        max_bytes = int(configured_value)
    except ValueError as exc:
        raise ValueError(f"{MAX_DOWNLOAD_BYTES_ENV} must be an integer") from exc

    if max_bytes <= 0:
        raise ValueError(f"{MAX_DOWNLOAD_BYTES_ENV} must be positive")

    return max_bytes


if __name__ == "__main__":
    print(search_paper_by_doi("10.1038/nature09492"))
