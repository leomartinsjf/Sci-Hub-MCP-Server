from __future__ import annotations

import asyncio

import sci_hub_server


def test_should_publish_descriptions_for_all_mcp_tools() -> None:
    async def list_tools():
        return await sci_hub_server.mcp.list_tools()

    tools = asyncio.run(list_tools())

    tool_names = {tool.name for tool in tools}

    assert len(tools) >= 62
    assert {
        "download_scihub_pdf",
        "get_paper_metadata",
        "search_scihub_by_doi",
        "search_scihub_by_keyword",
        "search_scihub_by_title",
        "search_papers",
        "search_arxiv",
        "download_arxiv",
        "read_arxiv_paper",
        "search_crossref",
        "get_crossref_paper_by_doi",
        "download_with_fallback",
        "search_openalex",
        "search_unpaywall",
    }.issubset(tool_names)
    assert len(tool_names) == len(tools)
    assert all(tool.description for tool in tools)
