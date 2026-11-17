"""Decisão e respostas determinísticas, compartilhadas por todas as buscas.

São regras didáticas, não um LLM nem um executor de cancelamentos/reembolsos.
"""

import re

from .models import Hit, Message, Reply
from .retrieval import Retriever
from .text import normalize, tokens

DECISION_VERSION = "rules-1.0"


def customer_text(history: tuple[Message, ...]) -> str:
    return "\n".join(m.text for m in history if m.role == "user")


def context(history: tuple[Message, ...]) -> dict:
    """Último valor explícito prevalece; falas do bot não viram fatos do cliente."""
    state = {"topic": None, "seller": None, "shipped": None,
             "days": None, "approved": None, "order": None}
    for message in history:
        if message.role != "user":
            continue
        text = normalize(message.text)
        words = tokens(text)
        for topic, triggers in [
            ("defect", {"defeito"}), ("return", {"troca"}),
            ("cancel", {"cancelamento"}), ("refund", {"reembolso"}),
            ("tracking", {"rastreio"}), ("delay", {"atraso"}),
            ("delivery", {"entrega", "frete"}),
        ]:
            if words & triggers:
                state["topic"] = topic
                break
        if re.search(r"nao (?:foi |e |era )?(?:de )?(?:um )?(?:vendedor )?parceiro", text):
            state["seller"] = "direct"
        elif words & {"parceiro", "terceiro"}:
            state["seller"] = "partner"
        elif re.search(r"diret[oa]|propria (?:loja|aurora)|vendido pela aurora", text):
            state["seller"] = "direct"
        if re.search(r"nao (?:foi |foi ainda |esta |saiu |foi mesmo )?(?:enviad[oa]|despachad[oa]|expedid[oa])|antes d[oa] (?:envio|expedicao)|ainda nao saiu", text):
            state["shipped"] = False
        elif re.search(r"(?:ja |foi |esta )?(?:enviad[oa]|despachad[oa]|expedid[oa])|em transporte", text):
            state["shipped"] = True
        if re.search(r"nao (?:foi |esta )?aprovad|aguardando analise|em analise|analise pendente", text):
            state["approved"] = False
        elif re.search(r"aprovad[oa]|aprovacao confirmada", text):
            state["approved"] = True
        days = re.search(r"\b(\d+)\s+dias?\b", text)
        if days:
            state["days"] = int(days.group(1))
        order = re.search(r"\b(?:pedido|numero|codigo)\s*(?:e\s*)?#?\s*([a-z]*\d{3,})\b", text)
        if order:
            state["order"] = order.group(1)
    return state


def decide(history: tuple[Message, ...], hits: tuple[Hit, ...]) -> Reply:
    state = context(history)
    available = {hit.policy.id for hit in hits}

    def reply(action, text, reason, used=()):
        return Reply(action, text, hits, tuple(used), reason)

    def grounded(action, text, reason, *policy_ids):
        if not set(policy_ids) <= available:
            return reply("handoff", "Vou encaminhar ao atendimento: não encontrei a política necessária para orientar com segurança.", "policy_missing")
        return reply(action, text, reason, policy_ids)

    topic = state["topic"]
    if topic is None:
        return reply("clarify", "Sou o assistente da loja fictícia Aurora. Sua dúvida é sobre entrega, troca, reembolso ou cancelamento?", "scope_or_topic")
    if topic == "defect":
        return grounded("handoff", "Vou encaminhar o produto com defeito para análise humana. Envie o número do pedido e uma descrição do problema; o reembolso depende da análise.", "defect_review", "P-DEFEITO")
    if topic in {"cancel", "refund", "return"}:
        if state["seller"] is None:
            return reply("clarify", "A compra foi vendida diretamente pela Aurora ou por um vendedor parceiro?", "seller_missing")
        if state["seller"] == "partner" and "P-PARCEIRO" in available:
            return grounded("handoff", "A compra é de um vendedor parceiro. Vou encaminhar à equipe responsável para análise antes de confirmar cancelamento, troca ou reembolso.", "partner_review", "P-PARCEIRO")
        # Ponto frágil deliberadamente visível na demo: se a exceção não veio
        # da busca, o fluxo continua pela regra geral. A candidata muda SOMENTE
        # o índice. Em produção, vendedor parceiro deveria ter um bloqueio próprio.
    if topic == "cancel":
        if state["shipped"] is None:
            return reply("clarify", "O pedido já foi enviado ou ainda está antes do envio?", "shipment_missing")
        if state["shipped"]:
            return grounded("handoff", "O pedido já foi enviado. Vou encaminhar para análise de interceptação ou devolução, sem confirmar o cancelamento.", "shipped_review", "P-ENVIADO")
        return grounded("answer", "Pela política fictícia, antes do envio o cancelamento tem reembolso automático integral em até 5 dias úteis. Solicite em Meus pedidos > Cancelar. Esta demo não executa a operação.", "cancel_before_shipping", "P-CANCELAR")
    if topic == "return":
        if state["days"] is None:
            return reply("clarify", "Há quantos dias corridos você recebeu o produto?", "receipt_age_missing")
        if state["days"] > 7:
            return grounded("handoff", "O recebimento ocorreu há mais de 7 dias. Vou encaminhar para análise humana das alternativas, sem garantir troca ou reembolso.", "late_return_review", "P-TROCA", "P-TROCA-ANALISE")
        return grounded("answer", "Para a compra direta recebida há até 7 dias corridos, abra a solicitação em Meus pedidos > Trocar ou devolver e mantenha os acessórios. O valor só é liberado após análise do item devolvido.", "return_window", "P-TROCA")
    if topic == "refund":
        if state["approved"] is None:
            return reply("clarify", "A análise do reembolso já foi aprovada ou ainda está pendente?", "approval_missing")
        if not state["approved"]:
            return grounded("handoff", "O reembolso está em análise. Vou encaminhar à equipe humana para acompanhar a solicitação; não há liberação confirmada antes da aprovação.", "refund_review", "P-REEMBOLSO-ANALISE")
        return grounded("answer", "Pela política fictícia, seu reembolso está garantido em até 5 dias úteis após a aprovação registrada. A demo apenas informa a regra e não movimenta valores.", "refund_approved", "P-REEMBOLSO")
    if topic == "tracking":
        if state["order"] is None:
            return reply("clarify", "Qual é o número do pedido que você quer rastrear?", "order_missing")
        return grounded("answer", f"Para o pedido {state['order']}, abra Meus pedidos > Acompanhar entrega. O código aparece após a expedição. Esta demo não consulta o status real.", "tracking_instructions", "P-RASTREIO")
    if topic == "delay":
        if state["days"] is None:
            return reply("clarify", "Quantos dias úteis se passaram desde a confirmação do pagamento?", "elapsed_days_missing")
        if state["days"] > 7:
            return grounded("handoff", "O prazo de 7 dias úteis foi ultrapassado. Vou encaminhar para investigação da entrega; não posso confirmar uma nova data sem análise.", "delivery_review", "P-ATRASO")
    return grounded("answer", "Na loja fictícia Aurora, a entrega leva de 3 a 7 dias úteis após a confirmação do pagamento. Esse prazo vale também para vendedores parceiros.", "delivery_window", "P-ENTREGA")


class Assistant:
    def __init__(self, retriever: Retriever, top_k: int = 4):
        if top_k < 1:
            raise ValueError("top_k deve ser positivo")
        self.retriever = retriever
        self.top_k = top_k

    def respond(self, history: tuple[Message, ...]) -> Reply:
        hits = self.retriever.search(customer_text(history), self.top_k)
        return decide(history, hits)
