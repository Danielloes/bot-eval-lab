"""Estratégias intercambiáveis: somente políticas e texto entram na busca."""

import math
from collections import Counter
from typing import Protocol

from .models import Hit, Policy
from .text import tokens

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Commit público fixo: evita que 'main' altere silenciosamente o experimento.
DEFAULT_REVISION = "bf3bf13ab40c3157080a7ab344c831b9ad18b5eb"


class Retriever(Protocol):
    config: dict

    def search(self, query: str, k: int = 4) -> tuple[Hit, ...]: ...


class LexicalRetriever:
    def __init__(self, policies: list[Policy], buggy: bool = False):
        # Regressão intencional de indexação: um filtro indevido perde exceções
        # de parceiros. Nenhum caso, rótulo ou ID de conversa é consultado.
        self.policies = sorted(
            (p for p in policies if not buggy or p.scope != "partner"),
            key=lambda p: p.id,
        )
        self.documents = {p.id: tokens(p.title + " " + p.text) for p in self.policies}
        self.titles = {p.id: tokens(p.title) for p in self.policies}
        frequency = Counter(t for doc in self.documents.values() for t in doc)
        self.idf = {t: math.log(1 + len(self.policies) / (1 + n)) for t, n in frequency.items()}
        self.config = {"strategy": "lexical-buggy" if buggy else "lexical",
                       "ranking": "overlap-idf-title2-v1", "index_filter": "exclude_partner" if buggy else "all"}

    def search(self, query: str, k: int = 4) -> tuple[Hit, ...]:
        query_tokens = tokens(query)
        hits = []
        for p in self.policies:
            common = query_tokens & self.documents[p.id]
            # Ordenar termos também torna a soma de floats determinística.
            score = sum(self.idf[t] * (2 if t in self.titles[p.id] else 1) for t in sorted(common))
            if score > 0:
                hits.append(Hit(p, score))
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.policy.id))[:k])


class SemanticRetriever:
    def __init__(self, policies: list[Policy], model_name: str = DEFAULT_MODEL,
                 revision: str | None = DEFAULT_REVISION, cache_dir: str = ".cache/models",
                 local_only: bool = False):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Busca semântica requer: python -m pip install ".[semantic]"') from exc
        self.policies = sorted(policies, key=lambda p: p.id)
        # Um carregamento por execução, CPU e nenhum código remoto.
        self.model = SentenceTransformer(model_name, revision=revision, device="cpu",
                                         cache_folder=cache_dir, local_files_only=local_only,
                                         trust_remote_code=False)
        self.model.eval()
        self.vectors = self.model.encode(
            [p.title + ". " + p.text for p in self.policies],
            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
        )
        self.config = {"strategy": "semantic", "model": model_name, "revision": revision,
                       "device": "cpu", "normalized_embeddings": True,
                       "max_seq_length": self.model.max_seq_length, "local_only": local_only}

    def search(self, query: str, k: int = 4) -> tuple[Hit, ...]:
        vector = self.model.encode(query, normalize_embeddings=True,
                                   convert_to_numpy=True, show_progress_bar=False)
        # Produto de vetores unitários = similaridade de cosseno.
        scores = self.vectors @ vector
        hits = [Hit(p, float(score)) for p, score in zip(self.policies, scores)]
        return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.policy.id))[:k])


def make_retriever(strategy: str, policies: list[Policy], **semantic_options) -> Retriever:
    if strategy in {"lexical", "lexical-buggy"}:
        return LexicalRetriever(policies, buggy=strategy == "lexical-buggy")
    if strategy == "semantic":
        return SemanticRetriever(policies, **semantic_options)
    raise ValueError(f"Estratégia desconhecida: {strategy}")
