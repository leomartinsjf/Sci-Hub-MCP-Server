from __future__ import annotations

import argparse
import asyncio
import logging
import os
import warnings
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict

from paper_search_integration import register_paper_search_tools
from sci_hub_search import (
    MAX_KEYWORD_RESULTS,
    download_paper,
    get_crossref_metadata_by_doi,
    scihub_fallback_enabled,
    search_paper_by_doi,
    search_paper_by_title,
    search_papers_by_keyword,
)

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# force=True: importing mcp/rich installs a root handler before this runs, which
# would make a plain basicConfig() a no-op (leaving the root at WARNING and
# dropping our INFO startup summary). force=True reclaims the root logger.
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)

# The Sci-Hub last-resort fallback makes unverified-HTTPS requests; keep its
# InsecureRequestWarning off stderr so server logs stay clean.
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_STREAMABLE_HTTP_PATH = "/mcp"
DEFAULT_SSE_PATH = "/sse"
DEFAULT_MESSAGE_PATH = "/messages/"
DEFAULT_MOUNT_PATH = "/"
DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*")
LOCAL_TOOL_SELECTION_ENV = "SCIHUB_MCP_LOCAL_TOOLS"
DEFAULT_STANDARD_SEARCH_LIMIT = 5

READ_ONLY_REMOTE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
DOWNLOAD_TOOL_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

mcp = FastMCP("scihub")


class StandardSearchResult(TypedDict):
    id: str
    title: str
    url: str


class StandardSearchPayload(TypedDict):
    results: list[StandardSearchResult]


class StandardFetchPayload(TypedDict):
    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, Any]


async def search(query: str) -> StandardSearchPayload:
    """
    Search for open-access academic papers and return ChatGPT-compatible results.

    Use this when a ChatGPT or Codex client needs a read-only knowledge lookup.
    FastMCP exposes this as structured content and JSON text content. Each result
    has `id`, `title`, and `url`; pass `id` to `fetch` for details.

    Args:
        query: Research keyword, title fragment, DOI, or phrase.
    """
    logging.info("Running standard search for query: %s", query)
    try:
        papers = await asyncio.to_thread(
            search_papers_by_keyword,
            query,
            DEFAULT_STANDARD_SEARCH_LIMIT,
        )
    except Exception as exc:
        logging.exception("Standard search failed")
        logging.debug("Search error detail: %s", exc)
        return {"results": []}

    return {
        "results": [
            search_result
            for paper in papers
            if (search_result := _to_standard_search_result(paper)) is not None
        ]
    }


async def fetch(id: str) -> StandardFetchPayload:
    """
    Fetch one open-access paper record by DOI and return ChatGPT-compatible text.

    Use this after `search`, passing the search result `id`. The resolver remains
    open-access-only here; Sci-Hub fallback is disabled for the standard ChatGPT
    data-app surface.

    Args:
        id: Paper identifier from `search`, normally a DOI.
    """
    logging.info("Running standard fetch for id: %s", id)
    identifier = id.strip()
    if not identifier:
        return {
            "id": id,
            "title": "",
            "text": "No paper id was provided.",
            "url": "",
            "metadata": {"status": "not_found"},
        }

    try:
        paper = await asyncio.to_thread(
            search_paper_by_doi,
            identifier,
            allow_scihub_fallback=False,
        )
    except Exception as exc:
        logging.exception("Standard fetch failed")
        return {
            "id": identifier,
            "title": identifier,
            "text": f"Fetch failed: {exc}",
            "url": _doi_url(identifier),
            "metadata": {"status": "error"},
        }

    return _to_standard_fetch_payload(identifier, paper)


async def search_scihub_by_doi(doi: str) -> dict[str, Any]:
    """
    Resolve a paper by DOI to a full-text URL, preferring legal open-access sources.

    Tries open-access providers first (arXiv, Unpaywall, OpenAlex, Europe PMC, DOAJ,
    and CORE when configured). Sci-Hub is used only as a last resort, when no
    open-access copy is found and SCIHUB_MCP_ENABLE_SCIHUB_FALLBACK is enabled.
    The "source" field in the response reports where the URL came from.

    Args:
        doi: Digital Object Identifier, for example "10.1038/nature09492".
    """
    logging.info("Searching for paper with DOI: %s", doi)
    try:
        return await asyncio.to_thread(search_paper_by_doi, doi)
    except Exception as exc:
        logging.exception("DOI search failed")
        return {"status": "error", "error": f"DOI search failed: {exc}"}


