from __future__ import annotations

from typing import Any

import pytest

import sci_hub_search
from oa_resolver import OpenAccessResult


def _fail_scihub(_doi: str) -> OpenAccessResult | None:
    raise AssertionError("Sci-Hub fallback must not run here")


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


def test_should_prefer_open_access_over_scihub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sci_hub_search,
        "get_crossref_metadata_by_doi",
        lambda _doi: {"title": "T", "author": "A", "year": "2020"},
    )
    monkeypatch.setattr(
        sci_hub_search,
        "resolve_open_access",
        lambda _doi: OpenAccessResult(
            source="unpaywall", pdf_url="https://oa/p.pdf", oa_status="gold", license="cc-by"
        ),
    )
    monkeypatch.setattr(sci_hub_search, "_resolve_via_scihub", _fail_scihub)

    result = sci_hub_search.search_paper_by_doi("10.1/x")

    assert result["status"] == "success"
    assert result["source"] == "unpaywall"
    assert result["pdf_url"] == "https://oa/p.pdf"
    assert result["is_open_access"] is True
    assert result["title"] == "T"


def test_should_fall_back_to_scihub_when_no_open_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sci_hub_search, "get_crossref_metadata_by_doi", lambda _doi: {})
    monkeypatch.setattr(sci_hub_search, "resolve_open_access", lambda _doi: None)
    monkeypatch.setattr(
        sci_hub_search,
        "_resolve_via_scihub",
        lambda _doi: OpenAccessResult(source="scihub", pdf_url="https://sci/p.pdf"),
    )
    monkeypatch.setenv(sci_hub_search.ENABLE_SCIHUB_FALLBACK_ENV, "1")

    result = sci_hub_search.search_paper_by_doi("10.1/x")

    assert result["status"] == "success"
    assert result["source"] == "scihub"
    assert result["is_open_access"] is False


def test_should_not_use_scihub_when_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sci_hub_search, "get_crossref_metadata_by_doi", lambda _doi: {})
    monkeypatch.setattr(sci_hub_search, "resolve_open_access", lambda _doi: None)
    monkeypatch.setattr(sci_hub_search, "_resolve_via_scihub", _fail_scihub)
    monkeypatch.setenv(sci_hub_search.ENABLE_SCIHUB_FALLBACK_ENV, "0")

    result = sci_hub_search.search_paper_by_doi("10.1/x")

    assert result["status"] == "not_found"


def test_should_disable_scihub_fallback_for_keyword_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_doi_search(doi: str, *, allow_scihub_fallback: bool = True) -> dict[str, Any]:
        captured["allow_scihub_fallback"] = allow_scihub_fallback
        return {"status": "success", "doi": doi, "pdf_url": "u", "source": "unpaywall"}

    monkeypatch.setattr(
        sci_hub_search,
        "_request_crossref",
        lambda _params: {"message": {"items": [{"DOI": "10.1/x", "title": ["T"]}]}},
    )
    monkeypatch.setattr(sci_hub_search, "search_paper_by_doi", fake_doi_search)

    papers = sci_hub_search.search_papers_by_keyword("ai", 1)

    assert captured["allow_scihub_fallback"] is False
    assert len(papers) == 1


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


def test_should_inject_default_timeout_into_scihub_session() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def request(self, method: str, url: str, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            return "resp"

    session = FakeSession()
    sci_hub_search._apply_default_timeout(session, 7)

    session.request("GET", "http://example.org")
    session.request("GET", "http://example.org", timeout=1)

    assert session.calls[0]["timeout"] == 7
    assert session.calls[1]["timeout"] == 1


def test_should_wrap_scihub_session_request_with_timeout() -> None:
    instance = sci_hub_search.create_scihub_instance()

    assert hasattr(instance.session.request, "__wrapped__")
