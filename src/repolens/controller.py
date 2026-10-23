"""A small service facade keeps Streamlit state outside the retrieval core."""

from dataclasses import replace
from pathlib import Path
from repolens.config import Settings, load_settings, save_model_preferences, check_fts5
from repolens.domain import ModelInfo, IndexStatus, Snapshot, AnswerResult
from repolens.ollama import OllamaGateway, OllamaClient
from repolens.indexing import build_index, index_status, load_active
from repolens.answering import answer_question


class AppController:
    """Connect UI actions to core services without importing Streamlit."""

    def __init__(self, settings: Settings, ollama: OllamaGateway):
        self.settings = settings
        self.ollama = ollama

    def models(self) -> tuple[ModelInfo, ...]:
        return self.ollama.list_models()

    def status(self, root: Path) -> IndexStatus:
        return index_status(root, self.settings, self.ollama)

    def build(self, root: Path) -> Snapshot:
        return build_index(root, self.settings, self.ollama)

    def ask(self, root: Path, question: str) -> AnswerResult:
        return answer_question(root, question, self.settings, self.ollama)

    def set_models(self, answer_model: str, embedding_model: str) -> None:
        updated = replace(
            self.settings, answer_model=answer_model, embedding_model=embedding_model
        )
        save_model_preferences(updated)
        self.settings = updated

    def open_repository(self, root: Path) -> None:
        snapshot = load_active(root, self.settings.data_dir)
        if snapshot:
            self.settings = replace(
                self.settings, embedding_model=snapshot.manifest.embedding_model
            )


def create_controller() -> AppController:
    """Check local prerequisites and connect the UI to the Ollama runtime."""
    check_fts5()
    settings = load_settings()
    return AppController(settings, OllamaClient(settings))