async def search_scihub_by_title(title: str) -> dict[str, Any]:
    """
    Search CrossRef for a title, then resolve the best DOI match to a full-text URL.

    Resolution prefers legal open-access sources and falls back to Sci-Hub only as a
    last resort (see search_scihub_by_doi).

    Args:
        title: Full or partial academic paper title.
    """
    logging.info("Searching for paper with title: %s", title)
    try:
        return await asyncio.to_thread(search_paper_by_title, title)
    except Exception as exc:
        logging.exception("Title search failed")
        return {"status": "error", "error": f"Title search failed: {exc}"}


async def search_scihub_by_keyword(
    keyword: str,
    num_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Search CrossRef by keyword and return papers that have an open-access full text.

    Bulk keyword resolution uses open-access providers only; the Sci-Hub fallback is
    disabled here to avoid automated bulk scraping.

    Args:
        keyword: Research keyword or phrase.
        num_results: Requested result count. Values are clamped to 1-20.
    """
    logging.info(
        "Searching for papers with keyword: %s, requested results: %s",
        keyword,
        num_results,
    )
    try:
        return await asyncio.to_thread(search_papers_by_keyword, keyword, num_results)
    except Exception as exc:
        logging.exception("Keyword search failed")
        return [{"status": "error", "error": f"Keyword search failed: {exc}"}]


async def download_scihub_pdf(pdf_url: str, output_path: str) -> str:
    """
    Download a PDF URL to the configured download directory.

    Args:
        pdf_url: Direct HTTP or HTTPS URL for a PDF.
        output_path: Relative .pdf path under SCIHUB_MCP_DOWNLOAD_DIR, or under ./downloads
            when the environment variable is not set.
    """
    logging.info("Attempting to download PDF from %s to %s", pdf_url, output_path)
    try:
        await asyncio.to_thread(download_paper, pdf_url, output_path)
        return f"PDF successfully downloaded to {output_path}"
    except Exception as exc:
        logging.exception("PDF download failed")
        return f"PDF download failed: {exc}"


async def get_paper_metadata(doi: str) -> dict[str, Any]:
    """
    Get metadata for a paper DOI from CrossRef.

    Args:
        doi: Digital Object Identifier, for example "10.1038/nature09492".
    """
    logging.info("Getting metadata for paper with DOI: %s", doi)
    try:
        metadata = await asyncio.to_thread(get_crossref_metadata_by_doi, doi)
    except Exception as exc:
        logging.exception("Metadata lookup failed")
        return {"status": "error", "error": f"Metadata lookup failed: {exc}"}

    if not metadata:
        return {"doi": doi, "status": "not_found"}

    metadata["status"] = "success"
    metadata["doi"] = metadata.get("doi") or doi
    return metadata


LOCAL_TOOL_REGISTRY = {
    "search": (search, READ_ONLY_REMOTE_ANNOTATIONS),
    "fetch": (fetch, READ_ONLY_REMOTE_ANNOTATIONS),
    "search_scihub_by_doi": (search_scihub_by_doi, READ_ONLY_REMOTE_ANNOTATIONS),
    "search_scihub_by_title": (search_scihub_by_title, READ_ONLY_REMOTE_ANNOTATIONS),
    "search_scihub_by_keyword": (search_scihub_by_keyword, READ_ONLY_REMOTE_ANNOTATIONS),
    "download_scihub_pdf": (download_scihub_pdf, DOWNLOAD_TOOL_ANNOTATIONS),
    "get_paper_metadata": (get_paper_metadata, READ_ONLY_REMOTE_ANNOTATIONS),
}
LOCAL_TOOL_PROFILES = {
    "all": list(LOCAL_TOOL_REGISTRY),
    "chatgpt": ["search", "fetch"],
    "standard": ["search", "fetch"],
    "none": [],
}


def register_local_tools(server: FastMCP) -> list[str]:
    """Register local tools selected by SCIHUB_MCP_LOCAL_TOOLS."""
    registered_tools = []
    for tool_name in _selected_local_tool_names():
        tool_config = LOCAL_TOOL_REGISTRY.get(tool_name)
        if tool_config is None:
            continue

        tool_fn, annotations = tool_config
        server.add_tool(
            tool_fn,
            name=tool_name,
            annotations=annotations,
            structured_output=tool_name in {"search", "fetch"},
        )
        registered_tools.append(tool_name)

    return registered_tools


def _selected_local_tool_names() -> list[str]:
    """Resolve local tools from SCIHUB_MCP_LOCAL_TOOLS."""
    raw_selection = os.getenv(LOCAL_TOOL_SELECTION_ENV, "all").strip()
    if not raw_selection:
        raw_selection = "all"

    normalized_selection = raw_selection.lower()
    if normalized_selection in LOCAL_TOOL_PROFILES:
        return list(LOCAL_TOOL_PROFILES[normalized_selection])

    known = set(LOCAL_TOOL_REGISTRY)
    requested = [name.strip() for name in raw_selection.split(",") if name.strip()]
    selected = [name for name in requested if name in known]
    unknown = [name for name in requested if name not in known]
    if unknown:
        logging.warning(
            "Ignoring unknown %s entries: %s",
            LOCAL_TOOL_SELECTION_ENV,
            ", ".join(unknown),
        )
    return selected


def _to_standard_search_result(paper: dict[str, Any]) -> StandardSearchResult | None:
    paper_id = str(paper.get("doi") or "").strip()
    if not paper_id:
        return None

    title = str(paper.get("title") or paper_id).strip()
    return {
        "id": paper_id,
        "title": title or paper_id,
        "url": _citation_url(paper, paper_id),
    }


def _to_standard_fetch_payload(identifier: str, paper: dict[str, Any]) -> StandardFetchPayload:
    paper_id = str(paper.get("doi") or identifier).strip()
    title = str(paper.get("title") or paper_id).strip()
    metadata = {
        key: value
        for key, value in {
            "doi": paper_id,
            "author": paper.get("author"),
            "year": paper.get("year"),
            "source": paper.get("source"),
            "oa_status": paper.get("oa_status"),
            "license": paper.get("license"),
            "is_open_access": paper.get("is_open_access"),
            "status": paper.get("status"),
        }.items()
        if value not in {None, ""}
    }

    if paper.get("status") == "success":
        text_parts = [
            f"Title: {title}",
            f"DOI: {paper_id}",
            f"Source: {paper.get('source', 'open-access')}",
        ]
        if paper.get("author"):
            text_parts.append(f"Authors: {paper['author']}")
        if paper.get("year"):
            text_parts.append(f"Year: {paper['year']}")
        if paper.get("pdf_url"):
            text_parts.append(f"Open-access PDF: {paper['pdf_url']}")
        if paper.get("landing_url"):
            text_parts.append(f"Landing page: {paper['landing_url']}")
    else:
        text_parts = [
            f"Title: {title}",
            f"DOI: {paper_id}",
            "No open-access full text was found by the OA-first resolver.",
        ]

    return {
        "id": paper_id,
        "title": title,
        "text": "\n".join(text_parts),
        "url": _citation_url(paper, paper_id),
        "metadata": metadata,
    }


def _citation_url(paper: dict[str, Any], paper_id: str) -> str:
    for key in ("landing_url", "pdf_url"):
        value = str(paper.get(key) or "").strip()
        if value:
            return value
    return _doi_url(paper_id)


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi.strip()}" if doi.strip() else ""


REGISTERED_LOCAL_TOOLS = register_local_tools(mcp)
REGISTERED_PAPER_SEARCH_TOOLS = register_paper_search_tools(mcp)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI settings for local stdio and remote HTTP/SSE MCP transports."""
    parser = argparse.ArgumentParser(description="Run the Sci-Hub MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", DEFAULT_TRANSPORT),
        help=(
            "MCP transport to run. Use stdio for local MCP clients and "
            "streamable-http for remote MCP clients."
        ),
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", DEFAULT_HOST),
        help="Host for HTTP transports.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", str(DEFAULT_PORT))),
        help="Port for HTTP transports.",
    )
    parser.add_argument(
        "--streamable-http-path",
        default=os.getenv("MCP_STREAMABLE_HTTP_PATH", DEFAULT_STREAMABLE_HTTP_PATH),
        help="HTTP path for streamable-http transport.",
    )
    parser.add_argument(
        "--sse-path",
        default=os.getenv("MCP_SSE_PATH", DEFAULT_SSE_PATH),
        help="HTTP path for SSE transport.",
    )
    parser.add_argument(
        "--message-path",
        default=os.getenv("MCP_MESSAGE_PATH", DEFAULT_MESSAGE_PATH),
        help="Message path used by SSE transport.",
    )
    parser.add_argument(
        "--mount-path",
        default=os.getenv("MCP_MOUNT_PATH", DEFAULT_MOUNT_PATH),
        help="Optional mount path for SSE transport.",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help=(
            "Additional allowed Host header for HTTP transports. Can be repeated. "
            "Also accepts comma-separated MCP_ALLOWED_HOSTS."
        ),
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help=(
            "Additional allowed Origin header for HTTP transports. Can be repeated. "
            "Also accepts comma-separated MCP_ALLOWED_ORIGINS."
        ),
    )
    return parser.parse_args(argv)


