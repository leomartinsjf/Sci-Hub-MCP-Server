from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from paper_search_integration import register_paper_search_tools
from sci_hub_search import (
    MAX_KEYWORD_RESULTS,
    download_paper,
    get_crossref_metadata_by_doi,
    search_paper_by_doi,
    search_paper_by_title,
    search_papers_by_keyword,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

mcp = FastMCP("scihub")


@mcp.tool()
async def search_scihub_by_doi(doi: str) -> dict[str, Any]:
    """
    Search Sci-Hub for a paper by DOI and return the resolved PDF URL when available.

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
    Search CrossRef for a title, then resolve the best DOI match through Sci-Hub.

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
    Search CrossRef by keyword and return papers that can be resolved through Sci-Hub.

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


if __name__ == "__main__":
    logging.info(
        "Starting Sci-Hub MCP Server with keyword result limit %s and %s paper-search tools",
        MAX_KEYWORD_RESULTS,
        len(REGISTERED_PAPER_SEARCH_TOOLS),
    )
    mcp.run(transport="stdio")
