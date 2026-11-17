"""Normalização pequena e explícita; não é um analisador completo do português."""

import re
import unicodedata

STOP_WORDS = set("a o as os um uma de da do das dos em no na nos nas e ou para por com que qual eu meu minha me voce se ao ate ja foi tem esta esse essa isso como quanto quais".split())
ALIASES = {
    "cancelar": "cancelamento", "cancela": "cancelamento", "canselar": "cancelamento",
    "cancele": "cancelamento", "cancelado": "cancelamento", "desistir": "cancelamento",
    "trocar": "troca", "trocas": "troca", "devolver": "troca", "devolucao": "troca",
    "reembouco": "reembolso", "reemboso": "reembolso", "estorno": "reembolso",
    "reembolsar": "reembolso", "reembolsado": "reembolso", "parceiros": "parceiro",
    "marketplace": "parceiro", "vendedores": "vendedor", "rastrear": "rastreio",
    "rastreamento": "rastreio", "rastreiu": "rastreio", "entregue": "entrega",
    "chegar": "entrega", "chega": "entrega", "recebi": "recebido",
    "recebida": "recebido", "aprovada": "aprovado", "aprovacao": "aprovado",
    "enviada": "enviado", "despachado": "enviado", "expedido": "enviado",
    "dias": "dia", "uteis": "util", "atrasada": "atraso", "atrasado": "atraso",
    "danificado": "defeito", "quebrado": "defeito", "avariado": "defeito",
}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", normalize(text))
    return {ALIASES.get(w, w) for w in words if w not in STOP_WORDS}
