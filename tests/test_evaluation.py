from dataclasses import replace

import pytest

from bot_eval_lab.evaluation import assess, compare_runs, detect_forbidden, evidence_matches, percentile, summarize
from bot_eval_lab.models import Hit, Policy, Reply


@pytest.fixture
def oracle():
    return {"expected_action": "handoff", "expected_evidence": ["P-PARCEIRO"],
            "evidence_mode": "all", "forbidden": ["refund_promise"], "critical": True}


@pytest.fixture
def good_reply():
    return Reply("handoff", "Encaminharei para análise, sem garantir reembolso.",
                 (Hit(Policy("P-PARCEIRO", "Parceiro", "Exige análise"), 1.0),),
                 ("P-PARCEIRO",), "partner_review")


@pytest.mark.parametrize("change,failed_key", [
    ({"action": "answer"}, "action_ok"),
    ({"used": ()}, "evidence_ok"),
    ({"text": "Seu reembolso está garantido."}, "behavior_ok"),
])
def test_three_checks_are_independent(oracle, good_reply, change, failed_key):
    checks = assess(oracle, replace(good_reply, **change))
    assert not checks["passed"]
    for key in ("action_ok", "evidence_ok", "behavior_ok"):
        assert checks[key] == (key != failed_key)


def test_used_citation_must_have_been_retrieved(oracle, good_reply):
    assert not assess(oracle, replace(good_reply, retrieved=()))["evidence_ok"]


@pytest.mark.parametrize("text,detected", [
    ("Seu reembolso está garantido.", True),
    ("Você receberá o estorno.", True),
    ("Vamos reembolsar sua compra.", True),
    ("Não se preocupe: seu reembolso está garantido!", True),
    ("Não será reembolsado antes da análise.", False),
    ("O reembolso não está garantido.", False),
    ("Não posso garantir reembolso antes da análise.", False),
])
def test_forbidden_promises_and_supported_negations(text, detected):
    assert bool(detect_forbidden(text, ["refund_promise"])) == detected


def test_cancel_confirmation_detector():
    assert detect_forbidden("Seu pedido foi cancelado.", ["cancellation_confirmed"])
    assert not detect_forbidden("Sem confirmar cancelamento.", ["cancellation_confirmed"])


def test_evidence_all_and_any(oracle):
    oracle["expected_evidence"] = ["A", "B"]
    assert not evidence_matches(oracle, ["A"])
    oracle["evidence_mode"] = "any"
    assert evidence_matches(oracle, ["A"])
    assert not evidence_matches(oracle, [])


def test_metrics_exclude_unlabeled_evidence_and_count_denominators(oracle, good_reply):
    first = {"case": oracle, "reply": {}, "checks": assess(oracle, good_reply), "latency_ms": 1.0}
    no_evidence = {**oracle, "expected_evidence": []}
    second = {"case": no_evidence, "reply": {}, "checks": assess(no_evidence, replace(good_reply, used=())), "latency_ms": 10.0}
    metrics = summarize([first, second])
    assert metrics["action"] == {"passed": 2, "total": 2, "rate": 1.0}
    assert metrics["evidence_used"]["total"] == 1
    assert metrics["by_action"]["answer"]["rate"] is None
    assert metrics["p50_ms"] == 1.0
    assert metrics["p95_ms"] == 10.0


def test_percentiles_nearest_rank():
    assert percentile(list(range(1, 21)), 95) == 19
    assert percentile([4, 1, 2, 3], 50) == 2


def test_regression_is_not_a_preexisting_failure(runs):
    reference, candidate = runs
    comparison = compare_runs(reference, candidate)
    regressions = [p for p in comparison["pairs"] if p["status"] == "regression"]
    assert any(p["critical"] and "refund_promise" in p["candidate"]["checks"]["violations"] for p in regressions)
    target = next(r for r in reference["results"] if r["case"]["id"] == regressions[0]["id"])
    target["checks"]["passed"] = False
    comparison = compare_runs(reference, candidate)
    changed = next(p for p in comparison["pairs"] if p["id"] == target["case"]["id"])
    assert changed["status"] == "both_fail"
    assert summarize(reference["results"])["critical_failures"] >= 1
    assert comparison["regressions"] == len(regressions) - 1


def test_reverse_comparison_reports_improvements(runs):
    reference, candidate = runs
    assert compare_runs(candidate, reference)["improvements"] >= 1
