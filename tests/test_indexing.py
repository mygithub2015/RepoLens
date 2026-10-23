from dataclasses import replace
import json
from pathlib import Path
import pytest
from fakes import FakeOllama


@pytest.fixture
def setup_index(source_root, tmp_path):
    from repolens.config import Settings
    from repolens.indexing import build_index

    settings = Settings(data_dir=tmp_path / "data")
    fake = FakeOllama()
    snapshot = build_index(source_root, settings, fake)
    return source_root, settings, fake, snapshot


def test_failed_rebuild_preserves_previous_snapshot(setup_index):
    from repolens.indexing import build_index, load_active, index_status
    from repolens.errors import RepoLensError

    root, settings, fake, previous = setup_index
    fake.fail_embed = True
    with pytest.raises(RepoLensError):
        build_index(root, settings, fake)
    assert (
        load_active(root, settings.data_dir).manifest.build_id
        == previous.manifest.build_id
    )
    assert index_status(root, settings, fake).state == "ready"


@pytest.mark.parametrize(
    "change", ["edit", "add", "delete", "rename", "digest", "model"]
)
def test_changes_require_rebuild(setup_index, change):
    from repolens.indexing import index_status

    root, settings, fake, snapshot = setup_index
    if change == "edit":
        (root / "app.py").write_text("changed=1\n")
    if change == "add":
        (root / "new.py").write_text("new=1\n")
    if change == "delete":
        (root / "app.py").unlink()
    if change == "rename":
        (root / "app.py").rename(root / "renamed.py")
    if change == "digest":
        fake.digest = "embedding-v2"
    if change == "model":
        settings = replace(settings, embedding_model="another-embedding")
    assert index_status(root, settings, fake).state == "stale"


def test_sources_changed_during_build_are_not_published(setup_index):
    from repolens.indexing import build_index, load_active
    from repolens.errors import RepoLensError

    root, settings, fake, previous = setup_index
    fake.on_embed = lambda: (root / "app.py").write_text("changed=1")
    with pytest.raises(RepoLensError):
        build_index(root, settings, fake)
    assert (
        load_active(root, settings.data_dir).manifest.build_id
        == previous.manifest.build_id
    )


@pytest.mark.parametrize(
    "breakage", ["pointer", "manifest", "sqlite", "vectors", "ids"]
)
def test_corrupt_active_snapshot_is_failed_not_missing(setup_index, breakage):
    from repolens.indexing import index_status

    root, settings, fake, snapshot = setup_index
    if breakage == "pointer":
        (snapshot.directory.parent.parent / "active.json").write_text(
            '{"build_id":"../escape"}'
        )
    if breakage == "manifest":
        (snapshot.directory / "manifest.json").write_text("{}")
    if breakage == "sqlite":
        (snapshot.directory / "index.sqlite").unlink()
    if breakage == "vectors":
        __import__("shutil").rmtree(snapshot.directory / "qdrant")
    if breakage == "ids":
        import sqlite3

        with sqlite3.connect(snapshot.directory / "index.sqlite") as db:
            db.execute("DELETE FROM snippets WHERE id=1")
    assert index_status(root, settings, fake).state == "failed"


def test_publication_failure_and_restart_do_not_mix_stores(setup_index, monkeypatch):
    from repolens.indexing import build_index, load_active
    from repolens.lexical import lexical_ids
    from repolens.vectors import vector_ids
    from repolens.errors import RepoLensError

    root, settings, fake, previous = setup_index
    original = Path.replace

    def fail_pointer(path, target):
        if Path(target).name == "active.json":
            raise OSError("injected publication failure")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", fail_pointer)
    with pytest.raises(RepoLensError):
        build_index(root, settings, fake)
    active = load_active(root, settings.data_dir)
    assert active.manifest.build_id == previous.manifest.build_id
    assert lexical_ids(active.directory / "index.sqlite") == vector_ids(
        active.directory / "qdrant"
    )
    other = root.parent / "other"
    other.mkdir()
    assert load_active(other, settings.data_dir) is None


def test_same_id_store_substitution_is_not_fresh(setup_index):
    import shutil
    from repolens.indexing import build_index, index_status

    root, settings, fake, previous = setup_index
    (root / "app.py").write_text("new_source=2\n")
    current = build_index(root, settings, fake)
    shutil.copyfile(
        previous.directory / "index.sqlite", current.directory / "index.sqlite"
    )
    assert index_status(root, settings, fake).state == "failed"


def test_corrupt_qdrant_database_is_recoverable(setup_index):
    from repolens.indexing import build_index, index_status

    root, settings, fake, snapshot = setup_index
    storage = snapshot.directory / "qdrant/collection/snippets/storage.sqlite"
    storage.write_bytes(b"not a sqlite database")
    assert index_status(root, settings, fake).state == "failed"
    build_index(root, settings, fake)
    assert index_status(root, settings, fake).state == "ready"


def test_same_id_vector_change_breaks_snapshot_integrity(setup_index):
    from qdrant_client import QdrantClient, models
    from repolens.indexing import index_status

    root, settings, fake, snapshot = setup_index
    client = QdrantClient(path=str(snapshot.directory / "qdrant"))
    try:
        client.upsert(
            "snippets", points=[models.PointStruct(id=1, vector=[1.0] + [0.0] * 7)]
        )
    finally:
        client.close()
    assert index_status(root, settings, fake).state == "failed"
