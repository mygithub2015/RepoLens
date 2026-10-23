from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_unavailable_ollama_shows_readiness_error(tmp_path, monkeypatch):
    from repolens.errors import RepoLensError
    from repolens.ollama import OllamaClient

    monkeypatch.setenv("REPOLENS_DATA_DIR", str(tmp_path))

    def offline(self):
        raise RepoLensError("model_unavailable", "Start Ollama and refresh models.")

    monkeypatch.setattr(OllamaClient, "list_models", offline)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    assert not app.exception
    assert any("Ollama" in element.value for element in app.error)
    assert next(b for b in app.button if b.label == "Ask").disabled


def test_full_flow_and_model_switch_clear_old_answer(
    source_root, tmp_path, monkeypatch
):
    import json
    from fakes import FakeOllama
    from repolens.config import Settings
    from repolens.controller import AppController
    import repolens.ui as ui

    fake = FakeOllama()
    fake.reply = json.dumps(
        {
            "answer": "Hello is returned [S1].",
            "source_ids": ["S1"],
            "insufficient_evidence": False,
        }
    )
    controller = AppController(Settings(data_dir=tmp_path / "data"), fake)
    monkeypatch.setattr(ui, "create_controller", lambda: controller)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    app.checkbox(key="manual_path").check().run()
    app.text_input(key="root").set_value(str(source_root)).run()
    next(b for b in app.button if b.label == "Build index").click().run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "Ask").disabled  # no question yet
    app.text_area(key="question").set_value("What does hello return?").run()
    next(b for b in app.button if b.label == "Ask").click().run()
    assert any("Hello is returned" in v.value for v in app.text)
    (source_root / "app.py").write_text("changed=1\n")
    app.run()
    assert next(b for b in app.button if b.label == "Ask").disabled
    assert not any("Hello is returned" in v.value for v in app.text)


def test_source_display_uses_original_line_numbers():
    from repolens.domain import Snippet
    from repolens.ui import numbered_source

    assert (
        numbered_source(Snippet(1, "a.py", 51, 52, "first\r\nsecond\r\n"))
        == "  51 first\n  52 second"
    )


def test_corrupt_index_can_be_rebuilt_in_ui(source_root, tmp_path, monkeypatch):
    from fakes import FakeOllama
    from repolens.config import Settings
    from repolens.controller import AppController
    import repolens.ui as ui

    controller = AppController(Settings(data_dir=tmp_path / "data"), FakeOllama())
    snapshot = controller.build(source_root)
    (snapshot.directory / "qdrant/collection/snippets/storage.sqlite").write_bytes(
        b"not sqlite"
    )
    monkeypatch.setattr(ui, "create_controller", lambda: controller)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    app.checkbox(key="manual_path").check().run()
    app.text_input(key="root").set_value(str(source_root)).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Rebuild index").click().run()
    assert not app.exception
    assert controller.status(source_root).state == "ready"


def workspace(source_root, tmp_path, monkeypatch, selections=None):
    """Real controller/stores with only the desktop dialog and Ollama replaced."""
    import json
    from fakes import FakeOllama
    from repolens.config import Settings
    from repolens.controller import AppController
    import repolens.ui as ui

    fake = FakeOllama()
    fake.reply = json.dumps(
        {
            "answer": "Hello is returned [S1].",
            "source_ids": ["S1"],
            "insufficient_evidence": False,
        }
    )
    catalog = ("qwen3.5:4b", "other-answer", "qwen3-embedding:0.6b", "other-embedding")
    fake.list_models = lambda: tuple(fake.get_model(name) for name in catalog)
    controller = AppController(Settings(data_dir=tmp_path / "data"), fake)
    remaining = selections if selections is not None else [source_root]

    def choose(initial=None):
        selected = remaining.pop(0)
        if isinstance(selected, Exception):
            raise selected
        return selected

    monkeypatch.setattr(ui, "create_controller", lambda: controller)
    monkeypatch.setattr(ui, "choose_repository_folder", choose, raising=False)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    return app, controller, fake


def click(app, label):
    matches = [button for button in app.button if button.label == label]
    assert matches, f"Expected an available {label!r} control"
    matches[0].click().run()
    assert not app.exception


def question_input(app):
    return app.text_area(key="question")


def build_and_answer(app):
    click(app, "Browse…")
    click(app, "Build index")
    question_input(app).set_value("What does hello return?").run()
    click(app, "Ask")
    assert any("Hello is returned" in text.value for text in app.text)