def _normalize_path(path: str, *, trailing_slash: bool = False) -> str:
    normalized_path = path.strip() or "/"
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if trailing_slash and not normalized_path.endswith("/"):
        normalized_path = f"{normalized_path}/"
    if not trailing_slash and len(normalized_path) > 1:
        normalized_path = normalized_path.rstrip("/")
    return normalized_path


def configure_server(args: argparse.Namespace) -> None:
    """Apply parsed network transport settings to FastMCP."""
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = _normalize_path(args.streamable_http_path)
    mcp.settings.sse_path = _normalize_path(args.sse_path)
    mcp.settings.message_path = _normalize_path(args.message_path, trailing_slash=True)
    mcp.settings.transport_security.allowed_hosts = _merge_csv_options(
        DEFAULT_ALLOWED_HOSTS,
        os.getenv("MCP_ALLOWED_HOSTS", ""),
        args.allowed_host,
    )
    mcp.settings.transport_security.allowed_origins = _merge_csv_options(
        DEFAULT_ALLOWED_ORIGINS,
        os.getenv("MCP_ALLOWED_ORIGINS", ""),
        args.allowed_origin,
    )


def _merge_csv_options(
    default_values: tuple[str, ...],
    env_value: str,
    cli_values: list[str],
) -> list[str]:
    values = list(default_values)
    for raw_value in [env_value, *cli_values]:
        for item in raw_value.split(","):
            normalized_item = item.strip()
            if normalized_item:
                values.append(normalized_item)
    return list(dict.fromkeys(values))


