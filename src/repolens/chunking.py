"""Deterministic whole-line chunks; line references always point to original text."""

import re
from repolens.config import Limits
from repolens.domain import FileRecord, Snippet
from repolens.errors import RepoLensError


def source_lines(text: str) -> list[str]:
    """Split physical LF, CRLF, or CR lines, retaining terminators and other Unicode."""
    return [
        match.group()
        for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)
        if match.group()
    ]


def chunk_files(files: tuple[FileRecord, ...], limits: Limits) -> tuple[Snippet, ...]:
    """Create bounded, overlapping snippets with original inclusive line ranges."""
    snippets = []
    for file in files:
        lines = source_lines(file.text)
        start = 0
        while start < len(lines):
            end, size = start, 0
            while (
                end < len(lines)
                and end - start < limits.chunk_lines
                and size + len(lines[end]) <= limits.chunk_chars
            ):
                size += len(lines[end])
                end += 1
            if end == start:
                raise RepoLensError(
                    "limit_exceeded", "A line exceeds the snippet size limit."
                )
            # List offsets are zero-based; displayed file references are one-based.
            snippets.append(
                Snippet(
                    len(snippets) + 1,
                    file.relative_path,
                    start + 1,
                    end,
                    "".join(lines[start:end]),
                )
            )
            if len(snippets) > limits.max_snippets:
                raise RepoLensError(
                    "limit_exceeded", "Too many snippets. Select a smaller folder."
                )
            if end == len(lines):
                break
            # Retain trailing context without getting stuck when a short chunk
            # contains fewer lines than the requested overlap.
            start = max(start + 1, end - limits.overlap_lines)
    return tuple(snippets)
