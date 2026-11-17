"""Tipos visíveis ao assistente. Não há rótulos de avaliação neste módulo."""

from dataclasses import dataclass
from typing import Literal

Action = Literal["answer", "clarify", "handoff"]


@dataclass(frozen=True)
class Message:
    role: str
    text: str


@dataclass(frozen=True)
class Policy:
    id: str
    title: str
    text: str
    scope: str = "general"


@dataclass(frozen=True)
class Hit:
    policy: Policy
    score: float


@dataclass(frozen=True)
class Reply:
    action: Action
    text: str
    retrieved: tuple[Hit, ...]
    used: tuple[str, ...]
    reason: str
