"""Local configuration; no model downloads or global package changes."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from repolens.errors import RepoLensError

SCHEMA_VERSION = FILTER_VERSION = CHUNKER_VERSION = 1


@dataclass(frozen=True)
class Limits:
    """Capacity bounds shared by repository reading and whole-line chunking."""

    max_files: int = 500
    max_total_bytes: int = 5 * 1024 * 1024
    max_file_bytes: int = 256 * 1024
    max_snippets: int = 2000
    chunk_lines: int = 60
    chunk_chars: int = 4000
    overlap_lines: int = 10


@dataclass(frozen=True)
class Settings:
    """Keep answer-model preferences separate from embedding-model configuration."""

    data_dir: Path
    ollama_url: str = "http://127.0.0.1:11434"
    answer_model: str = "qwen3.5:4b"
    embedding_model: str = "qwen3-embedding:0.6b"
    limits: Limits = Limits()


def load_settings() -> Settings:
    """Load local model preferences while retaining approved defaults."""
    data_dir = (
        Path(os.environ.get("REPOLENS_DATA_DIR", "~/.repolens")).expanduser().resolve()
    )
    saved = data_dir / "settings.json"
    try:
        preferences = json.loads(saved.read_text()) if saved.exists() else {}
        if not isinstance(preferences, dict) or any(
            not isinstance(v, str) for v in preferences.values()
        ):
            raise ValueError("invalid preferences")
        return Settings(
            data_dir=data_dir,
            **{
                k: preferences[k]
                for k in ("answer_model", "embedding_model")
                if k in preferences
            },
        )
    except (OSError, ValueError, TypeError) as exc:
        raise RepoLensError(
            "invalid_input",
            "Cannot read settings.json. Repair or remove that local settings file.",
        ) from exc


def save_model_preferences(settings: Settings) -> None:
    """Replace the local preferences file only after its new contents are written."""
    temporary = settings.data_dir / f"settings.{uuid4()}.tmp"
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(
                {
                    "answer_model": settings.answer_model,
                    "embedding_model": settings.embedding_model,
                }
            )
        )
        temporary.replace(settings.data_dir / "settings.json")
    except OSError as exc:
        raise RepoLensError(
            "invalid_input",
            "Cannot save model settings. Check the data directory permissions.",
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def check_fts5() -> None:
    """Fail early if this Python SQLite cannot provide lexical search."""
    try:
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    except sqlite3.Error as exc:
        raise RepoLensError(
            "invalid_input",
            "This Python SQLite lacks FTS5. Install a Python build with SQLite FTS5 enabled.",
        ) from exc
