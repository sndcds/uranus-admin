"""Bounded process-local, session-bound state. Tokens are random, not encoded semantics."""

import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic

from app.errors import APIError
from app.research.answer_facts import AnswerFacts
from app.research.wire.research_v13_schema import AnswerLanguage
from app.schemas.research_conversation_v12 import (
    ResearchConversationContextV12,
    ResearchPlanSummaryV12,
)


@dataclass(slots=True)
class ConversationState:
    owner: str
    expires: float
    language: AnswerLanguage = "de"
    summaries: list[ResearchPlanSummaryV12] = field(default_factory=list)
    pending: ResearchPlanSummaryV12 | None = None
    facts: AnswerFacts | None = None
    turns: int = 0
    busy: bool = False

    def context(self) -> ResearchConversationContextV12 | None:
        return (
            ResearchConversationContextV12(previous_turns=self.summaries)
            if self.summaries
            else None
        )

    def remember(self, summary: ResearchPlanSummaryV12 | None) -> None:
        if summary is None:
            self.summaries = []
            return
        summaries = [*self.summaries, summary][-4:]
        # Envelope overhead can push four individually valid summaries over 8192 bytes.
        while summaries:
            try:
                ResearchConversationContextV12(previous_turns=summaries)
                break
            except ValueError:
                summaries.pop(0)
        self.summaries = summaries


class ConversationStore:
    def __init__(
        self,
        *,
        ttl: int = 1800,
        capacity: int = 256,
        per_session: int = 8,
        clock: Callable[[], float] = monotonic,
    ):
        self.ttl = ttl
        self.capacity = capacity
        self.per_session = per_session
        self.clock = clock
        self.entries: dict[str, ConversationState] = {}

    @contextmanager
    def turn(self, owner: str, token: str | None) -> Iterator[tuple[str, ConversationState, bool]]:
        now = self.clock()
        for key in list(self.entries):
            if self.entries[key].expires <= now and not self.entries[key].busy:
                del self.entries[key]
        state = self.entries.get(token or "")
        expired = token is not None and (state is None or state.owner != owner)
        if state is None or state.owner != owner:
            owned = [(key, value) for key, value in self.entries.items() if value.owner == owner]
            if len(owned) >= self.per_session:
                self._evict(owned)
            if len(self.entries) >= self.capacity:
                self._evict(list(self.entries.items()))
            token = secrets.token_urlsafe(32)
            state = ConversationState(owner=owner, expires=now + self.ttl)
            self.entries[token] = state
        if state.busy:
            raise APIError(
                503, "research_planner_unavailable", "A conversation turn is already running."
            )
        assert token is not None
        state.busy = True
        try:
            yield token, state, expired
        finally:
            state.busy = False
            state.expires = self.clock() + self.ttl

    def _evict(self, entries: list[tuple[str, ConversationState]]) -> None:
        idle = [(key, state) for key, state in entries if not state.busy]
        if not idle:
            raise APIError(503, "research_planner_unavailable", "Conversation capacity reached.")
        key, _ = min(idle, key=lambda item: item[1].expires)
        del self.entries[key]
