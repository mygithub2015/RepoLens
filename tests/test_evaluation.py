import json
from pathlib import Path
from fakes import FakeOllama


def test_report_preserves_all_cases_and_retrieval_modes(source_root, tmp_path):
    from repolens.config import Settings
    from repolens.evaluation import run_evaluation

    questions = [
        {
            "id": f"Q{i}",
            "question": "Explain hello",
            "expected_path": "app.py" if i <= 8 else None,
            "expected_start": 1 if i <= 8 else None,
            "expected_end": 2 if i <= 8 else None,
            "expected_facts": "hello",
        }
        for i in range(1, 11)
    ]
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(questions))
    fake = (
        FakeOllama()
    )  # Intentionally malformed answers must remain recorded failures.
    result = run_evaluation(
        source_root,
        Settings(data_dir=tmp_path / "data"),
        fake,
        path,
        tmp_path / "results",
        corpus_revision="ff6fa22f4d961a28567db11430208b964620f511",
    )
    report = json.loads(result.read_text())
    assert report["corpus_revision"] == "ff6fa22f4d961a28567db11430208b964620f511"
    assert report["answerable_count"] == 8
    assert report["unanswerable_count"] == 2
    assert set(report["retrieval_modes"]) == {"lexical", "semantic", "hybrid"}
    assert len(report["questions"]) == 10
    assert all(row["answer_error"] == "answer_invalid" for row in report["questions"])
    assert str(tmp_path) not in result.read_text()
    assert all(row["human_review"] is None for row in report["questions"])
