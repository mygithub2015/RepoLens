"""Read bounded, eligible text without importing or executing repository code."""

from fnmatch import fnmatchcase
from hashlib import sha256
from pathlib import Path
import pathspec
import stat
from repolens.chunking import source_lines
from repolens.config import Limits
from repolens.domain import FileRecord, SkippedFile, ScanResult
from repolens.errors import RepoLensError

EXTENSIONS = set(
    (
        ".py .java .js .jsx .ts .tsx .go .rs .c .h .cpp .hpp .cs .kt .rb "
        ".php .scala .sh .sql .html .css .md .rst .txt .json .toml .yaml "
        ".yml .xml .ini .cfg .properties"
    ).split()
)
NAMES = {"readme", "license", "makefile", "dockerfile"}
EXCLUDED = set(
    ".git .venv venv node_modules vendor __pycache__ build dist target coverage .coverage".split()
)
PATTERNS = (
    "*.min.js *.min.css *.map package-lock.json yarn.lock "
    "pnpm-lock.yaml poetry.lock uv.lock cargo.lock pipfile.lock .env "
    ".env.* *.pem *.key *.p12 *.pfx id_rsa id_ed25519 credentials.* "
    "secrets.*"
).split()


def scan_repository(root: Path, data_dir: Path, limits: Limits) -> ScanResult:
    """Capture eligible text and fingerprints, reporting exclusions explicitly."""
    root, data_dir = root.expanduser().resolve(), data_dir.expanduser().resolve()
    if not root.is_dir():
        raise RepoLensError("invalid_input", "Select an existing repository folder.")
    if root == data_dir or root in data_dir.parents or data_dir in root.parents:
        raise RepoLensError(
            "invalid_input", "Repository and RepoLens data directory must not overlap."
        )
    files, skipped = [], []
    total = 0

    def skip(path, reason):
        skipped.append(SkippedFile(path.relative_to(root).as_posix(), reason))

    def walk(directory, rules):
        nonlocal total
        ignore = directory / ".gitignore"
        if ignore.is_file() and not ignore.is_symlink():
            with ignore.open("rb") as stream:
                ignore_bytes = stream.read(limits.max_file_bytes + 1)
            if len(ignore_bytes) > limits.max_file_bytes:
                raise RepoLensError(
                    "limit_exceeded",
                    (
                        "A .gitignore exceeds the file byte limit. Select a smaller "
                        "folder or reduce that ignore file."
                    ),
                )
            rules = rules + [
                (
                    directory,
                    pathspec.GitIgnoreSpec.from_lines(
                        ignore_bytes.decode("utf-8-sig").splitlines()
                    ),
                )
            ]
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            name = path.name.lower()
            if path.is_symlink():
                skip(path, "symlink")
                continue
            # Hard exclusions win before nested ignore negations are considered.
            if name in EXCLUDED or any(
                fnmatchcase(name, pattern) for pattern in PATTERNS
            ):
                skip(path, "excluded")
                continue
            is_dir = path.is_dir()
            ignored = False
            for base, spec in rules:
                match = spec.check_file(
                    path.relative_to(base).as_posix() + ("/" if is_dir else "")
                )
                if match.include is not None:
                    ignored = match.include
            if ignored:
                skip(path, "gitignore")
                continue
            if is_dir:
                walk(path, rules)
                continue
            if not stat.S_ISREG(path.stat().st_mode):
                skip(path, "not a regular file")
                continue
            if path.suffix.lower() not in EXTENSIONS and name not in NAMES:
                skip(path, "unsupported file type")
                continue
            if path.stat().st_size > limits.max_file_bytes:
                skip(path, "file exceeds byte limit")
                continue
            # Bound the read too: the file may grow after the earlier size check.
            with path.open("rb") as stream:
                raw = stream.read(limits.max_file_bytes + 1)
            if len(raw) > limits.max_file_bytes:
                skip(path, "file exceeds byte limit")
                continue
            if not raw or b"\x00" in raw:
                skip(path, "empty or binary")
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                skip(path, "unsupported encoding")
                continue
            if not text or any(
                len(line) > limits.chunk_chars for line in source_lines(text)
            ):
                skip(path, "empty or line exceeds character limit")
                continue
            total += len(raw)
            files.append(
                FileRecord(
                    path.relative_to(root).as_posix(),
                    sha256(raw).hexdigest(),
                    len(raw),
                    text,
                )
            )
            if len(files) > limits.max_files or total > limits.max_total_bytes:
                raise RepoLensError(
                    "limit_exceeded",
                    "Repository exceeds indexing limits. Select a smaller folder.",
                )

    try:
        walk(root, [])
    except (OSError, UnicodeError) as exc:
        raise RepoLensError(
            "build_failed",
            "Cannot read repository files. Check permissions and retry after edits settle.",
        ) from exc
    return ScanResult(
        root, tuple(sorted(files, key=lambda f: f.relative_path)), tuple(skipped)
    )
