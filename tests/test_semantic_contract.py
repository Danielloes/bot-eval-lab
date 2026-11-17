"""Testes do adaptador com doubles. Não são resultados de IA real."""

import sys
from types import SimpleNamespace

from bot_eval_lab.models import Policy
from bot_eval_lab.retrieval import SemanticRetriever


def test_semantic_loads_once_reuses_policy_vectors_and_sorts_cosines(monkeypatch):
    calls = []

    class Matrix:
        def __matmul__(self, vector):
            return [sum(a * b for a, b in zip(row, vector)) for row in [(1, 0), (0, 1)]]

    class LocalEncoder:
        max_seq_length = 128

        def __init__(self, *args, **kwargs):
            calls.append(("load", kwargs))

        def eval(self):
            pass

        def encode(self, text, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            calls.append(("encode", text))
            return Matrix() if isinstance(text, list) else [0, 1]

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=LocalEncoder))
    retriever = SemanticRetriever([Policy("B", "Segundo", "dois"), Policy("A", "Primeiro", "um")], local_only=True)
    for _ in range(2):
        hits = retriever.search("consulta", 2)
        assert [(h.policy.id, h.score) for h in hits] == [("B", 1.0), ("A", 0.0)]
    assert sum(c[0] == "load" for c in calls) == 1
    assert sum(c[0] == "encode" and isinstance(c[1], list) for c in calls) == 1
    assert calls[0][1]["local_files_only"] is True
    assert calls[0][1]["trust_remote_code"] is False
