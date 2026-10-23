"""Protect the boundary between a desktop chooser and repository selection."""

import json
from pathlib import Path
import subprocess

import pytest


def picker_module(monkeypatch, platform="darwin"):
    from repolens import folder_picker

    monkeypatch.setattr(folder_picker.sys, "platform", platform)
    return folder_picker


def test_mac_selection_preserves_spaces_quotes_and_uses_argument_list(
    tmp_path, monkeypatch
):
    picker = picker_module(monkeypatch)
    selected = tmp_path / 'my "repo" with spaces'
    selected.mkdir()
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, str(selected) + "/\n", "")

    monkeypatch.setattr(picker.subprocess, "run", run)
    assert picker.choose_repository_folder(tmp_path) == selected
    args, options = calls[0]
    assert args[0] == "/usr/bin/osascript"
    assert args[-1] == str(tmp_path)
    assert not options.get("shell", False)
    assert 0 < options["timeout"] <= 180


def test_mac_cancel_returns_none(monkeypatch):
    picker = picker_module(monkeypatch)
    monkeypatch.setattr(
        picker.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "User canceled. (-128)"),
    )
    assert picker.choose_repository_folder() is None


@pytest.mark.parametrize("failure", ["nonzero", "missing", "timeout", "invalid"])
def test_picker_failure_is_actionable(tmp_path, monkeypatch, failure):
    from repolens.errors import RepoLensError

    picker = picker_module(monkeypatch)

    def run(args, **kwargs):
        if failure == "missing":
            raise FileNotFoundError("no desktop picker")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        if failure == "invalid":
            return subprocess.CompletedProcess(args, 0, str(tmp_path / "missing"), "")
        return subprocess.CompletedProcess(args, 1, "", "desktop unavailable")

    monkeypatch.setattr(picker.subprocess, "run", run)
    with pytest.raises(RepoLensError, match="manual"):
        picker.choose_repository_folder()


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_other_desktops_decode_json_paths(tmp_path, monkeypatch, platform):
    picker = picker_module(monkeypatch, platform)
    folder = tmp_path / "source"
    folder.mkdir()
    monkeypatch.setattr(
        picker.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(
            args, 0, json.dumps(str(folder)) + "\n", ""
        ),
    )
    assert picker.choose_repository_folder() == folder


@pytest.mark.parametrize("response", ["", "null", "[]", "not JSON"])
def test_non_mac_malformed_result_is_not_a_folder(monkeypatch, response):
    from repolens.errors import RepoLensError

    picker = picker_module(monkeypatch, "linux")
    monkeypatch.setattr(
        picker.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 0, response, ""),
    )
    with pytest.raises(RepoLensError):
        picker.choose_repository_folder()


def test_other_desktop_cancel_returns_none(monkeypatch):
    picker = picker_module(monkeypatch, "linux")
    monkeypatch.setattr(
        picker.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 0, '""\n', ""),
    )
    assert picker.choose_repository_folder() is None
