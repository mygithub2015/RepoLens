from dataclasses import replace
import pytest


def test_whole_lines_and_overlap_preserve_references():
    from repolens.domain import FileRecord
    from repolens.config import Limits
    from repolens.chunking import chunk_files

    text = "".join(f"{n}\r\n" for n in range(1, 121))
    chunks = chunk_files((FileRecord("a.py", "digest", len(text), text),), Limits())
    assert [(s.start_line, s.end_line) for s in chunks] == [
        (1, 60),
        (51, 110),
        (101, 120),
    ]
    assert chunks[1].text.startswith("51\r\n")
    assert chunks[2].text.endswith("120\r\n")


def test_character_cap_always_advances_and_snippet_limit_fails():
    from repolens.domain import FileRecord
    from repolens.config import Limits
    from repolens.chunking import chunk_files
    from repolens.errors import RepoLensError

    files = (FileRecord("a.py", "digest", 6000, ("x" * 999 + "\n") * 6),)
    chunks = chunk_files(files, Limits())
    assert chunks[-1].end_line == 6
    assert all(len(c.text) <= 4000 for c in chunks)
    with pytest.raises(RepoLensError):
        chunk_files(files, replace(Limits(), max_snippets=1))


@pytest.mark.parametrize("separator", ["\u2028", "\u0085", "\f"])
def test_unicode_in_source_string_is_not_a_physical_newline(separator):
    from repolens.domain import FileRecord
    from repolens.config import Limits
    from repolens.chunking import chunk_files

    text = f'x="a{separator}b"\ny=2\n'
    snippets = chunk_files(
        (FileRecord("a.py", "digest", len(text.encode()), text),), Limits()
    )
    assert [(s.start_line, s.end_line, s.text) for s in snippets] == [(1, 2, text)]
