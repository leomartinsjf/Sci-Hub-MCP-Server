from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server.fastmcp import FastMCP

import sci_hub_server


def test_should_parse_default_stdio_transport() -> None:
    args = sci_hub_server.parse_args([])

    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.streamable_http_path == "/mcp"


def test_should_configure_streamable_http_transport_paths() -> None:
    args = sci_hub_server.parse_args(
        [
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--port",
            "9000",
            "--streamable-http-path",
            "mcp",
            "--sse-path",
            "events/",
            "--message-path",
            "messages",
            "--allowed-host",
            "scihub.example.org",
            "--allowed-origin",
            "https://claude.ai",
        ]
    )

    sci_hub_server.configure_server(args)

    assert args.transport == "streamable-http"
    assert sci_hub_server.mcp.settings.host == "0.0.0.0"
    assert sci_hub_server.mcp.settings.port == 9000
    assert sci_hub_server.mcp.settings.streamable_http_path == "/mcp"
    assert sci_hub_server.mcp.settings.sse_path == "/events"
    assert sci_hub_server.mcp.settings.message_path == "/messages/"
    assert "scihub.example.org" in sci_hub_server.mcp.settings.transport_security.allowed_hosts
    assert "https://claude.ai" in sci_hub_server.mcp.settings.transport_security.allowed_origins


def test_should_publish_descriptions_for_all_mcp_tools() -> None:
    async def list_tools():
        return await sci_hub_server.mcp.list_tools()

    tools = asyncio.run(list_tools())

    tool_names = {tool.name for tool in tools}

    assert len(tools) >= 64
    assert {
        "fetch",
        "download_scihub_pdf",
        "get_paper_metadata",
        "search",
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


def test_should_select_chatgpt_local_tool_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sci_hub_server.LOCAL_TOOL_SELECTION_ENV, "chatgpt")

    assert sci_hub_server._selected_local_tool_names() == ["search", "fetch"]


def test_should_register_only_chatgpt_local_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(sci_hub_server.LOCAL_TOOL_SELECTION_ENV, "chatgpt")
    mcp = FastMCP("test")

    registered_tools = sci_hub_server.register_local_tools(mcp)

    assert registered_tools == ["search", "fetch"]

    async def list_tools():
        return await mcp.list_tools()

    tool_names = {tool.name for tool in asyncio.run(list_tools())}
    assert tool_names == {"search", "fetch"}
    assert all(tool.annotations.readOnlyHint is True for tool in asyncio.run(list_tools()))


def test_should_return_standard_search_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_search_papers_by_keyword(keyword: str, num_results: int):
        assert keyword == "gambling interventions"
        assert num_results == sci_hub_server.DEFAULT_STANDARD_SEARCH_LIMIT
        return [
            {
                "doi": "10.1234/example",
                "title": "Example paper",
                "landing_url": "https://example.org/paper",
                "pdf_url": "https://example.org/paper.pdf",
            }
        ]

    monkeypatch.setattr(
        sci_hub_server,
        "search_papers_by_keyword",
        fake_search_papers_by_keyword,
    )

    payload = asyncio.run(sci_hub_server.search("gambling interventions"))

    assert payload == {
        "results": [
            {
                "id": "10.1234/example",
                "title": "Example paper",
                "url": "https://example.org/paper",
            }
        ]
    }


def test_should_fetch_standard_payload_without_scihub_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_fallback = None

    def fake_search_paper_by_doi(doi: str, *, allow_scihub_fallback: bool = True):
        nonlocal seen_fallback
        seen_fallback = allow_scihub_fallback
        return {
            "doi": doi,
            "status": "success",
            "title": "Example paper",
            "author": "Jane Doe",
            "year": "2026",
            "source": "unpaywall",
            "landing_url": "https://example.org/paper",
            "pdf_url": "https://example.org/paper.pdf",
            "is_open_access": True,
        }

    monkeypatch.setattr(sci_hub_server, "search_paper_by_doi", fake_search_paper_by_doi)

    payload = asyncio.run(sci_hub_server.fetch("10.1234/example"))

    assert seen_fallback is False
    assert payload["id"] == "10.1234/example"
    assert payload["title"] == "Example paper"
    assert payload["url"] == "https://example.org/paper"
    assert payload["metadata"]["source"] == "unpaywall"
    assert "Open-access PDF: https://example.org/paper.pdf" in payload["text"]


def test_should_return_standard_fetch_as_text_and_structured_content() -> None:
    async def call_tool():
        return await sci_hub_server.mcp.call_tool("fetch", {"id": ""})

    content, structured_content = asyncio.run(call_tool())

    assert json.loads(content[0].text) == structured_content
    assert structured_content == {
        "id": "",
        "title": "",
        "text": "No paper id was provided.",
        "url": "",
        "metadata": {"status": "not_found"},
    }
