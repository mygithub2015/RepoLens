"""Deterministic test runtime; never used to report AI quality."""

from hashlib import sha256
from repolens.domain import ModelInfo


class FakeOllama:
    def __init__(self):
        self.digest = "embedding-v1"
        self.dimensions = 8
        self.embedding_call_count = 0
        self.on_embed = None
        self.fail_embed = False
        self.chat_calls = []
        self.on_chat = None
        self.reply = "{}"
        self.done_reason = "stop"

    def list_models(self):
        return (self.get_model("qwen3.5:4b"), self.get_model("qwen3-embedding:0.6b"))

    def get_model(self, name):
        embed = "embedding" in name
        return ModelInfo(
            name,
            self.digest if embed else "answer-v1",
            frozenset({"embedding"} if embed else {"completion"}),
            8192,
            True,
        )

    def embed(self, texts, model):
        self.embedding_call_count += 1
        if self.fail_embed:
            raise RuntimeError("injected embedding failure")
        if self.on_embed:
            self.on_embed()
        return [
            [
                (x / 255) + 0.01
                for x in sha256(text.encode()).digest()[: self.dimensions]
            ]
            for text in texts
        ]

    def chat(self, model, messages, schema, context):
        from repolens.domain import ChatReply

        self.chat_calls.append(
            {"model": model, "messages": messages, "schema": schema, "context": context}
        )
        if self.on_chat:
            self.on_chat()
        return ChatReply(self.reply, self.done_reason)
