"""SQLite owns original text; the separate FTS representation normalizes identifiers."""

from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
from repolens.domain import Snippet, SearchHit
from repolens.errors import RepoLensError


def terms(text: str) -> tuple[str, ...]:
    """Retain whole identifiers and add their snake/camel-case components."""
    split = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    split = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", split).replace("_", " ")
    return tuple(
        dict.fromkeys(
            re.findall(r"\w+", text.lower()) + re.findall(r"\w+", split.lower())
        )
    )


@contextmanager
def connection(path: Path, write: bool = False):
    """Close connections within each operation, including Streamlit reruns."""
    db = None
    try:
        db = sqlite3.connect(
            str(path) if write else path.resolve().as_uri() + "?mode=ro", uri=not write
        )
        yield db
        if write:
            db.commit()
    except sqlite3.Error as exc:
        raise RepoLensError(
            "index_invalid",
            "Cannot read or write the snippet index. Close other app instances and rebuild.",
        ) from exc
    finally:
        if db:
            db.close()


def write_lexical_index(db_path: Path, snippets: tuple[Snippet, ...]) -> None:
    """Store canonical source text separately from its searchable representation."""
    with connection(db_path, True) as db:
        db.execute(
            (
                "CREATE TABLE snippets(id INTEGER PRIMARY KEY, relative_path "
                "TEXT, start_line INTEGER, end_line INTEGER, text TEXT)"
            )
        )
        db.execute(
            (
                "CREATE VIRTUAL TABLE search USING fts5(representation, "
                'tokenize="unicode61 tokenchars _")'
            )
        )
        for s in snippets:
            db.execute(
                "INSERT INTO snippets VALUES (?, ?, ?, ?, ?)",
                (s.id, s.relative_path, s.start_line, s.end_line, s.text),
            )
            db.execute(
                "INSERT INTO search(rowid, representation) VALUES (?,?)",
                (s.id, " ".join(terms(s.relative_path + " " + s.text))),
            )


def search_lexical(
    db_path: Path, question: str, limit: int = 10
) -> tuple[SearchHit, ...]:
    """Turn plain questions into safe FTS terms and return ranked snippet IDs."""
    # Treat user text as literal terms, not executable FTS query syntax.
    query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms(question))
    if not query:
        return ()
    with connection(db_path) as db:
        # SQLite BM25 ranks smaller scores first, unlike cosine similarity.
        rows = db.execute(
            (
                "SELECT rowid, bm25(search) AS score FROM search WHERE search "
                "MATCH ? ORDER BY score, rowid LIMIT ?"
            ),
            (query, limit),
        ).fetchall()
    return tuple(SearchHit(row[0], i + 1, row[1]) for i, row in enumerate(rows))


def load_snippets(db_path: Path, ids: tuple[int, ...]) -> dict[int, Snippet]:
    """Resolve retrieved IDs back to the original text and file locations."""
    if not ids:
        return {}
    with connection(db_path) as db:
        rows = db.execute(
            "SELECT * FROM snippets WHERE id IN (" + ",".join("?" for _ in ids) + ")",
            ids,
        ).fetchall()
    return {row[0]: Snippet(*row) for row in rows}


def lexical_ids(db_path: Path) -> frozenset[int]:
    """Return snippet IDs for validation against the matching vector store."""
    with connection(db_path) as db:
        return frozenset(row[0] for row in db.execute("SELECT id FROM snippets"))
