def test_rrf_merges_ranks_with_stable_ties():
    from repolens.domain import SearchHit
    from repolens.retrieval import fuse

    lexical = (SearchHit(1, 1, -9), SearchHit(2, 2, -2), SearchHit(3, 3, -1))
    semantic = (SearchHit(2, 1, 0.9), SearchHit(4, 2, 0.8))
    assert [h.snippet_id for h in fuse(lexical, semantic)] == [2, 1, 4, 3]


def test_overlap_and_unicode_budget_preserve_whole_sources():
    from repolens.domain import SearchHit, Snippet, RetrievalResult
    from repolens.retrieval import select_evidence, render_sources

    snippets = {
        1: Snippet(1, "a.py", 1, 60, "é" * 20),
        2: Snippet(2, "a.py", 10, 60, "second"),
        3: Snippet(3, "b.py", 1, 1, "third"),
    }
    result = RetrievalResult(
        tuple(SearchHit(i, i, 1.0) for i in (1, 2, 3)), snippets, {}
    )
    selected = select_evidence(result, 1000)
    assert [s.snippet.id for s in selected] == [1, 3]
    assert [s.source_id for s in selected] == ["S1", "S2"]
    assert select_evidence(result, 1) == ()
    assert len(render_sources(select_evidence(result, 100)).encode()) <= 100


def test_empty_lexical_results_still_use_semantics_and_errors_do_not_fall_back(
    source_root, tmp_path
):
    import pytest
    from fakes import FakeOllama
    from repolens.config import Settings
    from repolens.indexing import build_index
    from repolens.lexical import search_lexical
    from repolens.retrieval import retrieve
    from repolens.errors import RepoLensError

    settings = Settings(data_dir=tmp_path / "data")
    fake = FakeOllama()
    snapshot = build_index(source_root, settings, fake)
    assert search_lexical(snapshot.directory / "index.sqlite", "zzzxxyy") == ()
    result = retrieve("zzzxxyy", snapshot, fake)
    assert result.hits
    assert set(result.snippets) == {1, 2, 3}

    def unavailable(texts, model):
        raise RepoLensError("model_unavailable", "Embedding service unavailable")

    fake.embed = unavailable
    with pytest.raises(RepoLensError) as caught:
        retrieve("hello", snapshot, fake)
    assert caught.value.code == "model_unavailable"
