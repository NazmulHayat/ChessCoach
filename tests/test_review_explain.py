"""Optional Claude explanations: off without a key, and the request carries only computed facts."""

import asyncio
from types import SimpleNamespace

import anthropic

from ep_model.review import explain

MOVE = {
    "mover": "black", "move_number": 5, "san": "Bxd1", "ep_label": "blunder", "fen_before": "8/8/8/8/8/8/8/K6k b - - 0 1",
    "ep_best": 0.33, "ep_after": 0.06, "best_san": "dxe5", "best_line_san": ["dxe5", "Qxg4"], "second_san": "Be6",
    "tactic": "allows mate in 2", "sacrifice": 0,
}


def test_enabled_follows_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert not explain.enabled()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert explain.enabled()


def test_explain_sends_facts_and_returns_text(monkeypatch):
    sent = {}

    class FakeMessages:
        async def create(self, **kw):
            sent.update(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Bxd1 walks into mate.")])

    class FakeClient:
        def __init__(self, **kw):
            self.beta = SimpleNamespace(messages=FakeMessages())

        async def close(self):
            pass

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    text = asyncio.run(explain.explain_move(MOVE, {"White": "Alice", "Black": "Bob"}, 1500))
    assert text == "Bxd1 walks into mate."
    facts = sent["messages"][0]["content"]
    assert "5... Bxd1" in facts and "dxe5 Qxg4" in facts and "allows mate in 2" in facts and "Bob" in facts
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"


def test_refusal_becomes_friendly_error(monkeypatch):
    class FakeMessages:
        async def create(self, **kw):
            return SimpleNamespace(stop_reason="refusal", content=[])

    class FakeClient:
        def __init__(self, **kw):
            self.beta = SimpleNamespace(messages=FakeMessages())

        async def close(self):
            pass

    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeClient)
    try:
        asyncio.run(explain.explain_move(MOVE, {}, None))
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "No explanation" in str(e)
