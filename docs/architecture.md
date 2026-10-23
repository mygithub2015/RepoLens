# Architecture

RepoLens is a single-user local application for independent questions about a
repository. Streamlit displays controls and evidence. Ollama runs the embedding
and answer models. SQLite and Qdrant persist a matching index on the same computer.

## Indexing

1. Resolve the selected local folder and scan eligible UTF-8 files without executing
   repository code or following symlinks. Apply hard exclusions and nested Git ignores.
2. Split each file into whole-line snippets: up to 60 lines or 4,000 characters,
   with up to 10 overlapping lines. Preserve original text and inclusive line ranges.
3. Generate embeddings through Ollama in batches of 16, without silent truncation.
4. Store authoritative snippets and the FTS5 lexical index in SQLite; persist vectors
   in Qdrant local mode under the same integer snippet IDs.
5. Validate both stores, source fingerprints and embedding identity, then publish
   the new build by replacing one active pointer.

The default limits are 500 eligible files, 5 MiB total eligible bytes, 256 KiB per
file, and 2,000 snippets. Total-limit failures require choosing a smaller folder.
Individual unsupported files are reported as skipped. Filename exclusions are
not a general-purpose secret detector.

## Local snapshots

Each resolved repository path gets a SHA-256 identifier under `~/.repolens/indexes/`.
`REPOLENS_DATA_DIR` can select another data directory outside the source tree.

```text
indexes/<repository-id>/
  active.json
  snapshots/<build-id>/
    index.sqlite
    qdrant/
    manifest.json
```

A snapshot contains SQLite snippets/FTS5, Qdrant vectors, and a manifest describing
the source hashes, embedding model name/digest, dimensions, limits and store hashes.
It does not copy Git history. SQLite and Qdrant manage their own underlying files;
there is no application-managed `embeddings.npy` file or separate database server.

A rebuild writes an inactive snapshot. Only a complete, validated SQLite/Qdrant pair
becomes active. Normal failures clean up the incomplete build and retain the prior
pointer. A successful build keeps itself and the previous valid snapshot. Retention
does not automatically roll back to an old snapshot or permit answers from stale data.
Moving a repository or using another clone path creates a different index namespace.

## Questions and evidence

Both retrieval branches run for every question. SQLite FTS5/BM25 and Qdrant cosine
search each return up to ten snippet IDs. Reciprocal rank fusion combines their
positions with `sum(1 / (60 + rank))`; raw lexical and vector scores are not mixed.

Select up to four whole snippets within a conservative UTF-8 byte budget, suppressing
large same-file overlaps. Assign question-local source IDs such as `S1`, then ask
the local answer model for structured JSON using only the selected evidence.

Validate fields, source IDs, inline citations and completion status. Display the
answer as plain text and expand original source text with original line numbers.
These checks establish structural validity, not factual entailment: a valid source
ID can still refer to a snippet that does not support a claim. Users must inspect it.

## Freshness and UI state

Source fingerprints and embedding/index configuration are checked on UI interactions
and before/after answering. Source changes, embedding name/digest changes or relevant
configuration changes require an explicit rebuild. An answer-model change clears
the displayed answer but reuses a fresh index. No watcher, incremental build or
automatic retry runs in the background.

The two-column screen separates ingestion from questions/results and stacks on narrow
screens. Browse uses the local desktop chooser to obtain an absolute directory path;
it is not a browser upload. Cancellation preserves the selection and answer. A
collapsed manual-path fallback supports machines without a desktop chooser. The app
serializes operations within one process; run one process per data directory.

## Code map

| Module | Responsibility |
| --- | --- |
| `ui.py`, `ui_style.py` | Widgets, presentation and session state |
| `folder_picker.py` | Bounded native directory selection |
| `controller.py`, `config.py` | Service orchestration and local model preferences |
| `repository.py`, `chunking.py` | Bounded source reading and original-line snippets |
| `indexing.py` | Snapshot publication, validation and freshness |
| `lexical.py`, `vectors.py` | SQLite lexical search and Qdrant local vectors |
| `retrieval.py` | Rank fusion and bounded evidence selection |
| `answering.py`, `ollama.py` | Evidence prompt, response validation and model HTTP calls |
| `evaluation.py` | Fixed-question retrieval comparison and review records |

Authentication, hosted service deployment, multiple users, repository execution,
remote cloning in the app and compiler-level analysis are outside this version.
