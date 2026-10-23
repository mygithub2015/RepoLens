import pytest


def test_identifiers_and_components_retrieve_original_snippets(tmp_path):
    from repolens.domain import Snippet
    from repolens.lexical import (
        write_lexical_index,
        search_lexical,
        load_snippets,
        lexical_ids,
    )

    db = tmp_path / "index.sqlite"
    snippets = (
        Snippet(
            1, "retry.py", 1, 2, "def is_retryable(code):\n    return code == 503\n"
        ),
        Snippet(2, "client.js", 1, 1, "function fetchUser() {}\n"),
    )
    write_lexical_index(db, snippets)
    assert search_lexical(db, "is_retryable")[0].snippet_id == 1
    assert search_lexical(db, "fetch user")[0].snippet_id == 2
    assert search_lexical(db, "retry.py")[0].snippet_id == 1
    assert load_snippets(db, (1,))[1] == snippets[0]
    assert lexical_ids(db) == frozenset({1, 2})
    assert search_lexical(db, '! " * ()') == ()
    assert isinstance(search_lexical(db, '" OR ( fetch* :'), tuple)


def test_bm25_order_and_stable_ties(tmp_path):
    from repolens.domain import Snippet
    from repolens.lexical import write_lexical_index, search_lexical

    db = tmp_path / "index.sqlite"
    write_lexical_index(
        db, (Snippet(2, "b.py", 1, 1, "unique\n"), Snippet(1, "a.py", 1, 1, "unique\n"))
    )
    hits = search_lexical(db, "unique")
    assert [h.snippet_id for h in hits] == [1, 2]
    assert hits[0].score <= hits[1].score
