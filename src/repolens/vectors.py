"""Qdrant local persistence, with external Ollama vectors and bounded handle lifetime."""

from contextlib import contextmanager
from math import isfinite
import sqlite3
from pathlib import Path
from qdrant_client import QdrantClient, models
from repolens.domain import SearchHit
from repolens.errors import RepoLensError


def validate_vector(vector: list[float], dimensions: int) -> None:
    """Reject unusable dimensions or coordinates before storing or searching."""
    if len(vector) != dimensions or not all(
        type(v) in (int, float) and isfinite(v) for v in vector
    ):
        raise RepoLensError(
            "model_incompatible",
            (
                "Embedding dimensions or coordinates are invalid. Select a "
                "compatible model and rebuild."
            ),
        )


@contextmanager
def local_client(directory: Path):
    """Release the Qdrant directory lock after each operation, even on errors."""
    client = None
    try:
        client = QdrantClient(path=str(directory))
        yield client
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        raise RepoLensError(
            "index_invalid",
            (
                "Cannot open vector index; another app may hold its lock. Close "
                "it, then retry or rebuild."
            ),
        ) from exc
    finally:
        if client is not None:
            client.close()


def write_vectors(
    directory: Path, dimensions: int, vectors: dict[int, list[float]]
) -> None:
    """Persist externally generated embeddings under the same IDs as SQLite."""
    if dimensions <= 0 or not vectors:
        raise RepoLensError("model_incompatible", "No usable embeddings were returned.")
    for vector in vectors.values():
        validate_vector(vector, dimensions)
    with local_client(directory) as client:
        client.create_collection(
            "snippets",
            vectors_config=models.VectorParams(
                size=dimensions, distance=models.Distance.COSINE
            ),
        )
        for start in range(0, len(vectors), 64):
            entries = list(vectors.items())[start : start + 64]
            client.upsert(
                "snippets",
                points=[models.PointStruct(id=i, vector=v) for i, v in entries],
            )


def search_vectors(
    directory: Path, vector: list[float], limit: int = 10
) -> tuple[SearchHit, ...]:
    """Search with the snapshot embedding dimensions and stable tie ordering."""
    with local_client(directory) as client:
        dimensions = client.get_collection("snippets").config.params.vectors.size
        validate_vector(vector, dimensions)
        points = client.query_points("snippets", query=vector, limit=limit).points
    # Qdrant's equal-score order is not a stable source ordering.
    points = sorted(points, key=lambda p: (-p.score, int(p.id)))
    return tuple(SearchHit(int(p.id), i + 1, p.score) for i, p in enumerate(points))


def vector_ids(directory: Path) -> frozenset[int]:
    """Read IDs without loading vectors for cross-store consistency checks."""
    with local_client(directory) as client:
        ids, offset = set(), None
        while True:
            points, offset = client.scroll(
                "snippets",
                limit=256,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            ids.update(int(p.id) for p in points)
            if offset is None:
                break
        return frozenset(ids)


def vector_dimensions(directory: Path) -> int:
    """Read the collection dimensions used to validate question embeddings."""
    with local_client(directory) as client:
        return client.get_collection("snippets").config.params.vectors.size