def main(argv: list[str] | None = None) -> None:
    """Console entry point for local and remote MCP transports."""
    args = parse_args(argv)
    configure_server(args)
    contact_email_set = bool(os.getenv("SCIHUB_MCP_CONTACT_EMAIL") or os.getenv("UNPAYWALL_EMAIL"))
    logging.info(
        "Starting Sci-Hub MCP Server | local tools=%s | local_profile=%s | "
        "paper-search tools=%s | profile=%s | "
        "contact_email=%s | core_api_key=%s | scihub_fallback=%s | keyword_limit=%s | "
        "transport=%s | host=%s | port=%s | streamable_http_path=%s | allowed_hosts=%s",
        len(REGISTERED_LOCAL_TOOLS),
        os.getenv(LOCAL_TOOL_SELECTION_ENV, "all"),
        len(REGISTERED_PAPER_SEARCH_TOOLS),
        os.getenv("SCIHUB_MCP_TOOLS", "all"),
        "set" if contact_email_set else "unset",
        "set" if os.getenv("CORE_API_KEY") else "unset",
        "on" if scihub_fallback_enabled() else "off",
        MAX_KEYWORD_RESULTS,
        args.transport,
        mcp.settings.host,
        mcp.settings.port,
        mcp.settings.streamable_http_path,
        ",".join(mcp.settings.transport_security.allowed_hosts),
    )
    if args.transport == "sse":
        mcp.run(transport="sse", mount_path=_normalize_path(args.mount_path))
    else:
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
