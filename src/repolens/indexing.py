"""Build complete snapshots, then publish one pointer. Source repositories are read-only."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
from threading import RLock
from uuid import UUID, uuid4

from repolens.config import Settings, SCHEMA_VERSION, FILTER_VERSION, CHUNKER_VERSION
from repolens.domain import Snapshot, SnapshotManifest, IndexStatus, SkippedFile
from repolens.errors import RepoLensError
from repolens.repository import scan_repository
from repolens.chunking import chunk_files
from repolens.lexical import write_lexical_index, lexical_ids
from repolens.vectors import (
    write_vectors,
    vector_ids,
    vector_dimensions,
    validate_vector,
)
from repolens.ollama import OllamaGateway

_LOCK = RLock()


@contextmanager
def operation():
    """Serialize nested build/query operations within this one app process."""
    if not _LOCK.acquire(blocking=False):
        raise RepoLensError(
            "operation_busy",
            "Another operation is running. Wait for it to finish, then retry.",
        )
    try:
        yield
    finally:
        _LOCK.release()


def repository_id(root: Path) -> str:
    """Give each resolved repository root its own index namespace."""
    return sha256(str(root.expanduser().resolve()).encode("utf-8")).hexdigest()


def _base(root: Path, data_dir: Path) -> Path:
    return data_dir / "indexes" / repository_id(root)


def _store_hashes(directory: Path) -> dict[str, str]:
    """Bind persistent store contents to their completed snapshot."""
    paths = [directory / "index.sqlite"] + sorted((directory / "qdrant").rglob("*"))
    result = {}
    for path in paths:
        if path.is_symlink():
            raise RepoLensError(
                "index_invalid",
                "Index storage must not contain symlinks. Rebuild the index.",
            )
        # A lock records current ownership, not immutable index contents.
        if path.is_file() and path.name != ".lock":
            digest = sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            result[path.relative_to(directory).as_posix()] = digest.hexdigest()
    return result


def _validate(snapshot: Snapshot) -> None:
    """Reject missing, altered, or mismatched stores before querying them."""
    manifest, directory = snapshot.manifest, snapshot.directory
    if (
        not (directory / "index.sqlite").is_file()
        or not (directory / "qdrant" / "meta.json").is_file()
    ):
        raise RepoLensError(
            "index_invalid", "Index files are missing. Rebuild this repository index."
        )
    if not manifest.store_hashes or _store_hashes(directory) != manifest.store_hashes:
        raise RepoLensError(
            "index_invalid", "Index storage changed or is corrupt. Rebuild the index."
        )
    ids = lexical_ids(directory / "index.sqlite")
    if (
        len(ids) != manifest.snippet_count
        or ids != vector_ids(directory / "qdrant")
        or vector_dimensions(directory / "qdrant") != manifest.dimensions
    ):
        raise RepoLensError(
            "index_invalid",
            "Snippet and vector stores do not match. Rebuild the index.",
        )


def load_active(root: Path, data_dir: Path) -> Snapshot | None:
    """Open only the completed snapshot named by the published pointer."""
    base = _base(root, data_dir)
    pointer = base / "active.json"
    if not pointer.exists():
        return None
    try:
        data = json.loads(pointer.read_text())
        if set(data) != {"build_id"}:
            raise ValueError("invalid pointer")
        build_id = str(UUID(data["build_id"]))
        if build_id != data["build_id"]:
            raise ValueError("noncanonical uuid")
        directory = base / "snapshots" / build_id
        raw = json.loads((directory / "manifest.json").read_text())
        raw["skipped"] = tuple(SkippedFile(**s) for s in raw.get("skipped", []))
        manifest = SnapshotManifest(**raw)
        if (
            manifest.build_id != build_id
            or manifest.repository_id != repository_id(root)
            or manifest.source_root != str(root.resolve())
        ):
            raise ValueError("wrong repository")
        snapshot = Snapshot(directory, manifest)
        _validate(snapshot)
        return snapshot
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RepoLensError(
            "index_invalid",
            "Saved index is unreadable or incomplete. Rebuild this repository index.",
        ) from exc


def _hashes(scan):
    return {f.relative_path: f.digest for f in scan.files}


def _embedding_model(settings, ollama):
    model = ollama.get_model(settings.embedding_model)
    if not model.is_local or "embedding" not in model.capabilities or not model.digest:
        raise RepoLensError(
            "model_incompatible",
            "Select a locally installed model with embedding capability.",
        )
    return model


def require_fresh(
    snapshot: Snapshot, settings: Settings, ollama: OllamaGateway
) -> None:
    """Require unchanged eligible files and embedding/index configuration."""
    manifest = snapshot.manifest
    scan = scan_repository(
        Path(manifest.source_root), settings.data_dir, settings.limits
    )
    model = _embedding_model(settings, ollama)
    if (
        _hashes(scan) != manifest.file_hashes
        or model.name != manifest.embedding_model
        or model.digest != manifest.embedding_digest
        or (manifest.schema_version, manifest.filter_version, manifest.chunker_version)
        != (SCHEMA_VERSION, FILTER_VERSION, CHUNKER_VERSION)
        or manifest.limits != asdict(settings.limits)
    ):
        raise RepoLensError(
            "index_stale",
            "Sources or embedding configuration changed. Rebuild the index before asking.",
        )


def index_status(root: Path, settings: Settings, ollama: OllamaGateway) -> IndexStatus:
    """Translate verification results into actionable states for the UI."""
    snapshot = None
    try:
        with operation():
            snapshot = load_active(root, settings.data_dir)
            if snapshot is None:
                return IndexStatus(
                    "missing", None, "Build an index to enable questions."
                )
            require_fresh(snapshot, settings, ollama)
            return IndexStatus("ready", snapshot)
    except RepoLensError as exc:
        return IndexStatus(
            "stale" if exc.code == "index_stale" else "failed", snapshot, str(exc)
        )


def build_index(root: Path, settings: Settings, ollama: OllamaGateway) -> Snapshot:
    """Build and verify both stores before atomically publishing a snapshot."""
    with operation():
        scan = scan_repository(root, settings.data_dir, settings.limits)
        model = _embedding_model(settings, ollama)
        snippets = chunk_files(scan.files, settings.limits)
        if not snippets:
            raise RepoLensError(
                "no_evidence",
                "No eligible source text. Select a folder with supported files.",
            )
        base = _base(scan.root, settings.data_dir)
        build_id = str(uuid4())
        directory = base / "snapshots" / build_id
        published = False
        try:
            previous = None
            if (base / "active.json").exists():
                try:
                    previous = load_active(scan.root, settings.data_dir)
                except RepoLensError:
                    pass  # A corrupt index must remain rebuildable.
            # This new directory is inactive: readers still use the old pointer.
            directory.mkdir(parents=True)
            vectors = {}
            for start in range(0, len(snippets), 16):
                batch = snippets[start : start + 16]
                result = ollama.embed(tuple(s.text for s in batch), model.name)
                if len(result) != len(batch):
                    raise ValueError("incomplete embeddings")
                for snippet, vector in zip(batch, result, strict=True):
                    vectors[snippet.id] = vector
            dimensions = len(next(iter(vectors.values())))
            for vector in vectors.values():
                validate_vector(vector, dimensions)
            # Both stores use the same snippet IDs, so retrieval can merge results
            # and resolve vector hits back to authoritative SQLite text.
            write_lexical_index(directory / "index.sqlite", snippets)
            write_vectors(directory / "qdrant", dimensions, vectors)
            manifest = SnapshotManifest(
                build_id,
                repository_id(scan.root),
                str(scan.root),
                model.name,
                model.digest,
                dimensions,
                len(snippets),
                _hashes(scan),
                SCHEMA_VERSION,
                FILTER_VERSION,
                CHUNKER_VERSION,
                datetime.now(timezone.utc).isoformat(),
                asdict(settings.limits),
                _store_hashes(directory),
                scan.skipped,
            )
            snapshot = Snapshot(directory, manifest)
            _validate(snapshot)
            # Reject edits or an embedding-tag digest change during the build.
            require_fresh(snapshot, settings, ollama)
            (directory / "manifest.json").write_text(
                json.dumps(asdict(manifest), ensure_ascii=False)
            )
            temporary = base / f"active.{build_id}.tmp"
            temporary.write_text(json.dumps({"build_id": build_id}))
            # Same-directory replacement publishes the complete pair at once.
            # Until this succeeds, the previous snapshot remains active.
            temporary.replace(base / "active.json")
            published = True
            # Retention runs only after publication, never against source files.
            keep = {build_id, previous.manifest.build_id if previous else ""}
            for old in directory.parent.iterdir():
                if old.name not in keep and old.is_dir() and not old.is_symlink():
                    try:
                        UUID(old.name)
                    except ValueError:
                        continue
                    shutil.rmtree(old, ignore_errors=True)
            return snapshot
        except RepoLensError:
            raise
        except (OSError, ValueError, RuntimeError) as exc:
            raise RepoLensError(
                "build_failed",
                (
                    "Index build failed. The previous index was retained. Fix the "
                    "cause and retry a full rebuild."
                ),
            ) from exc
        finally:
            if not published:
                shutil.rmtree(directory, ignore_errors=True)
            (base / f"active.{build_id}.tmp").unlink(missing_ok=True)
