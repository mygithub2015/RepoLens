from dataclasses import replace


def test_preferences_round_trip_with_defaults(tmp_path, monkeypatch):
    from repolens.config import load_settings, save_model_preferences

    monkeypatch.setenv("REPOLENS_DATA_DIR", str(tmp_path))
    settings = load_settings()
    assert settings.answer_model == "qwen3.5:4b"
    assert settings.embedding_model == "qwen3-embedding:0.6b"
    save_model_preferences(replace(settings, answer_model="other:4b"))
    assert load_settings().answer_model == "other:4b"


def test_corrupt_preferences_are_actionable(tmp_path, monkeypatch):
    import pytest
    from repolens.config import load_settings
    from repolens.errors import RepoLensError

    monkeypatch.setenv("REPOLENS_DATA_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text("{broken")
    with pytest.raises(RepoLensError, match="settings"):
        load_settings()
