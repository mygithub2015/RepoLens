import json
import subprocess
import sys
import pytest


def test_vectors_reopen_in_separate_process(tmp_path):
    from repolens.vectors import write_vectors, search_vectors, vector_ids

    directory = tmp_path / "qdrant"
    vectors = {
        1: [1.0, 0.0] + [0.0] * 1022,
        2: [0.8, 0.2] + [0.0] * 1022,
        3: [0.0, 1.0] + [0.0] * 1022,
    }
    write_vectors(directory, 1024, vectors)
    assert vector_ids(directory) == frozenset({1, 2, 3})
    assert [h.snippet_id for h in search_vectors(directory, vectors[1])] == [1, 2, 3]
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            'from repolens.vectors import vector_ids; import sys; print(sorted(vector_ids(__import__("pathlib").Path(sys.argv[1]))))',
            str(directory),
        ],
        text=True,
    )
    assert json.loads(output) == [1, 2, 3]


def test_vector_dimension_and_lock_errors_are_actionable(tmp_path):
    from qdrant_client import QdrantClient
    from repolens.errors import RepoLensError
    from repolens.vectors import write_vectors, search_vectors

    path = tmp_path / "qdrant"
    write_vectors(path, 2, {1: [1.0, 0.0]})
    with pytest.raises(RepoLensError):
        search_vectors(path, [1.0, 0.0, 0.0])
    with pytest.raises(RepoLensError):
        write_vectors(tmp_path / "bad", 2, {1: [float("nan"), 0.0]})
    client = QdrantClient(path=str(path))
    try:
        with pytest.raises(RepoLensError, match="lock|another"):
            search_vectors(path, [1.0, 0.0])
    finally:
        client.close()


def test_corrupt_vector_database_has_actionable_error(tmp_path):
    from repolens.vectors import write_vectors, search_vectors
    from repolens.errors import RepoLensError

    path = tmp_path / "qdrant"
    write_vectors(path, 2, {1: [1.0, 0.0]})
    (path / "collection/snippets/storage.sqlite").write_bytes(b"not sqlite")
    with pytest.raises(RepoLensError):
        search_vectors(path, [1.0, 0.0])
