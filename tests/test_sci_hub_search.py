from __future__ import annotations

from typing import Any

import pytest

import sci_hub_search


class FakeDownloadResponse:
    def __init__(self, chunks: list[bytes], content_type: str = "application/pdf") -> None:
        self.headers = {"Content-Type": content_type}
        self._chunks = chunks

    def __enter__(self) -> FakeDownloadResponse:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return self._chunks


def test_should_use_crossref_params_when_searching_by_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params)
        return {
            "message": {
                "items": [
                    {
                        "DOI": "10.123/example",
                        "title": ["Example title"],
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "issued": {"date-parts": [[1843]]},
                    }
                ]
            }
        }

    monkeypatch.setattr(sci_hub_search, "_request_crossref", fake_request)
    monkeypatch.setattr(
        sci_hub_search,
        "search_paper_by_doi",
        lambda doi: {"doi": doi, "status": "success", "pdf_url": "https://example.org/a.pdf"},
    )

    result = sci_hub_search.search_paper_by_title(" Example & title ")

    assert calls == [{"query.title": "Example & title", "rows": 1}]
    assert result == {
        "doi": "10.123/example",
        "status": "success",
        "pdf_url": "https://example.org/a.pdf",
        "title": "Example title",
        "author": "Ada Lovelace",
        "year": "1843",
    }


def test_should_clamp_keyword_result_count(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params)
        return {"message": {"items": []}}

    monkeypatch.setattr(sci_hub_search, "_request_crossref", fake_request)

    assert sci_hub_search.search_papers_by_keyword("ai", num_results=999) == []
    assert calls == [{"query": "ai", "rows": sci_hub_search.MAX_KEYWORD_RESULTS}]


def test_should_download_pdf_inside_configured_directory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_dir = tmp_path / "allowed"
    monkeypatch.setenv(sci_hub_search.DOWNLOAD_DIR_ENV, str(target_dir))
    monkeypatch.setattr(
        sci_hub_search.requests,
        "get",
        lambda *_args, **_kwargs: FakeDownloadResponse([b"%PDF-1.7\n", b"body"]),
    )

    assert sci_hub_search.download_paper("https://example.org/paper.pdf", "nested/paper.pdf")
    assert (target_dir / "nested" / "paper.pdf").read_bytes() == b"%PDF-1.7\nbody"


def test_should_reject_download_paths_outside_configured_directory(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(sci_hub_search.DOWNLOAD_DIR_ENV, str(tmp_path / "allowed"))

    with pytest.raises(ValueError, match="inside"):
        sci_hub_search.download_paper("https://example.org/paper.pdf", "../paper.pdf")


def test_should_reject_non_pdf_download_content(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_dir = tmp_path / "allowed"
    monkeypatch.setenv(sci_hub_search.DOWNLOAD_DIR_ENV, str(target_dir))
    monkeypatch.setattr(
        sci_hub_search.requests,
        "get",
        lambda *_args, **_kwargs: FakeDownloadResponse(
            [b"<html></html>"],
            content_type="application/pdf",
        ),
    )

    with pytest.raises(ValueError, match="not a PDF"):
        sci_hub_search.download_paper("https://example.org/paper.pdf", "paper.pdf")

    assert not (target_dir / "paper.pdf.tmp").exists()
