"""Carrega e valida o contrato do avaliador, isolado do assistente."""

import hashlib
import json
from pathlib import Path

from .models import Policy

DATA = Path(__file__).parent / "data"
ACTIONS = ("answer", "clarify", "handoff")
FORBIDDEN = {"refund_promise", "cancellation_confirmed"}


def fingerprint(value) -> str:
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_inputs(cases_path: Path = DATA / "cases.json", policies_path: Path = DATA / "policies.json",
                split: str = "holdout") -> tuple[dict, dict, list[Policy]]:
    dataset = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    corpus = json.loads(Path(policies_path).read_text(encoding="utf-8"))
    if split not in {"dev", "holdout", "all"}:
        raise ValueError("Divisão inválida; use dev, holdout ou all")
    policies = [Policy(**p) for p in corpus["policies"]]
    policy_ids = {p.id for p in policies}
    if not policies or len(policy_ids) != len(policies):
        raise ValueError("A base deve ter trechos e IDs de política únicos")
    ids, groups, conversations = set(), {}, {}
    for case in dataset["cases"]:
        if case["id"] in ids:
            raise ValueError(f"ID de caso duplicado: {case['id']}")
        ids.add(case["id"])
        if case["expected_action"] not in ACTIONS or case["split"] not in {"dev", "holdout"}:
            raise ValueError(f"Ação ou divisão inválida: {case['id']}")
        if case["evidence_mode"] not in {"any", "all"}:
            raise ValueError("evidence_mode deve ser any ou all")
        if not isinstance(case["critical"], bool):
            raise ValueError("critical deve ser booleano")
        if not set(case["expected_evidence"]) <= policy_ids or not set(case["forbidden"]) <= FORBIDDEN:
            raise ValueError(f"Evidência ou comportamento proibido desconhecido: {case['id']}")
        if not case["history"] or not any(m["role"] == "user" for m in case["history"]):
            raise ValueError("Conversa deve conter mensagem do cliente")
        for message in case["history"]:
            if message["role"] not in {"user", "assistant"} or not isinstance(message["text"], str) or not message["text"].strip():
                raise ValueError("Mensagem inválida")
        previous_split = groups.setdefault(case["group"], case["split"])
        if previous_split != case["split"]:
            raise ValueError(f"Vazamento: grupo {case['group']} aparece em duas divisões")
        conversation_hash = fingerprint(case["history"])
        previous_split = conversations.setdefault(conversation_hash, case["split"])
        if previous_split != case["split"]:
            raise ValueError("Vazamento: conversa idêntica nas duas divisões")
    selected = sorted((c for c in dataset["cases"] if split == "all" or c["split"] == split), key=lambda c: c["id"])
    if not selected:
        raise ValueError("Nenhum caso na divisão selecionada")
    # Hash inclui histórico, rótulos, grupos, criticidade e regras dos casos.
    snapshot = {"id": dataset["id"], "split": split, "cases": selected}
    corpus = {**corpus, "policies": sorted(corpus["policies"], key=lambda p: p["id"])}
    return snapshot, corpus, policies
