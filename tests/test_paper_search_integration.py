from __future__ import annotations

import ast
import asyncio
import inspect
import os
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP
from paper_search_mcp import server as paper_search_server

from oa_resolver import CONTACT_EMAIL_ENV, LEGACY_EMAIL_ENV
from paper_search_integration import (
    PAPER_SEARCH_TOOL_NAMES,
    TOOL_PROFILES,
    TOOL_SELECTION_ENV,
    _normalize_save_path,
    _selected_tool_names,
    _unify_contact_email,
    _wrap_tool,
    register_paper_search_tools,
)
from sci_hub_search import DOWNLOAD_DIR_ENV


async def _dummy_download(paper_id: str, save_path: str = "./downloads") -> str:
    return f"{paper_id}:{save_path}"


def test_should_preserve_wrapped_tool_signature() -> None:
    wrapped = _wrap_tool(_dummy_download)

    assert inspect.signature(wrapped) == inspect.signature(_dummy_download)


def test_should_track_complete_upstream_tool_set() -> None:
    source = inspect.getsource(paper_search_server)
    module = ast.parse(source)
    upstream_tool_names = {
        node.name
        for node in ast.walk(module)
        if isinstance(node, ast.AsyncFunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
    }

    assert len(upstream_tool_names) == 63
    assert upstream_tool_names == set(PAPER_SEARCH_TOOL_NAMES)


def test_should_normalize_default_download_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_dir = tmp_path / "downloads"
    monkeypatch.setenv(DOWNLOAD_DIR_ENV, str(download_dir))

    assert _normalize_save_path("./downloads") == str(download_dir)
    assert _normalize_save_path("nested") == str(download_dir / "nested")


def test_should_reject_save_path_outside_download_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_dir = tmp_path / "downloads"
    monkeypatch.setenv(DOWNLOAD_DIR_ENV, str(download_dir))

    with pytest.raises(ValueError, match="save_path must be inside"):
        _normalize_save_path("../outside")


def test_should_select_all_upstream_tools_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOOL_SELECTION_ENV, raising=False)

    assert _selected_tool_names() == PAPER_SEARCH_TOOL_NAMES


def test_should_select_core_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOOL_SELECTION_ENV, "core")

    assert _selected_tool_names() == TOOL_PROFILES["core"]


def test_should_select_no_upstream_tools_for_none_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOOL_SELECTION_ENV, "none")

    assert _selected_tool_names() == []


def test_should_select_explicit_allowlist_and_ignore_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOOL_SELECTION_ENV, "search_papers, bogus_tool , search_arxiv")

    assert _selected_tool_names() == ["search_papers", "search_arxiv"]


def test_should_register_only_core_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOOL_SELECTION_ENV, "core")
    mcp = FastMCP("test")

    registered = register_paper_search_tools(mcp)

    assert set(registered) <= set(TOOL_PROFILES["core"])
    assert "search_papers" in registered
    assert "search_arxiv" not in registered


def test_should_mirror_contact_email_to_unpaywall_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CONTACT_EMAIL_ENV, "me@uni.edu")
    monkeypatch.delenv(LEGACY_EMAIL_ENV, raising=False)
    monkeypatch.delenv("PAPER_SEARCH_MCP_UNPAYWALL_EMAIL", raising=False)

    _unify_contact_email()

    assert os.environ["UNPAYWALL_EMAIL"] == "me@uni.edu"
    assert os.environ["PAPER_SEARCH_MCP_UNPAYWALL_EMAIL"] == "me@uni.edu"


def test_should_not_override_existing_unpaywall_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(CONTACT_EMAIL_ENV, "contact@uni.edu")
    monkeypatch.setenv("UNPAYWALL_EMAIL", "existing@uni.edu")

    _unify_contact_email()

    assert os.environ["UNPAYWALL_EMAIL"] == "existing@uni.edu"


def test_should_redirect_wrapped_tool_stdout_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def noisy_tool(paper_id: str) -> str:
        print(f"stray stdout for {paper_id}")
        return "ok"

    wrapped = _wrap_tool(noisy_tool)
    result = asyncio.run(wrapped("123"))
    captured = capsys.readouterr()

    assert result == "ok"
    assert "stray stdout" not in captured.out
    assert "stray stdout" in captured.err
