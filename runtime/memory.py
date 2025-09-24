from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from typing import (
    Deque,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}


@dataclass
class MemoryEntry:
    """A single unit of stored context."""

    id: int
    kind: str
    text: str
    tokens: Sequence[str]
    vector: Mapping[str, float]
    created: float = field(default_factory=time.time)
    tags: frozenset[str] = field(default_factory=frozenset)
    importance: float = 1.0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "created": self.created,
            "tags": sorted(self.tags),
            "importance": self.importance,
            "metadata": dict(self.metadata),
        }


class FunctionalMemory:
    """Hybrid memory with vector and graph semantics."""

    def __init__(self, *, max_entries: int = 200, decay_after: float = 600.0):
        self.max_entries = max_entries
        self.decay_after = max(decay_after, 1.0)
        self._entries: Deque[MemoryEntry] = deque()
        self._next_id = 1
        self._graph: Dict[str, Dict[str, float]] = defaultdict(dict)

    # ------------------------------------------------------------------
    # ingestion helpers
    # ------------------------------------------------------------------
    def add(
        self,
        kind: str,
        text: str,
        *,
        tags: Optional[Iterable[str]] = None,
        importance: float = 1.0,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Optional[MemoryEntry]:
        text = text.strip()
        if not text:
            return None
        tokens = self._tokenize(text)
        if not tokens:
            return None
        vector = self._vectorize(tokens)
        entry = MemoryEntry(
            id=self._next_id,
            kind=kind,
            text=text,
            tokens=tokens,
            vector=vector,
            tags=frozenset(tags or ()),
            importance=max(importance, 0.0),
            metadata=dict(metadata or {}),
        )
        self._next_id += 1
        self._entries.append(entry)
        self._update_graph(entry, sign=1.0)
        self._enforce_limit()
        return entry

    def _enforce_limit(self) -> None:
        while len(self._entries) > self.max_entries:
            old = self._entries.popleft()
            self._update_graph(old, sign=-1.0)

    # ------------------------------------------------------------------
    # similarity search
    # ------------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        kind: Optional[str] = None,
        required_tags: Optional[Iterable[str]] = None,
    ) -> List[MemoryEntry]:
        query = query.strip()
        if not query:
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        q_vec = self._vectorize(tokens)
        tags = frozenset(t.lower() for t in (required_tags or ()))
        now = time.time()
        scored: List[tuple[float, MemoryEntry]] = []
        for entry in self._entries:
            if kind and entry.kind != kind:
                continue
            if tags and not tags.issubset({t.lower() for t in entry.tags}):
                continue
            sim = self._cosine(q_vec, entry.vector)
            if sim <= 0:
                continue
            age = max(now - entry.created, 0.0)
            recency = 1.0 / (1.0 + age / self.decay_after)
            graph_bonus = self._graph_bonus(entry, tokens)
            score = sim * (1.0 + 0.3 * entry.importance) * recency + graph_bonus
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[: max(limit, 0)]]

    def recent(
        self, limit: int = 10, *, kind: Optional[str] = None
    ) -> List[MemoryEntry]:
        out: List[MemoryEntry] = []
        for entry in reversed(self._entries):
            if kind and entry.kind != kind:
                continue
            out.append(entry)
            if len(out) >= limit:
                break
        return list(reversed(out))

    # ------------------------------------------------------------------
    # graph analytics
    # ------------------------------------------------------------------
    def graph_summary(self, limit: int = 5) -> List[str]:
        edges: Dict[tuple[str, str], float] = {}
        for left, neighbours in self._graph.items():
            for right, weight in neighbours.items():
                if weight <= 0:
                    continue
                key = tuple(sorted((left, right)))
                edges[key] = max(edges.get(key, 0.0), weight)
        pairs = sorted(edges.items(), key=lambda item: item[1], reverse=True)
        summary = []
        for (a, b), weight in pairs[: max(limit, 0)]:
            summary.append(f"{a} ⇄ {b} (weight={weight:.2f})")
        return summary

    def neighbours(self, token: str, *, limit: int = 5) -> List[tuple[str, float]]:
        token = token.lower()
        neighbours = self._graph.get(token)
        if not neighbours:
            return []
        data = sorted(neighbours.items(), key=lambda item: item[1], reverse=True)
        return data[: max(limit, 0)]

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _graph_bonus(self, entry: MemoryEntry, query_tokens: Sequence[str]) -> float:
        if not query_tokens:
            return 0.0
        bonus = 0.0
        entry_tokens = set(entry.vector.keys())
        for token in set(query_tokens):
            neighbours = self._graph.get(token)
            if not neighbours:
                continue
            for e_token in entry_tokens:
                weight = neighbours.get(e_token)
                if weight:
                    bonus += 0.01 * weight
        return bonus

    def _update_graph(self, entry: MemoryEntry, *, sign: float) -> None:
        unique_tokens = sorted(set(entry.tokens))
        if len(unique_tokens) < 2:
            return
        weight = max(entry.importance, 0.1) * sign
        for idx, left in enumerate(unique_tokens):
            left = left.lower()
            neighbours: MutableMapping[str, float] = self._graph.setdefault(left, {})
            for right in unique_tokens[idx + 1 :]:
                right = right.lower()
                neighbours[right] = neighbours.get(right, 0.0) + weight
                mirror = self._graph.setdefault(right, {})
                mirror[left] = mirror.get(left, 0.0) + weight
                if neighbours[right] <= 0:
                    neighbours.pop(right, None)
                if mirror[left] <= 0:
                    mirror.pop(left, None)
            if not neighbours:
                self._graph.pop(left, None)

    @staticmethod
    def _cosine(a: Mapping[str, float], b: Mapping[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for key, value in a.items():
            norm_a += value * value
            if key in b:
                dot += value * b[key]
        for value in b.values():
            norm_b += value * value
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / math.sqrt(norm_a * norm_b)

    @staticmethod
    def _tokenize(text: str) -> Sequence[str]:
        tokens = [tok.lower() for tok in re.findall(r"[a-zA-Z0-9']+", text)]
        return [tok for tok in tokens if tok and tok not in _STOPWORDS]

    @staticmethod
    def _vectorize(tokens: Sequence[str]) -> Mapping[str, float]:
        counts = Counter(tokens)
        if not counts:
            return {}
        norm = math.sqrt(sum(freq * freq for freq in counts.values()))
        if norm <= 0:
            return {}
        return {token: freq / norm for token, freq in counts.items()}


__all__ = ["FunctionalMemory", "MemoryEntry"]