def test_browse_selects_existing_folder_and_enables_build(
    source_root, tmp_path, monkeypatch
):
    app, controller, fake = workspace(source_root, tmp_path, monkeypatch)
    assert app.text_input(key="root").disabled
    assert next(b for b in app.button if b.label == "Ask").disabled
    click(app, "Browse…")
    assert app.text_input(key="root").value == str(source_root)
    assert controller.status(source_root).state == "missing"
    click(app, "Build index")
    assert controller.status(source_root).state == "ready"
    assert next(b for b in app.button if b.label == "Ask").disabled


def test_browse_cancel_preserves_repository_and_answer(
    source_root, tmp_path, monkeypatch
):
    app, controller, fake = workspace(
        source_root, tmp_path, monkeypatch, [source_root, None]
    )
    build_and_answer(app)
    click(app, "Browse…")
    assert app.text_input(key="root").value == str(source_root)
    assert any("Hello is returned" in text.value for text in app.text)
    assert len(fake.chat_calls) == 1


def test_browse_error_preserves_answer_and_manual_fallback(
    source_root, tmp_path, monkeypatch
):
    from repolens.errors import RepoLensError

    failure = RepoLensError("folder_picker_unavailable", "Choose the folder manually.")
    app, controller, fake = workspace(
        source_root, tmp_path, monkeypatch, [source_root, failure]
    )
    build_and_answer(app)
    click(app, "Browse…")
    assert any("manually" in error.value for error in app.error)
    assert any("Hello is returned" in text.value for text in app.text)
    assert app.text_input(key="root").value == str(source_root)
    app.checkbox(key="manual_path").check().run()
    assert not app.text_input(key="root").disabled


def test_browse_switch_restores_snapshot_embedding_and_clears_answer(
    source_root, tmp_path, monkeypatch
):
    other = tmp_path / "other-source"
    other.mkdir()
    (other / "other.py").write_text("def other():\n    return 2\n")
    app, controller, fake = workspace(
        source_root, tmp_path, monkeypatch, [source_root, other]
    )
    controller.set_models("qwen3.5:4b", "other-embedding")
    controller.build(other)
    controller.set_models("qwen3.5:4b", "qwen3-embedding:0.6b")
    build_and_answer(app)
    click(app, "Browse…")
    assert app.selectbox(key="embedding_model").value == "other-embedding"
    assert controller.status(other).state == "ready"
    assert not any("Hello is returned" in text.value for text in app.text)


def test_model_switches_keep_answer_model_independent_from_index(
    source_root, tmp_path, monkeypatch
):
    app, controller, fake = workspace(source_root, tmp_path, monkeypatch)
    build_and_answer(app)
    from repolens.indexing import load_active

    build_id = load_active(source_root, controller.settings.data_dir).manifest.build_id
    embedding_calls = fake.embedding_call_count
    app.selectbox(key="answer_model").select("other-answer").run()
    assert not app.exception
    assert not any("Hello is returned" in text.value for text in app.text)
    assert controller.status(source_root).state == "ready"
    assert (
        load_active(source_root, controller.settings.data_dir).manifest.build_id
        == build_id
    )
    assert fake.embedding_call_count == embedding_calls
    click(app, "Ask")
    assert fake.chat_calls[-1]["model"] == "other-answer"
    app.selectbox(key="embedding_model").select("other-embedding").run()
    assert controller.status(source_root).state == "stale"
    assert next(b for b in app.button if b.label == "Ask").disabled
    assert not any("Hello is returned" in text.value for text in app.text)


def test_failed_rebuild_retains_snapshot_and_retry_recovers(
    source_root, tmp_path, monkeypatch
):
    from repolens.indexing import load_active

    app, controller, fake = workspace(source_root, tmp_path, monkeypatch)
    build_and_answer(app)
    old_id = load_active(source_root, controller.settings.data_dir).manifest.build_id
    (source_root / "app.py").write_text("def hello():\n    return 'updated'\n")
    fake.fail_embed = True
    app.run()
    assert next(b for b in app.button if b.label == "Ask").disabled
    click(app, "Rebuild index")
    assert app.error
    assert (
        load_active(source_root, controller.settings.data_dir).manifest.build_id
        == old_id
    )
    fake.fail_embed = False
    click(app, "Retry rebuild")
    assert controller.status(source_root).state == "ready"
    assert not app.error
    assert (
        load_active(source_root, controller.settings.data_dir).manifest.build_id
        != old_id
    )


def test_question_edits_and_unavailable_models_clear_or_disable_answer(
    source_root, tmp_path, monkeypatch
):
    app, controller, fake = workspace(source_root, tmp_path, monkeypatch)
    build_and_answer(app)
    question_input(app).set_value("A different question").run()
    assert not any("Hello is returned" in text.value for text in app.text)
    fake.list_models = lambda: ()
    click(app, "Refresh models")
    assert app.warning
    assert next(b for b in app.button if b.label == "Ask").disabled
