import httpx
import pytest


def catalog_transport(request):
    if request.url.path == "/api/tags":
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "local:4b", "digest": "a"},
                    {"name": "embed:small", "digest": "b"},
                    {"name": "cloud-model:cloud", "digest": "c"},
                    {"name": "ambiguous", "digest": "d"},
                ]
            },
        )
    name = __import__("json").loads(request.content)["model"]
    return httpx.Response(
        200,
        json={
            "capabilities": {
                "local:4b": ["completion", "thinking"],
                "embed:small": ["embedding"],
                "cloud-model:cloud": ["completion"],
            }.get(name, []),
            "model_info": {"test.context_length": 4096},
            **({"remote_host": "https://example.invalid"} if "cloud" in name else {}),
        },
    )


def test_catalog_excludes_cloud_and_preserves_capabilities(tmp_path):
    from repolens.config import Settings
    from repolens.ollama import OllamaClient

    client = OllamaClient(
        Settings(data_dir=tmp_path), httpx.MockTransport(catalog_transport)
    )
    models = client.list_models()
    assert [m.name for m in models] == ["ambiguous", "embed:small", "local:4b"]
    assert client.get_model("local:4b").context_length == 4096
    assert client.get_model("ambiguous").capabilities == frozenset()


def test_missing_ollama_is_actionable(tmp_path):
    from repolens.config import Settings
    from repolens.ollama import OllamaClient
    from repolens.errors import RepoLensError

    def offline(request):
        raise httpx.ConnectError("offline")

    with pytest.raises(RepoLensError, match="Ollama"):
        OllamaClient(
            Settings(data_dir=tmp_path), httpx.MockTransport(offline)
        ).list_models()


def test_embeddings_are_batched_without_truncation(tmp_path):
    from repolens.config import Settings
    from repolens.ollama import OllamaClient

    def respond(request):
        import json

        data = json.loads(request.content)
        assert request.url.path == "/api/embed"
        assert data == {
            "model": "embed:small",
            "input": ["first", "second"],
            "truncate": False,
        }
        return httpx.Response(200, json={"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    assert OllamaClient(
        Settings(data_dir=tmp_path), httpx.MockTransport(respond)
    ).embed(("first", "second"), "embed:small") == [[1.0, 0.0], [0.0, 1.0]]
