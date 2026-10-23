"""Run both searches, merge ranks, and retain bounded original snippets."""

import json
from time import perf_counter
from repolens.domain import Snapshot, SearchHit, RetrievalResult, EvidenceSource
from repolens.errors import RepoLensError
from repolens.lexical import search_lexical, load_snippets
from repolens.vectors import search_vectors, validate_vector
from repolens.ollama import OllamaGateway


def fuse(
    lexical: tuple[SearchHit, ...], semantic: tuple[SearchHit, ...], constant: int = 60
) -> tuple[SearchHit, ...]:
    """Combine branch ranks with RRF instead of adding incompatible raw scores."""
    # A snippet returned by both branches gains two rank-based contributions.
    # Missing branch entries contribute nothing; score scales never mix.
    scores = {}
    for branch in (lexical, semantic):
        for hit in branch:
            scores[hit.snippet_id] = scores.get(hit.snippet_id, 0) + 1 / (
                constant + hit.rank
            )
    ordered = sorted(scores, key=lambda i: (-scores[i], i))
    return tuple(SearchHit(id, i + 1, scores[id]) for i, id in enumerate(ordered))


def retrieve(
    question: str, snapshot: Snapshot, ollama: OllamaGateway
) -> RetrievalResult:
    """Run both retrieval branches and load their canonical SQLite snippets."""
    timings = {}
    start = perf_counter()
    lexical = search_lexical(snapshot.directory / "index.sqlite", question)
    timings["lexical_seconds"] = perf_counter() - start
    start = perf_counter()
    # The question must use the exact embedding model that built this snapshot.
    vectors = ollama.embed((question,), snapshot.manifest.embedding_model)
    if len(vectors) != 1:
        raise RepoLensError(
            "model_incompatible", "No usable question embedding was returned."
        )
    validate_vector(vectors[0], snapshot.manifest.dimensions)
    semantic = search_vectors(snapshot.directory / "qdrant", vectors[0])
    timings["semantic_seconds"] = perf_counter() - start
    # Empty lexical results are valid; branch failures are not silent fallbacks.
    hits = fuse(lexical, semantic)
    snippets = load_snippets(
        snapshot.directory / "index.sqlite", tuple(h.snippet_id for h in hits)
    )
    if len(snippets) != len(hits):
        raise RepoLensError(
            "index_invalid", "Retrieved source IDs are missing. Rebuild the index."
        )
    return RetrievalResult(hits, snippets, timings)


def render_sources(sources: tuple[EvidenceSource, ...]) -> str:
    """Serialize selected evidence as data with application-owned source IDs."""
    return json.dumps(
        [
            {
                "source_id": s.source_id,
                "path": s.snippet.relative_path,
                "start_line": s.snippet.start_line,
                "end_line": s.snippet.end_line,
                "text": s.snippet.text,
            }
            for s in sources
        ],
        ensure_ascii=False,
    )


def select_evidence(
    result: RetrievalResult, budget_bytes: int
) -> tuple[EvidenceSource, ...]:
    """Keep whole, sufficiently distinct snippets within the prompt byte budget."""
    selected = []
    for hit in result.hits:
        snippet = result.snippets[hit.snippet_id]
        overlaps = False
        for source in selected:
            other = source.snippet
            overlap = max(
                0,
                min(snippet.end_line, other.end_line)
                - max(snippet.start_line, other.start_line)
                + 1,
            )
            if (
                snippet.relative_path == other.relative_path
                and overlap
                > min(
                    snippet.end_line - snippet.start_line + 1,
                    other.end_line - other.start_line + 1,
                )
                / 2
            ):
                overlaps = True
                break
        if overlaps:
            continue
        # Assign citation IDs only after overlap filtering, then keep the entire
        # snippet or skip it; never shorten text while claiming its original range.
        candidate = tuple(selected + [EvidenceSource(f"S{len(selected) + 1}", snippet)])
        if len(render_sources(candidate).encode("utf-8")) <= budget_bytes:
            selected = list(candidate)
        if len(selected) == 4:
            break
    return tuple(selected)
