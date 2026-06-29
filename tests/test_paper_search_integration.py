from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from paper_search_mcp import server as paper_search_server

from paper_search_integration import PAPER_SEARCH_TOOL_NAMES, _normalize_save_path, _wrap_tool
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
