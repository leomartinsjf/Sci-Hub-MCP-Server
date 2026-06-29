from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

import sci_hub_search
import sci_hub_server

RUN_NETWORK_TESTS_ENV = "SCIHUB_MCP_RUN_NETWORK_TESTS"
INTEGRATION_PDF_URL_ENV = "SCIHUB_MCP_INTEGRATION_PDF_URL"
DEFAULT_OPEN_ACCESS_PDF_URL = "https://arxiv.org/pdf/1706.03762"
DEFAULT_CROSSREF_DOI = "10.1038/nature14539"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv(RUN_NETWORK_TESTS_ENV) != "1",
    reason=f"set {RUN_NETWORK_TESTS_ENV}=1 to run network integration tests",
)
def test_should_fetch_real_crossref_metadata() -> None:
    metadata = sci_hub_search.get_crossref_metadata_by_doi(DEFAULT_CROSSREF_DOI)

    assert metadata["doi"] == DEFAULT_CROSSREF_DOI
    assert metadata["title"] == "Deep learning"
    assert metadata["year"] == "2015"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv(RUN_NETWORK_TESTS_ENV) != "1",
    reason=f"set {RUN_NETWORK_TESTS_ENV}=1 to run network integration tests",
)
def test_should_search_real_arxiv_via_integrated_mcp_tool() -> None:
    _content, structured = asyncio.run(
        sci_hub_server.mcp.call_tool(
            "search_arxiv",
            {"query": "attention is all you need", "max_results": 1},
        ),
    )

    papers = structured["result"]
    assert len(papers) == 1
    assert papers[0]["source"] == "arxiv"
    assert papers[0]["title"]
    assert papers[0]["url"].startswith("http")


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv(RUN_NETWORK_TESTS_ENV) != "1",
    reason=f"set {RUN_NETWORK_TESTS_ENV}=1 to run network integration tests",
)
def test_should_download_open_access_arxiv_pdf_via_integrated_mcp_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_dir = tmp_path / "integrated-downloads"
    monkeypatch.setenv(sci_hub_search.DOWNLOAD_DIR_ENV, str(download_dir))

    _content, structured = asyncio.run(
        sci_hub_server.mcp.call_tool(
            "download_arxiv",
            {"paper_id": "1706.03762", "save_path": "./downloads"},
        ),
    )

    downloaded_pdf = Path(structured["result"])
    assert downloaded_pdf.exists()
    assert downloaded_pdf.is_relative_to(download_dir)
    assert downloaded_pdf.stat().st_size > 1024
    assert downloaded_pdf.read_bytes().startswith(b"%PDF-")


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv(RUN_NETWORK_TESTS_ENV) != "1",
    reason=f"set {RUN_NETWORK_TESTS_ENV}=1 to run network integration tests",
)
def test_should_download_real_open_access_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_dir = tmp_path / "downloads"
    pdf_url = os.getenv(INTEGRATION_PDF_URL_ENV, DEFAULT_OPEN_ACCESS_PDF_URL)

    monkeypatch.setenv(sci_hub_search.DOWNLOAD_DIR_ENV, str(download_dir))
    monkeypatch.setenv(sci_hub_search.MAX_DOWNLOAD_BYTES_ENV, str(5 * 1024 * 1024))

    assert sci_hub_search.download_paper(pdf_url, "integration/arxiv-paper.pdf")

    downloaded_pdf = download_dir / "integration" / "arxiv-paper.pdf"
    assert downloaded_pdf.exists()
    assert downloaded_pdf.stat().st_size > 1024
    assert downloaded_pdf.read_bytes().startswith(b"%PDF-")
