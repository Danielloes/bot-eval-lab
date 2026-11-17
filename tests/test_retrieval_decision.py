import pytest

from bot_eval_lab.decision import Assistant
from bot_eval_lab.models import Message, Policy
from bot_eval_lab.retrieval import LexicalRetriever


def test_lexical_tie_is_stable_even_with_reversed_input():
    policies = [Policy("B", "Reembolso", "Reembolso aprovado"), Policy("A", "Reembolso", "Reembolso aprovado")]
    first, second = LexicalRetriever(policies), LexicalRetriever(list(reversed(policies)))
    assert first.search("REEMBÓLSO") == second.search("reembolso")
    assert [h.policy.id for h in first.search("reembolso")] == ["A", "B"]
    assert first.search("reembolso") == first.search("reembolso")


def test_lexical_empty_query_and_top_k(policies):
    search = LexicalRetriever(policies)
    assert search.search("a e o") == ()
    assert len(search.search("reembolso parceiro compra", k=2)) == 2


@pytest.mark.parametrize("text,action,reason", [
    ("Quero cancelar compra de parceiro antes do envio.", "handoff", "partner_review"),
    ("Quero trocar compra de parceiro recebida há 3 dias.", "handoff", "partner_review"),
    ("Quero cancelar.", "clarify", "seller_missing"),
    ("Quero cancelar compra direta da loja.", "clarify", "shipment_missing"),
    ("Quero trocar compra direta da loja.", "clarify", "receipt_age_missing"),
    ("Quero cancelar compra direta antes do envio.", "answer", "cancel_before_shipping"),
    ("Quero cancelar compra direta já enviada.", "handoff", "shipped_review"),
])
def test_decisions(assistant, text, action, reason):
    reply = assistant.respond((Message("user", text),))
    assert (reply.action, reply.reason) == (action, reason)
    assert set(reply.used) <= {hit.policy.id for hit in reply.retrieved}


def test_history_uses_latest_explicit_shipping_state(assistant):
    reply = assistant.respond((Message("user", "Cancelar compra direta já enviada."),
                               Message("assistant", "Confira a etapa."),
                               Message("user", "Corrigindo, ainda não foi enviada.")))
    assert reply.action == "answer"


def test_assistant_does_not_treat_its_own_claim_as_customer_fact(assistant):
    reply = assistant.respond((Message("user", "Quero cancelar."),
                               Message("assistant", "A compra foi direta e não foi enviada.")))
    assert reply.reason == "seller_missing"


def test_bug_changes_retrieval_with_same_decision(policies):
    history = (Message("user", "Cancelar compra de parceiro antes do envio."),)
    reference = Assistant(LexicalRetriever(policies)).respond(history)
    candidate = Assistant(LexicalRetriever(policies, buggy=True)).respond(history)
    assert reference.action == "handoff"
    assert "P-PARCEIRO" in reference.used
    assert candidate.action == "answer"
    assert "reembolso automático" in candidate.text
    assert "P-PARCEIRO" not in {hit.policy.id for hit in candidate.retrieved}


def test_changing_gold_labels_and_case_id_does_not_change_prediction(assistant, inputs):
    import copy
    from bot_eval_lab.runner import evaluate

    dataset, corpus, _ = inputs
    subset = {**dataset, "cases": [copy.deepcopy(dataset["cases"][0])]}
    before = evaluate(assistant, subset, corpus)["results"][0]
    subset["cases"][0]["id"] = "a-completely-new-id"
    subset["cases"][0]["expected_action"] = "handoff"
    subset["cases"][0]["critical"] = True
    after = evaluate(assistant, subset, corpus)["results"][0]
    assert before["reply"] == after["reply"]
    assert before["checks"]["action_ok"] and not after["checks"]["action_ok"]
