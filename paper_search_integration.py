from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from paper_search_mcp import server as paper_search_server

from sci_hub_search import DEFAULT_DOWNLOAD_DIR, DOWNLOAD_DIR_ENV, _download_dir

PAPER_SEARCH_MCP_COMMIT = "dba2c7430aec7e17463ad981caf1d391f0204335"

PAPER_SEARCH_TOOL_NAMES = [
    "search_papers",
    "search_arxiv",
    "search_pubmed",
    "search_biorxiv",
    "search_medrxiv",
    "search_google_scholar",
    "search_iacr",
    "download_arxiv",
    "download_pubmed",
    "download_biorxiv",
    "download_medrxiv",
    "download_iacr",
    "read_arxiv_paper",
    "read_pubmed_paper",
    "read_biorxiv_paper",
    "read_medrxiv_paper",
    "read_iacr_paper",
    "search_semantic",
    "download_semantic",
    "read_semantic_paper",
    "search_crossref",
    "get_crossref_paper_by_doi",
    "download_crossref",
    "download_scihub",
    "download_with_fallback",
    "read_crossref_paper",
    "search_openalex",
    "search_pmc",
    "search_core",
    "search_europepmc",
    "search_dblp",
    "search_openaire",
    "search_citeseerx",
    "search_doaj",
    "search_base",
    "search_zenodo",
    "search_hal",
    "search_ssrn",
    "search_unpaywall",
    "read_dblp_paper",
    "download_dblp",
    "read_openaire_paper",
    "download_openaire",
    "read_citeseerx_paper",
    "download_citeseerx",
    "read_doaj_paper",
    "download_doaj",
    "read_base_paper",
    "download_base",
    "read_zenodo_paper",
    "download_zenodo",
    "read_hal_paper",
    "download_hal",
    "read_ssrn_paper",
    "download_ssrn",
    "read_openalex_paper",
    "download_openalex",
    "search_ieee",
    "download_ieee",
    "read_ieee_paper",
    "search_acm",
    "download_acm",
    "read_acm_paper",
]


def register_paper_search_tools(mcp: FastMCP) -> list[str]:
    """Register paper-search-mcp tools on the local MCP server."""
    registered_tools = []

    for tool_name in PAPER_SEARCH_TOOL_NAMES:
        tool_fn = getattr(paper_search_server, tool_name, None)
        if tool_fn is None:
            continue

        mcp.add_tool(_wrap_tool(tool_fn), name=tool_name)
        registered_tools.append(tool_name)

    return registered_tools


def _wrap_tool(tool_fn: Callable[..., Any]) -> Callable[..., Any]:
    signature = inspect.signature(tool_fn)

    @functools.wraps(tool_fn)
    async def wrapped_tool(*args: Any, **kwargs: Any) -> Any:
        bound_args = signature.bind_partial(*args, **kwargs)
        bound_args.apply_defaults()

        if "save_path" in signature.parameters:
            bound_args.arguments["save_path"] = _normalize_save_path(
                str(bound_args.arguments.get("save_path") or DEFAULT_DOWNLOAD_DIR),
            )

        return await tool_fn(*bound_args.args, **bound_args.kwargs)

    wrapped_tool.__signature__ = signature
    return wrapped_tool


def _normalize_save_path(save_path: str) -> str:
    download_dir = _download_dir()
    requested_path = Path(save_path).expanduser()

    if requested_path in {Path("."), Path(DEFAULT_DOWNLOAD_DIR), Path(f"./{DEFAULT_DOWNLOAD_DIR}")}:
        target_path = download_dir
    elif requested_path.is_absolute():
        target_path = requested_path.resolve()
    else:
        target_path = (download_dir / requested_path).resolve()

    try:
        target_path.relative_to(download_dir)
    except ValueError as exc:
        raise ValueError(f"save_path must be inside {DOWNLOAD_DIR_ENV} ({download_dir})") from exc

    return str(target_path)
