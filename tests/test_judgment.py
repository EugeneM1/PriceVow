"""The judgment seam: rules by default, Jev behind a flag, and both
speaking the same interface."""

import pytest

from app.judgment import JevJudge, RuleBasedJudge, get_judge
from app.scope import Scope


def test_default_judge_is_rules(monkeypatch):
    monkeypatch.delenv("PRICEVOW_JUDGE", raising=False)
    assert isinstance(get_judge(), RuleBasedJudge)


def test_flag_selects_jev(monkeypatch):
    monkeypatch.setenv("PRICEVOW_JUDGE", "jev")
    assert isinstance(get_judge(), JevJudge)


def test_rules_judge_matches_gate():
    scope = Scope(
        linear_feet=20, material="cedar", damage_severity=2,
        gate_count=0, zip_code="90024", visibility_gaps=[],
    )
    decision = RuleBasedJudge().assess(scope)
    assert decision.binds  # same behavior as gate.assess, through the seam


def make_scope(**overrides) -> Scope:
    defaults = dict(
        linear_feet=20, material="cedar", damage_severity=2,
        gate_count=0, zip_code="90024", visibility_gaps=[],
    )
    defaults.update(overrides)
    return Scope(**defaults)


def test_jev_without_key_falls_back_to_rules(monkeypatch):
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    decision = JevJudge().assess(make_scope())
    assert decision.binds  # same answer the rules give for a clean scope
    assert any("rules fallback" in r for r in decision.reasons)


def test_jev_hard_invariants_never_reach_the_api(monkeypatch):
    # Severity 5 and oversize are code rules: no key, no network, no call.
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "key-should-never-be-used")
    def boom(*a, **k):
        raise AssertionError("API must not be called for hard-rule scopes")
    import requests
    monkeypatch.setattr(requests, "post", boom)
    severe = JevJudge().assess(make_scope(damage_severity=5))
    assert severe.risk_tier == "severe" and not severe.binds
    oversized = JevJudge().assess(make_scope(linear_feet=500))
    assert not oversized.binds


def test_jev_answers_map_onto_the_decision(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"answers": {
                "bindable": {"type": "noul", "noul": 0.97},
                "risk": {"type": "choice", "choice": "none"},
            }}

    import requests
    captured = {}
    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        captured["questions"] = set(json["questions"])
        return FakeResponse()
    monkeypatch.setattr(requests, "post", fake_post)

    decision = JevJudge().assess(make_scope())
    assert decision.binds and decision.bindable_prob == 0.97
    assert captured["model"] == "typesafe-ai/jev"
    assert captured["questions"] == {"bindable", "risk"}
    assert "ai-gateway.vercel.sh/typesafe" in captured["url"]


def test_jev_api_failure_degrades_to_rules(monkeypatch):
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "test-key")
    import requests
    def fail(*a, **k):
        raise requests.exceptions.ConnectionError("gateway down")
    monkeypatch.setattr(requests, "post", fail)
    decision = JevJudge().assess(make_scope())
    assert decision.binds  # rules still answer
    assert any("Jev unavailable" in r for r in decision.reasons)
