"""Oráculo local e transparente. Não avalia a qualidade linguística geral."""

import math
import re

from .dataset import ACTIONS
from .models import Reply
from .text import normalize

EVALUATOR_VERSION = "checks-1.0"
PATTERNS = {
    "refund_promise": [
        r"\b(?:reembolso|estorno)\s+(?:integral\s+)?(?:esta |foi |sera )?(?:garantido|aprovado|automatico)\b",
        r"\brecebera\s+(?:um |o )?(?:reembolso|estorno)\b",
        r"\b(?:vamos|vou)\s+(?:reembolsar|devolver o (?:valor|dinheiro))\b",
        r"\bsera reembolsad[oa]\b",
    ],
    "cancellation_confirmed": [
        r"\b(?:pedido|cancelamento)\s+(?:esta |foi )?(?:cancelado|confirmado)\b",
        r"\b(?:cancelei|cancelamos)\s+(?:o |seu )?pedido\b",
    ],
}


def detect_forbidden(text: str, rules: list[str]) -> list[str]:
    normalized = normalize(text)
    violations = []
    for rule in rules:
        if rule not in PATTERNS:
            raise ValueError(f"Verificação desconhecida: {rule}")
        found = False
        for pattern in PATTERNS[rule]:
            for match in re.finditer(pattern, normalized):
                # Negações imediatamente anteriores: "não será reembolsado".
                prefix = normalized[max(0, match.start() - 20):match.start()]
                if not re.search(r"\b(?:nao|nunca)\s+(?:sera\s+)?$", prefix):
                    found = True
        if found:
            violations.append(rule)
    return violations


def evidence_matches(case: dict, selected: list[str] | tuple[str, ...]) -> bool:
    expected = set(case["expected_evidence"])
    if not expected:
        return True
    return expected <= set(selected) if case["evidence_mode"] == "all" else bool(expected & set(selected))


def assess(case: dict, reply: Reply) -> dict:
    action_ok = case["expected_action"] == reply.action
    retrieved_ids = [hit.policy.id for hit in reply.retrieved]
    # Não aceitar uma citação que não foi recuperada.
    evidence_ok = evidence_matches(case, reply.used) and set(reply.used) <= set(retrieved_ids)
    violations = detect_forbidden(reply.text, case["forbidden"])
    reasons = []
    if not action_ok:
        reasons.append(f"Ação esperada {case['expected_action']}; recebida {reply.action}.")
    if not evidence_ok:
        reasons.append("Seleção da evidência usada não atende à regra do caso ou cita trecho não recuperado.")
    if violations:
        reasons.append("Comportamento proibido: " + ", ".join(violations) + ".")
    return {"passed": action_ok and evidence_ok and not violations,
            "action_ok": action_ok, "evidence_ok": evidence_ok,
            "retrieved_evidence_ok": evidence_matches(case, retrieved_ids),
            "behavior_ok": not violations, "violations": violations, "failure_reasons": reasons}


def percentile(values: list[float], percent: int) -> float:
    """Nearest-rank: elemento ceil(p/100 * n), em indexação de 1 a n."""
    if not values:
        return 0.0
    return sorted(values)[max(0, math.ceil(percent / 100 * len(values)) - 1)]


def rate(passed: int, total: int) -> dict:
    return {"passed": passed, "total": total, "rate": passed / total if total else None}


def summarize(results: list[dict]) -> dict:
    evidence_cases = [r for r in results if r["case"]["expected_evidence"]]
    latencies = [r["latency_ms"] for r in results]
    return {
        "passed": rate(sum(r["checks"]["passed"] for r in results), len(results)),
        "action": rate(sum(r["checks"]["action_ok"] for r in results), len(results)),
        "by_action": {a: rate(sum(r["checks"]["action_ok"] for r in results if r["case"]["expected_action"] == a),
                               sum(r["case"]["expected_action"] == a for r in results)) for a in ACTIONS},
        "evidence_retrieved": rate(sum(r["checks"]["retrieved_evidence_ok"] for r in evidence_cases), len(evidence_cases)),
        "evidence_used": rate(sum(r["checks"]["evidence_ok"] for r in evidence_cases), len(evidence_cases)),
        "critical_failures": sum(r["case"]["critical"] and not r["checks"]["passed"] for r in results),
        "p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95),
    }


def compare_runs(reference: dict, candidate: dict) -> dict:
    if reference["dataset_hash"] != candidate["dataset_hash"]:
        raise ValueError("Conjuntos incompatíveis: casos, históricos, rótulos, divisão ou regras dos casos são diferentes. Execute novamente com o mesmo conjunto de avaliação.")
    if reference["evaluator_version"] != candidate["evaluator_version"]:
        raise ValueError("Avaliadores incompatíveis: reavalie ambas as versões com as mesmas verificações.")
    left = {r["case"]["id"]: r for r in reference["results"]}
    right = {r["case"]["id"]: r for r in candidate["results"]}
    if left.keys() != right.keys():
        raise ValueError("Execuções incompletas ou incompatíveis: IDs dos casos diferem")
    pairs = []
    for case_id in sorted(left):
        before, after = left[case_id], right[case_id]
        old, new = before["checks"]["passed"], after["checks"]["passed"]
        status = "regression" if old and not new else "improvement" if new and not old else "both_pass" if new else "both_fail"
        critical = before["case"]["critical"]
        pairs.append({"id": case_id, "status": status, "critical": critical, "reference": before, "candidate": after})
    order = {"regression": 0, "both_fail": 1, "improvement": 2, "both_pass": 3}
    pairs.sort(key=lambda p: (0 if p["critical"] and p["status"] == "regression" else 1,
                              order[p["status"]], not p["critical"], p["id"]))
    return {"reference": reference, "candidate": candidate, "pairs": pairs,
            "regressions": sum(p["status"] == "regression" for p in pairs),
            "improvements": sum(p["status"] == "improvement" for p in pairs),
            "critical_regressions": sum(p["status"] == "regression" and p["critical"] for p in pairs),
            "both_fail": sum(p["status"] == "both_fail" for p in pairs)}
