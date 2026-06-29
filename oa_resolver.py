"""Open-access full-text resolver.

Resolves a DOI to a legally accessible full-text/PDF URL by walking an ordered
chain of public open-access providers. Each provider is independent and fails
soft: a network error, missing field, or empty result simply advances the chain.

This module intentionally knows nothing about Sci-Hub. The MCP server keeps
Sci-Hub strictly as a last-resort fallback that runs only when every provider
here returns nothing (see ``sci_hub_search.search_paper_by_doi``).

Configuration (environment variables):
    SCIHUB_MCP_CONTACT_EMAIL  Contact email used for Unpaywall (required by its
                              terms) and for the OpenAlex/Crossref polite pool.
                              ``UNPAYWALL_EMAIL`` is accepted as a fallback name.
    SCIHUB_MCP_OA_PROVIDERS   Comma-separated provider order/subset override,
                              e.g. "unpaywall,openalex". Unknown names are
                              ignored. Defaults to DEFAULT_PROVIDER_ORDER.
    CORE_API_KEY              Enables the CORE provider when set.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15
USER_AGENT = "Sci-Hub-MCP-Server/0.2 (open-access-resolver)"

CONTACT_EMAIL_ENV = "SCIHUB_MCP_CONTACT_EMAIL"
LEGACY_EMAIL_ENV = "UNPAYWALL_EMAIL"
PROVIDER_ORDER_ENV = "SCIHUB_MCP_OA_PROVIDERS"
CORE_API_KEY_ENV = "CORE_API_KEY"

UNPAYWALL_API_URL = "https://api.unpaywall.org/v2"
OPENALEX_API_URL = "https://api.openalex.org/works"
EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DOAJ_API_URL = "https://doaj.org/api/search/articles"
CORE_API_URL = "https://api.core.ac.uk/v3/discover"

ARXIV_DOI_PREFIX = "10.48550/arxiv."
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"

# Order matters: arXiv is a zero-network shortcut; the OA aggregators
# (Unpaywall, OpenAlex) come next because they explicitly classify OA status and
# license; repository-level providers follow. Crossref is deliberately absent:
# its text-mining links are often paywalled and are not reliable OA signals.
DEFAULT_PROVIDER_ORDER = ("arxiv", "unpaywall", "openalex", "europepmc", "doaj", "core")

_OPEN_AVAILABILITY = {"open access", "free"}


@dataclass(frozen=True)
class OpenAccessResult:
    """A resolved, legally accessible location for a paper."""

    source: str
    pdf_url: str | None = None
    landing_url: str | None = None
    oa_status: str = ""
    license: str = ""
    version: str = ""

    @property
    def best_url(self) -> str | None:
        """Prefer a direct PDF, otherwise the landing page."""
        return self.pdf_url or self.landing_url


def resolve_open_access(doi: str) -> OpenAccessResult | None:
    """Resolve ``doi`` to an open-access location, or None if none is found.

    Providers run in the configured order and the first hit wins.
    """
    normalized_doi = (doi or "").strip()
    if not normalized_doi:
        return None

    context = {"email": _contact_email()}
    for provider_name in _provider_order():
        provider = _PROVIDERS.get(provider_name)
        if provider is None:
            continue
        try:
            result = provider(normalized_doi, context)
        except Exception:
            LOGGER.debug("OA provider %s raised for %s", provider_name, doi, exc_info=True)
            continue
        if result is not None and result.best_url:
            LOGGER.info("Resolved %s via %s", normalized_doi, provider_name)
            return result
    return None


def _resolve_arxiv(doi: str, _context: dict[str, Any]) -> OpenAccessResult | None:
    """Map an arXiv-minted DOI (10.48550/arXiv.*) straight to its PDF."""
    lowered = doi.lower()
    if not lowered.startswith(ARXIV_DOI_PREFIX):
        return None
    arxiv_id = doi[len(ARXIV_DOI_PREFIX):].strip()
    if not arxiv_id:
        return None
    return OpenAccessResult(
        source="arxiv",
        pdf_url=ARXIV_PDF_URL.format(arxiv_id=arxiv_id),
        landing_url=f"https://arxiv.org/abs/{arxiv_id}",
        oa_status="green",
    )


def _resolve_unpaywall(doi: str, context: dict[str, Any]) -> OpenAccessResult | None:
    """Unpaywall: the authoritative OA aggregator. Requires a contact email."""
    email = context.get("email")
    if not email:
        LOGGER.info("Unpaywall skipped: set %s to enable it", CONTACT_EMAIL_ENV)
        return None

    data = _get_json(f"{UNPAYWALL_API_URL}/{doi}", params={"email": email})
    if not data or not data.get("is_oa"):
        return None

    location = _as_dict(data.get("best_oa_location"))
    pdf_url = _clean_url(location.get("url_for_pdf"))
    landing_url = _clean_url(location.get("url_for_landing_page") or location.get("url"))
    if not pdf_url and not landing_url:
        return None

    return OpenAccessResult(
        source="unpaywall",
        pdf_url=pdf_url,
        landing_url=landing_url,
        oa_status=data.get("oa_status") or "",
        license=location.get("license") or "",
        version=location.get("version") or "",
    )


def _resolve_openalex(doi: str, context: dict[str, Any]) -> OpenAccessResult | None:
    """OpenAlex: a second OA aggregator that catches Unpaywall misses."""
    params = {}
    if context.get("email"):
        params["mailto"] = context["email"]

    data = _get_json(f"{OPENALEX_API_URL}/doi:{doi}", params=params)
    if not data:
        return None

    open_access = _as_dict(data.get("open_access"))
    if not open_access.get("is_oa"):
        return None

    best_location = _as_dict(data.get("best_oa_location"))
    primary_location = _as_dict(data.get("primary_location"))
    pdf_url = _clean_url(best_location.get("pdf_url") or primary_location.get("pdf_url"))
    landing_url = _clean_url(best_location.get("landing_page_url") or open_access.get("oa_url"))
    if not pdf_url and not landing_url:
        return None

    return OpenAccessResult(
        source="openalex",
        pdf_url=pdf_url,
        landing_url=landing_url,
        oa_status=open_access.get("oa_status") or "",
        license=best_location.get("license") or "",
        version=best_location.get("version") or "",
    )


def _resolve_europepmc(doi: str, _context: dict[str, Any]) -> OpenAccessResult | None:
    """Europe PMC: strong for biomedical full text and PMC open-access renders."""
    params = {
        "query": f'DOI:"{doi}"',
        "resultType": "core",
        "format": "json",
        "pageSize": 1,
    }
    data = _get_json(EUROPEPMC_SEARCH_URL, params=params)
    results = ((data or {}).get("resultList") or {}).get("result") or []
    if not results:
        return None

    record = _as_dict(results[0])
    pdf_url: str | None = None
    landing_url: str | None = None
    full_text_urls = _as_dict(record.get("fullTextUrlList")).get("fullTextUrl") or []
    for entry in full_text_urls:
        if not isinstance(entry, dict):
            continue
        if (entry.get("availability") or "").lower() not in _OPEN_AVAILABILITY:
            continue
        url = _clean_url(entry.get("url"))
        if not url:
            continue
        if (entry.get("documentStyle") or "").lower() == "pdf" and not pdf_url:
            pdf_url = url
        elif not landing_url:
            landing_url = url

    pmcid = record.get("pmcid")
    if not pdf_url and pmcid and record.get("isOpenAccess") == "Y":
        pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"

    if not pdf_url and not landing_url:
        return None

    return OpenAccessResult(
        source="europepmc",
        pdf_url=pdf_url,
        landing_url=landing_url,
        oa_status="green" if pmcid else "",
        license=record.get("license") or "",
    )


def _resolve_doaj(doi: str, _context: dict[str, Any]) -> OpenAccessResult | None:
    """DOAJ: full text from vetted fully open-access journals (always gold OA)."""
    data = _get_json(f"{DOAJ_API_URL}/{quote(f'doi:{doi}')}")
    results = (data or {}).get("results") or []
    if not results:
        return None

    bibjson = _as_dict(results[0].get("bibjson"))
    for link in bibjson.get("link") or []:
        if not isinstance(link, dict):
            continue
        if (link.get("type") or "").lower() != "fulltext":
            continue
        url = _clean_url(link.get("url"))
        if not url:
            continue
        is_pdf = (link.get("content_type") or "").lower() == "pdf" or url.lower().endswith(".pdf")
        return OpenAccessResult(
            source="doaj",
            pdf_url=url if is_pdf else None,
            landing_url=None if is_pdf else url,
            oa_status="gold",
        )
    return None


def _resolve_core(doi: str, _context: dict[str, Any]) -> OpenAccessResult | None:
    """CORE: aggregates institutional/repository OA copies. Requires an API key."""
    api_key = os.getenv(CORE_API_KEY_ENV)
    if not api_key or not api_key.strip():
        return None

    data = _post_json(
        CORE_API_URL,
        json_body={"doi": doi},
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    full_text_link = _clean_url((data or {}).get("fullTextLink"))
    if not full_text_link:
        return None

    return OpenAccessResult(source="core", pdf_url=full_text_link)


_PROVIDERS: dict[str, Callable[[str, dict[str, Any]], OpenAccessResult | None]] = {
    "arxiv": _resolve_arxiv,
    "unpaywall": _resolve_unpaywall,
    "openalex": _resolve_openalex,
    "europepmc": _resolve_europepmc,
    "doaj": _resolve_doaj,
    "core": _resolve_core,
}


def _provider_order() -> list[str]:
    raw_order = os.getenv(PROVIDER_ORDER_ENV, "")
    if raw_order.strip():
        requested = [name.strip().lower() for name in raw_order.split(",") if name.strip()]
        return [name for name in requested if name in _PROVIDERS]
    return list(DEFAULT_PROVIDER_ORDER)


def _contact_email() -> str | None:
    for env_var in (CONTACT_EMAIL_ENV, LEGACY_EMAIL_ENV):
        value = os.getenv(env_var)
        if value and value.strip():
            return value.strip()
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    """Return ``value`` if it is a dict, otherwise an empty dict (defensive)."""
    return value if isinstance(value, dict) else {}


def _clean_url(value: Any) -> str | None:
    """Accept only well-formed http(s) URLs from providers; reject everything else.

    Provider responses are untrusted input. Validating the scheme and host here
    keeps non-http(s) URLs (javascript:, file:, data:) and blank/whitespace values
    out of tool responses, instead of relying on a downstream consumer to do it.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def _get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    try:
        response = requests.get(
            url,
            params=params,
            headers=headers or {"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        LOGGER.debug("OA provider GET failed: %s", url, exc_info=True)
        return None


def _post_json(
    url: str,
    *,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    try:
        response = requests.post(
            url,
            json=json_body,
            headers=request_headers,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        LOGGER.debug("OA provider POST failed: %s", url, exc_info=True)
        return None
