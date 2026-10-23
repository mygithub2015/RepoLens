"""Immutable records shared by the UI and testable application services."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """Capabilities and digest identify what an installed model can safely do."""

    name: str
    digest: str
    capabilities: frozenset[str]
    context_length: int | None
    is_local: bool


from pathlib import Path


@dataclass(frozen=True)
class FileRecord:
    relative_path: str
    digest: str
    byte_size: int
    text: str


@dataclass(frozen=True)
class SkippedFile:
    relative_path: str
    reason: str


@dataclass(frozen=True)
class ScanResult:
    root: Path
    files: tuple[FileRecord, ...]
    skipped: tuple[SkippedFile, ...]


@dataclass(frozen=True)
class Snippet:
    """Original text and line locations; the ID is unique within one snapshot."""

    id: int
    relative_path: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    """Rank drives fusion; branch-specific scores are diagnostic only."""

    snippet_id: int
    rank: int
    score: float


@dataclass(frozen=True)
class SnapshotManifest:
    """Bind stores, source fingerprints, and embedding identity to one build."""

    build_id: str
    repository_id: str
    source_root: str
    embedding_model: str
    embedding_digest: str
    dimensions: int
    snippet_count: int
    file_hashes: dict[str, str]
    schema_version: int
    filter_version: int
    chunker_version: int
    created_at: str
    limits: dict[str, int]
    store_hashes: dict[str, str]
    skipped: tuple[SkippedFile, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    directory: Path
    manifest: SnapshotManifest


@dataclass(frozen=True)
class IndexStatus:
    state: str
    snapshot: Snapshot | None
    reason: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    hits: tuple[SearchHit, ...]
    snippets: dict[int, Snippet]
    timings: dict[str, float]


@dataclass(frozen=True)
class EvidenceSource:
    """A question-local citation ID paired with its authoritative snippet."""

    source_id: str
    snippet: Snippet


@dataclass(frozen=True)
class ChatReply:
    content: str
    done_reason: str


@dataclass(frozen=True)
class AnswerResult:
    """Validated answer data ready for display with original source evidence."""

    answer: str
    sources: tuple[EvidenceSource, ...]
    insufficient_evidence: bool
    answer_model: ModelInfo
    timings: dict[str, float]
