"""Finite HTTP calls to the user-managed Ollama runtime."""

from typing import Protocol
import httpx
from repolens.config import Settings
from repolens.domain import ModelInfo, ChatReply
from repolens.errors import RepoLensError


class OllamaGateway(Protocol):
    """The runtime contract shared by the real HTTP client and test fakes."""

    def list_models(self) -> tuple[ModelInfo, ...]: ...
    def get_model(self, name: str) -> ModelInfo: ...
    def embed(self, texts: tuple[str, ...], model: str) -> list[list[float]]: ...
    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, object],
        context: int,
    ) -> ChatReply: ...


class OllamaClient:
    """Call an existing Ollama runtime without downloading or choosing models."""

    def __init__(
        self, settings: Settings, transport: httpx.BaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport

    def _request(
        self, method: str, path: str, payload: dict | None = None, timeout: int = 5
    ) -> dict:
        try:
            with httpx.Client(
                base_url=self.settings.ollama_url,
                transport=self.transport,
                timeout=timeout,
                trust_env=False,
            ) as client:
                response = client.request(method, path, json=payload)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("Expected an object")
                return result
        except (httpx.HTTPError, ValueError) as exc:
            raise RepoLensError(
                "model_unavailable",
                "Ollama request failed. Start Ollama, check the installed model, and retry.",
            ) from exc

    def _details(self, tag: dict) -> ModelInfo:
        name = tag.get("name", "")
        data = self._request("POST", "/api/show", {"model": name})
        limits = [
            v
            for k, v in data.get("model_info", {}).items()
            if k.endswith(".context_length") and type(v) is int and v > 0
        ]
        local = not any(
            data.get(k) or tag.get(k) for k in ("remote_host", "remote_model")
        ) and not name.endswith(":cloud")
        capabilities = data.get("capabilities", [])
        return ModelInfo(
            name,
            tag.get("digest", ""),
            frozenset(c for c in capabilities if isinstance(c, str)),
            min(limits) if limits else None,
            local,
        )

    def list_models(self) -> tuple[ModelInfo, ...]:
        """Inspect capabilities and exclude remote-only model entries."""
        try:
            models = [
                self._details(tag)
                for tag in self._request("GET", "/api/tags").get("models", [])
            ]
            return tuple(
                sorted((m for m in models if m.is_local), key=lambda m: m.name)
            )
        except (TypeError, AttributeError) as exc:
            raise RepoLensError(
                "model_unavailable",
                "Ollama returned invalid model metadata. Refresh models after checking Ollama.",
            ) from exc

    def get_model(self, name: str) -> ModelInfo:
        """Resolve the selected local model, including its current digest."""
        for tag in self._request("GET", "/api/tags").get("models", []):
            if tag.get("name") == name:
                model = self._details(tag)
                if model.is_local and model.digest:
                    return model
        raise RepoLensError(
            "model_unavailable",
            "Selected model is not installed locally. Install it in Ollama, then refresh models.",
        )

    def embed(self, texts: tuple[str, ...], model: str) -> list[list[float]]:
        """Request complete vectors; truncated or incomplete batches are errors."""
        data = self._request(
            "POST",
            "/api/embed",
            # Silently shortened inputs would no longer match the indexed snippet.
            {"model": model, "input": list(texts), "truncate": False},
            120,
        )
        vectors = data.get("embeddings")
        if (
            not isinstance(vectors, list)
            or len(vectors) != len(texts)
            or not vectors
            or not all(isinstance(v, list) and v for v in vectors)
        ):
            raise RepoLensError(
                "model_incompatible",
                (
                    "Ollama returned an incomplete embedding batch. Retry or select a "
                    "compatible model."
                ),
            )
        from repolens.vectors import validate_vector

        for vector in vectors:
            validate_vector(vector, len(vectors[0]))
        return vectors

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        schema: dict[str, object],
        context: int,
    ) -> ChatReply:
        """Request one bounded structured answer without execution tools."""
        info = self.get_model(model)
        if not info.is_local or "completion" not in info.capabilities:
            raise RepoLensError(
                "model_incompatible",
                "Select a locally installed answer model with generation capability.",
            )
        payload = {
            "model": model,
            "messages": messages,
            "format": schema,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512, "num_ctx": context},
        }
        if "thinking" in info.capabilities:
            payload["think"] = False
        data = self._request("POST", "/api/chat", payload, 120)
        message = data.get("message", {})
        if (
            data.get("done") is not True
            or not isinstance(message, dict)
            or not isinstance(message.get("content"), str)
        ):
            raise RepoLensError(
                "answer_invalid",
                "Ollama returned an incomplete answer. Retry the question.",
            )
        return ChatReply(message["content"], data.get("done_reason", ""))
