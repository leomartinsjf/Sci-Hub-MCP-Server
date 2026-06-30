from __future__ import annotations

import asyncio

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
