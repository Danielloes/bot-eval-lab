"""Orquestra avaliação; rótulos nunca são enviados ao assistente."""

import platform
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from . import __version__
from .dataset import fingerprint
from .decision import Assistant, DECISION_VERSION
from .evaluation import EVALUATOR_VERSION, assess, summarize
from .models import Message


def environment() -> dict:
    packages = {}
    for name in ("sentence-transformers", "transformers", "torch", "numpy"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": packages}


def evaluate(assistant: Assistant, dataset: dict, corpus: dict) -> dict:
    # Warm-up fixo sem caso ou rótulo; custo excluído das amostras.
    assistant.respond((Message("user", "Qual é o prazo de entrega?"),))
    results = []
    for case in dataset["cases"]:
        history = tuple(Message(**m) for m in case["history"])
        started = time.perf_counter_ns()
        reply = assistant.respond(history)
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        results.append({"case": case, "reply": asdict(reply), "latency_ms": latency_ms,
                        "checks": assess(case, reply)})
    return {
        "id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assistant_version": f"bot-eval-lab-{__version__}/{DECISION_VERSION}",
        "evaluator_version": EVALUATOR_VERSION,
        "config": {**assistant.retriever.config, "top_k": assistant.top_k,
                   "warmup": "one fixed delivery question", "environment": environment()},
        "dataset": dataset, "dataset_hash": fingerprint(dataset),
        "corpus": corpus, "policy_hash": fingerprint(corpus),
        "results": results, "metrics": summarize(results),
    }
