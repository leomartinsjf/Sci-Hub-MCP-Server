from __future__ import annotations

from typing import Any

import pytest

import oa_resolver
from oa_resolver import resolve_open_access

DOI = "10.1234/example"


@pytest.fixture(autouse=True)
def _clear_resolver_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_var in (
        oa_resolver.CONTACT_EMAIL_ENV,
        oa_resolver.LEGACY_EMAIL_ENV,
        oa_resolver.PROVIDER_ORDER_ENV,
        oa_resolver.CORE_API_KEY_ENV,
    ):
        monkeypatch.delenv(env_var, raising=False)


def _patch_get(monkeypatch: pytest.MonkeyPatch, responses: dict[str, Any]) -> None:
    def fake_get(url: str, **_kwargs: Any) -> Any:
        for needle, payload in responses.items():
            if needle in url:
                return payload
        return None

    monkeypatch.setattr(oa_resolver, "_get_json", fake_get)


def _no_network(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("no network call expected")


def test_should_resolve_arxiv_doi_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oa_resolver, "_get_json", _no_network)

    result = resolve_open_access("10.48550/arXiv.2106.01345")

    assert result is not None
    assert result.source == "arxiv"
    assert result.pdf_url == "https://arxiv.org/pdf/2106.01345"
    assert result.best_url == "https://arxiv.org/pdf/2106.01345"


def test_should_skip_unpaywall_without_contact_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "unpaywall")
    _patch_get(
        monkeypatch,
        {"unpaywall": {"is_oa": True, "best_oa_location": {"url_for_pdf": "x"}}},
    )

    assert resolve_open_access(DOI) is None


