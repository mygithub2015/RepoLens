from dataclasses import replace
from pathlib import Path
import pytest


def test_eligibility_nested_ignores_and_hard_exclusions(source_root, tmp_path):
    from repolens.config import Limits
    from repolens.repository import scan_repository

    (source_root / ".gitignore").write_text("*.java\nignored/\n")
    sub = source_root / "sub"
    sub.mkdir()
    (sub / ".gitignore").write_text("!Keep.java\n!secret.key\n")
    (sub / "Keep.java").write_text("class Keep {}")
    (sub / "secret.key").write_text("secret")
    ignored = source_root / "ignored"
    ignored.mkdir()
    (ignored / ".gitignore").write_text("!hidden.py")
    (ignored / "hidden.py").write_text("x=1")
    (source_root / "link.py").symlink_to(source_root / "app.py")
    (source_root / ".env").write_text("SECRET=1")
    scan = scan_repository(source_root, tmp_path / "data", Limits())
    assert {f.relative_path for f in scan.files} == {
        "app.py",
        "app.js",
        "sub/Keep.java",
    }
    assert scan.skipped


def test_utf8_bom_crlf_and_invalid_files(source_root, tmp_path):
    from repolens.config import Limits
    from repolens.repository import scan_repository

    (source_root / "bom.py").write_bytes(b'\xef\xbb\xbfx="\xc3\xa9"\r\nsecond=2\r\n')
    (source_root / "binary.py").write_bytes(b"x\x00y")
    (source_root / "encoding.py").write_bytes(b"\xff")
    (source_root / "empty.py").write_bytes(b"")
    (source_root / "long.py").write_text("x" * 4001)
    scan = scan_repository(source_root, tmp_path / "data", Limits())
    file = next(f for f in scan.files if f.relative_path == "bom.py")
    assert file.text == 'x="é"\r\nsecond=2\r\n'
    assert file.byte_size == 21
    assert {"binary.py", "encoding.py", "empty.py", "long.py"} <= {
        f.relative_path for f in scan.skipped
    }


@pytest.mark.parametrize("limits", [{"max_files": 2}, {"max_total_bytes": 2}])
def test_total_limits_fail_instead_of_partial_index(source_root, tmp_path, limits):
    from repolens.config import Limits
    from repolens.repository import scan_repository
    from repolens.errors import RepoLensError

    with pytest.raises(RepoLensError) as caught:
        scan_repository(source_root, tmp_path / "data", replace(Limits(), **limits))
    assert caught.value.code == "limit_exceeded"


def test_overlap_and_unexpected_read_failure(source_root, tmp_path, monkeypatch):
    from repolens.config import Limits
    from repolens.repository import scan_repository
    from repolens.errors import RepoLensError

    with pytest.raises(RepoLensError):
        scan_repository(source_root, source_root / "data", Limits())
    read = Path.open

    def broken(path, *args, **kwargs):
        if path.name == "app.py":
            raise PermissionError("denied")
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken)
    with pytest.raises(RepoLensError, match="read"):
        scan_repository(source_root, tmp_path / "data", Limits())


def test_invalid_ignore_file_has_safe_read_error(source_root, tmp_path):
    from repolens.repository import scan_repository
    from repolens.config import Limits
    from repolens.errors import RepoLensError

    (source_root / ".gitignore").write_bytes(b"\xff")
    with pytest.raises(RepoLensError, match="read"):
        scan_repository(source_root, tmp_path / "data", Limits())


def test_file_growth_is_bounded_during_read(source_root, tmp_path, monkeypatch):
    import io
    from repolens.repository import scan_repository
    from repolens.config import Limits

    original = Path.open
    reads = []

    class GrowingFile(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    def opened(path, *args, **kwargs):
        if path.name == "app.py" and args and args[0] == "rb":
            return GrowingFile(b"x" * 1000)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    scan = scan_repository(
        source_root, tmp_path / "data", replace(Limits(), max_file_bytes=64)
    )
    assert reads == [65]
    assert "app.py" not in {f.relative_path for f in scan.files}


@pytest.mark.skipif(not hasattr(__import__("os"), "mkfifo"), reason="POSIX FIFO only")
def test_fifo_is_skipped_without_blocking(tmp_path):
    import os, subprocess, sys

    root = tmp_path / "fifo-repo"
    root.mkdir()
    os.mkfifo(root / "pipe.py")
    code = "from pathlib import Path; from repolens.repository import scan_repository; from repolens.config import Limits; import sys; print(len(scan_repository(Path(sys.argv[1]),Path(sys.argv[2]),Limits()).files))"
    result = subprocess.run(
        [sys.executable, "-c", code, str(root), str(tmp_path / "data")],
        capture_output=True,
        text=True,
        timeout=2,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0"


def test_oversized_ignore_file_fails_without_partial_rules(source_root, tmp_path):
    from repolens.repository import scan_repository
    from repolens.config import Limits
    from repolens.errors import RepoLensError

    (source_root / ".gitignore").write_text("#" * (256 * 1024 + 1))
    with pytest.raises(RepoLensError) as caught:
        scan_repository(source_root, tmp_path / "data", Limits())
    assert caught.value.code == "limit_exceeded"
