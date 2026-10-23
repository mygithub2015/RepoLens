import sqlite3
import pytest


def test_missing_fts5_reports_actionable_error(monkeypatch):
    from repolens.config import check_fts5
    from repolens.errors import RepoLensError

    original = sqlite3.connect

    class MissingFTS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql):
            raise sqlite3.OperationalError("no such module: fts5")

    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: MissingFTS())
    with pytest.raises(RepoLensError, match="FTS5"):
        check_fts5()
