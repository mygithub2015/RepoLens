import json
import pytest


@pytest.mark.live_models
def test_default_model_returns_valid_structured_answer(tmp_path):
    from repolens.config import Settings
    from repolens.ollama import OllamaClient
    from repolens.answering import ANSWER_SCHEMA

    client = OllamaClient(Settings(data_dir=tmp_path))
    reply = client.chat(
        "qwen3.5:4b",
        [
            {
                "role": "system",
                "content": (
                    "Answer only from the evidence in JSON using answer, source_ids, "
                    "insufficient_evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Evidence S1: def add(a, b): return a + b\nQuestion: What does add "
                    "return?"
                ),
            },
        ],
        ANSWER_SCHEMA,
        8192,
    )
    data = json.loads(reply.content)
    assert reply.done_reason == "stop"
    assert data["source_ids"] == ["S1"]
    assert data["insufficient_evidence"] is False


@pytest.mark.live_models
def test_blog_guard_answer_cites_the_actual_decorator_lines(tmp_path):
    from pathlib import Path
    from repolens.config import Settings
    from repolens.ollama import OllamaClient
    from repolens.indexing import build_index
    from repolens.answering import answer_question

    settings = Settings(data_dir=tmp_path / "data")
    client = OllamaClient(settings)
    root = Path(__file__).parents[1] / "examples/flask-tutorial"
    build_index(root, settings, client)
    result = answer_question(
        root,
        "Which guard is applied to the route that creates a blog post?",
        settings,
        client,
    )
    assert any(
        s.snippet.relative_path == "flaskr/blog.py"
        and s.snippet.start_line <= 60
        and s.snippet.end_line >= 62
        for s in result.sources
    )