def test_should_resolve_via_unpaywall_when_open_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.CONTACT_EMAIL_ENV, "researcher@uni.edu")
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "unpaywall")
    _patch_get(
        monkeypatch,
        {
            "unpaywall": {
                "is_oa": True,
                "oa_status": "gold",
                "best_oa_location": {
                    "url_for_pdf": "https://pub/p.pdf",
                    "url_for_landing_page": "https://pub/landing",
                    "license": "cc-by",
                    "version": "publishedVersion",
                },
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "unpaywall"
    assert result.pdf_url == "https://pub/p.pdf"
    assert result.landing_url == "https://pub/landing"
    assert result.oa_status == "gold"
    assert result.license == "cc-by"


def test_should_not_resolve_unpaywall_when_not_open_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oa_resolver.CONTACT_EMAIL_ENV, "researcher@uni.edu")
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "unpaywall")
    _patch_get(monkeypatch, {"unpaywall": {"is_oa": False}})

    assert resolve_open_access(DOI) is None


def test_should_resolve_via_openalex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "openalex")
    _patch_get(
        monkeypatch,
        {
            "openalex.org": {
                "open_access": {"is_oa": True, "oa_status": "green", "oa_url": "https://oa/u"},
                "best_oa_location": {
                    "pdf_url": "https://oa/p.pdf",
                    "landing_page_url": "https://oa/landing",
                    "license": "cc-by",
                },
                "primary_location": {},
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "openalex"
    assert result.pdf_url == "https://oa/p.pdf"
    assert result.oa_status == "green"


def test_should_render_europepmc_pmc_pdf_when_no_explicit_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "europepmc")
    _patch_get(
        monkeypatch,
        {
            "europepmc": {
                "resultList": {
                    "result": [
                        {
                            "pmcid": "PMC123",
                            "isOpenAccess": "Y",
                            "fullTextUrlList": {"fullTextUrl": []},
                        }
                    ]
                }
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "europepmc"
    assert result.pdf_url == "https://europepmc.org/articles/PMC123?pdf=render"


def test_should_prefer_open_access_pdf_over_subscription_in_europepmc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "europepmc")
    _patch_get(
        monkeypatch,
        {
            "europepmc": {
                "resultList": {
                    "result": [
                        {
                            "fullTextUrlList": {
                                "fullTextUrl": [
                                    {
                                        "availability": "Subscription required",
                                        "documentStyle": "pdf",
                                        "url": "https://paywall/p.pdf",
                                    },
                                    {
                                        "availability": "Open access",
                                        "documentStyle": "pdf",
                                        "url": "https://oa/p.pdf",
                                    },
                                ]
                            }
                        }
                    ]
                }
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.pdf_url == "https://oa/p.pdf"


def test_should_resolve_via_doaj_as_gold_oa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "doaj")
    _patch_get(
        monkeypatch,
        {
            "doaj.org": {
                "results": [
                    {
                        "bibjson": {
                            "link": [
                                {
                                    "type": "fulltext",
                                    "content_type": "PDF",
                                    "url": "https://doaj/p.pdf",
                                }
                            ]
                        }
                    }
                ]
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "doaj"
    assert result.pdf_url == "https://doaj/p.pdf"
    assert result.oa_status == "gold"


def test_should_skip_core_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "core")
    monkeypatch.setattr(oa_resolver, "_post_json", lambda *a, **k: {"fullTextLink": "x"})

    assert resolve_open_access(DOI) is None


def test_should_resolve_via_core_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "core")
    monkeypatch.setenv(oa_resolver.CORE_API_KEY_ENV, "secret")
    monkeypatch.setattr(oa_resolver, "_post_json", lambda *a, **k: {"fullTextLink": "https://core/p.pdf"})

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "core"
    assert result.pdf_url == "https://core/p.pdf"


def test_should_return_first_provider_that_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.CONTACT_EMAIL_ENV, "researcher@uni.edu")
    _patch_get(
        monkeypatch,
        {
            "unpaywall": {"is_oa": True, "best_oa_location": {"url_for_pdf": "https://up/p.pdf"}},
            "openalex.org": {
                "open_access": {"is_oa": True, "oa_url": "https://oa/u"},
                "best_oa_location": {"pdf_url": "https://oa/p.pdf"},
            },
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "unpaywall"


def test_should_return_none_when_all_providers_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.CONTACT_EMAIL_ENV, "researcher@uni.edu")
    _patch_get(monkeypatch, {})

    assert resolve_open_access(DOI) is None


def test_should_return_none_for_blank_doi() -> None:
    assert resolve_open_access("   ") is None


def test_should_ignore_unknown_provider_names_in_order_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "bogus, openalex")
    _patch_get(
        monkeypatch,
        {
            "openalex.org": {
                "open_access": {"is_oa": True, "oa_url": "https://oa/u"},
                "best_oa_location": {},
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.source == "openalex"
    assert result.best_url == "https://oa/u"


def test_should_keep_pdf_url_none_when_openalex_has_only_landing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "openalex")
    _patch_get(
        monkeypatch,
        {
            "openalex.org": {
                "open_access": {
                    "is_oa": True,
                    "oa_status": "bronze",
                    "oa_url": "https://oa/landing",
                },
                "best_oa_location": {},
                "primary_location": {},
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.pdf_url is None
    assert result.landing_url == "https://oa/landing"
    assert result.best_url == "https://oa/landing"


def test_should_reject_non_http_url_from_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "doaj")
    _patch_get(
        monkeypatch,
        {
            "doaj.org": {
                "results": [
                    {"bibjson": {"link": [{"type": "fulltext", "url": "javascript:alert(1)"}]}}
                ]
            }
        },
    )

    assert resolve_open_access(DOI) is None


def test_should_skip_whitespace_only_url_from_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "doaj")
    _patch_get(
        monkeypatch,
        {
            "doaj.org": {
                "results": [{"bibjson": {"link": [{"type": "fulltext", "url": "   \t  "}]}}]
            }
        },
    )

    assert resolve_open_access(DOI) is None


def test_should_skip_non_dict_entries_in_europepmc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(oa_resolver.PROVIDER_ORDER_ENV, "europepmc")
    _patch_get(
        monkeypatch,
        {
            "europepmc": {
                "resultList": {
                    "result": [
                        {
                            "fullTextUrlList": {
                                "fullTextUrl": [
                                    "not-a-dict",
                                    {
                                        "availability": "Open access",
                                        "documentStyle": "pdf",
                                        "url": "https://oa/p.pdf",
                                    },
                                ]
                            }
                        }
                    ]
                }
            }
        },
    )

    result = resolve_open_access(DOI)

    assert result is not None
    assert result.pdf_url == "https://oa/p.pdf"
