from __future__ import annotations

import time

from runtime.memory import FunctionalMemory


def test_memory_recall_scores_recent_entries_higher():
    mem = FunctionalMemory(max_entries=10, decay_after=5.0)
    mem.add("note", "draft integration tests for memory", tags={"task"})
    time.sleep(0.01)
    mem.add("note", "write user documentation about memory", tags={"docs"})

    results = mem.recall("documentation", limit=1)
    assert results, "expected at least one recall result"
    assert "documentation" in results[0].text


def test_memory_graph_tracks_relations():
    mem = FunctionalMemory(max_entries=5)
    mem.add("note", "connect database client", tags={"system"})
    mem.add("note", "client handles retries", tags={"system"})

    neighbours = dict(mem.neighbours("client"))
    assert "database" in neighbours
    assert neighbours["database"] > 0


def test_memory_enforces_capacity():
    mem = FunctionalMemory(max_entries=2)
    mem.add("note", "first entry")
    mem.add("note", "second entry")
    mem.add("note", "third entry")

    recent = [entry.text for entry in mem.recent(limit=3)]
    assert "first entry" not in recent
    assert "third entry" in recent
