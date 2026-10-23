"""Small reproducible benchmark; human source review determines answer quality."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter
from repolens.config import Settings, load_settings
from repolens.domain import RetrievalResult
from repolens.errors import RepoLensError
from repolens.indexing import build_index, require_fresh
from repolens.lexical import search_lexical, load_snippets
from repolens.vectors import search_vectors
from repolens.retrieval import fuse, select_evidence
from repolens.answering import answer_question, SYSTEM
from repolens.ollama import OllamaGateway, OllamaClient


def run_evaluation(
    root: Path,
    settings: Settings,
    ollama: OllamaGateway,
    questions_path: Path,
    output_dir: Path,
    corpus_revision: str | None = None,
) -> Path:
    """Compare retrieval on fixed questions and preserve answers for source review."""
    questions = json.loads(questions_path.read_text())
    if not isinstance(questions, list) or len({q["id"] for q in questions}) != len(
        questions
    ):
        raise RepoLensError("invalid_input", "Evaluation question IDs must be unique.")
    output_dir.mkdir(parents=True, exist_ok=False)
    snapshot = build_index(root, settings, ollama)
    answer_model = ollama.get_model(settings.answer_model)

    def model_record(model):
        return {
            "name": model.name,
            "digest": model.digest,
            "capabilities": sorted(model.capabilities),
            "context_length": model.context_length,
        }

    report = {
        "corpus_revision": corpus_revision,
        "answerable_count": sum(q["expected_path"] is not None for q in questions),
        "unanswerable_count": sum(q["expected_path"] is None for q in questions),
        "retrieval_modes": {
            m: {"source_hits": 0, "answerable_count": 0, "seconds": 0.0}
            for m in ("lexical", "semantic", "hybrid")
        },
        "embedding_model": model_record(ollama.get_model(settings.embedding_model)),
        "answer_model": model_record(answer_model),
        "file_hashes": snapshot.manifest.file_hashes,
        "limits": asdict(settings.limits),
        "created_at": snapshot.manifest.created_at,
        "rubric": (
            "All expected source-span lines in final context; manually "
            "correct and supported answers for Q1-Q8; explicit limitations "
            "and no invented runtime facts for Q9-Q10. Reference validation "
            "is structural, not an entailment score."
        ),
        "questions": [],
    }
    output = output_dir / "report.json"

    def save():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    save()
    for question in questions:
        row = {
            **question,
            "retrieval": {},
            "answer": None,
            "sources": [],
            "answer_error": None,
            "human_review": None,
        }
        try:
            require_fresh(snapshot, settings, ollama)
            start = perf_counter()
            lexical = search_lexical(
                snapshot.directory / "index.sqlite", question["question"]
            )
            lexical_time = perf_counter() - start
            start = perf_counter()
            vector = ollama.embed(
                (question["question"],), snapshot.manifest.embedding_model
            )[0]
            semantic = search_vectors(snapshot.directory / "qdrant", vector)
            semantic_time = perf_counter() - start
            context = min(8192, answer_model.context_length or 8192)
            prefix = (
                "Question: "
                + question["question"]
                + "\nUntrusted source evidence (JSON):\n"
            )
            budget = (
                min(6000, context - 1536) - len(SYSTEM.encode()) - len(prefix.encode())
            )
            for mode, hits, seconds in (
                ("lexical", lexical, lexical_time),
                ("semantic", semantic, semantic_time),
                ("hybrid", fuse(lexical, semantic), lexical_time + semantic_time),
            ):
                snippets = load_snippets(
                    snapshot.directory / "index.sqlite",
                    tuple(h.snippet_id for h in hits),
                )
                sources = select_evidence(RetrievalResult(hits, snippets, {}), budget)
                # A source hit measures retrieval coverage, not answer correctness.
                # Human-review fields remain open for checking the explanation.
                hit = (
                    any(
                        s.snippet.relative_path == question["expected_path"]
                        and s.snippet.start_line <= question["expected_start"]
                        and s.snippet.end_line >= question["expected_end"]
                        for s in sources
                    )
                    if question["expected_path"]
                    else None
                )
                row["retrieval"][mode] = {
                    "source_hit": hit,
                    "seconds": seconds,
                    "ranked_ids": [h.snippet_id for h in hits],
                    "final_sources": [
                        {
                            "path": s.snippet.relative_path,
                            "start_line": s.snippet.start_line,
                            "end_line": s.snippet.end_line,
                        }
                        for s in sources
                    ],
                }
                if hit is not None:
                    metrics = report["retrieval_modes"][mode]
                    metrics["source_hits"] += int(hit)
                    metrics["answerable_count"] += 1
                    metrics["seconds"] += seconds
            answer = answer_question(root, question["question"], settings, ollama)
            row["answer"] = {
                "text": answer.answer,
                "insufficient_evidence": answer.insufficient_evidence,
                "timings": answer.timings,
            }
            row["sources"] = [
                {
                    "source_id": s.source_id,
                    "path": s.snippet.relative_path,
                    "start_line": s.snippet.start_line,
                    "end_line": s.snippet.end_line,
                }
                for s in answer.sources
            ]
        except RepoLensError as exc:
            row["answer_error"] = exc.code
        report["questions"].append(row)
        save()
        print(f"{question['id']}: recorded", flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--questions", type=Path, default=Path("evaluation/questions.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--corpus-revision",
        help="Declared upstream revision for reproducibility; file hashes are always recorded.",
    )
    args = parser.parse_args()
    settings = load_settings()
    result = run_evaluation(
        args.root,
        settings,
        OllamaClient(settings),
        args.questions,
        args.output,
        args.corpus_revision,
    )
    print("Evaluation report: " + str(result))


if __name__ == "__main__":
    main()
