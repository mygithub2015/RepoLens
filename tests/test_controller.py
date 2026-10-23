from dataclasses import replace
import pytest
from fakes import FakeOllama


def test_answer_model_change_clears_answer_without_rebuild(source_root, tmp_path):
    from repolens.config import Settings
    from repolens.controller import AppController

    fake = FakeOllama()
    controller = AppController(Settings(data_dir=tmp_path / "data"), fake)
    snapshot = controller.build(source_root)
    before = fake.embedding_call_count
    controller.set_models("another-answer", "qwen3-embedding:0.6b")
    assert controller.status(source_root).state == "ready"
    assert fake.embedding_call_count == before
    controller.set_models("another-answer", "another-embedding")
    assert controller.status(source_root).state == "stale"


def test_existing_root_restores_embedding_selection(source_root, tmp_path):
    from repolens.config import Settings
    from repolens.controller import AppController

    settings = Settings(data_dir=tmp_path / "data", embedding_model="another-embedding")
    first = AppController(settings, FakeOllama())
    first.build(source_root)
    second = AppController(
        replace(settings, embedding_model="qwen3-embedding:0.6b"), FakeOllama()
    )
    second.open_repository(source_root)
    assert second.settings.embedding_model == "another-embedding"
