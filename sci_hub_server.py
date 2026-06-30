from __future__ import annotations

import argparse
import asyncio
import logging
import os
import warnings
from typing import Any

from mcp.server.fastmcp import FastMCP

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

mcp = FastMCP("scihub")


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


REGISTERED_PAPER_SEARCH_TOOLS = register_paper_search_tools(mcp)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI settings for local stdio and remote HTTP/SSE MCP transports."""
    parser = argparse.ArgumentParser(description="Run the Sci-Hub MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.getenv("MCP_TRANSPORT", DEFAULT_TRANSPORT),
        help=(
            "MCP transport to run. Use stdio for Claude Code and streamable-http "
            "for Claude remote connectors."
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
        "Starting Sci-Hub MCP Server | paper-search tools=%s | profile=%s | "
        "contact_email=%s | core_api_key=%s | scihub_fallback=%s | keyword_limit=%s | "
        "transport=%s | host=%s | port=%s | streamable_http_path=%s | allowed_hosts=%s",
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
