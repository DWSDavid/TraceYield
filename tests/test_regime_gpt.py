import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.regime_gpt import bounded_regime_read


def test_bounded_regime_read_degrades_without_llm_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    result = bounded_regime_read(
        documents=["Inflation remains elevated."],
        cache_path=tmp_path / "regime.json",
    )

    assert result["available"] is False
    assert result["numeric_bp_allowed"] is False
    assert result["regime"] == {
        "inflation": "neutral",
        "policy": "neutral",
        "growth": "neutral",
        "liquidity_supply": "neutral",
        "global_relative_value": "neutral",
    }
    assert result["key_quotes"] == []
    assert "degraded" in result["rationale"].lower()


def test_bounded_regime_read_clamps_categories_and_drops_numeric_bp(tmp_path):
    result = bounded_regime_read(
        documents=["sample"],
        cache_path=tmp_path / "regime.json",
        scorer=lambda _prompt: {
            "regime": {
                "inflation": "hot",
                "policy": "dovish",
                "growth": "recessionary",
                "liquidity_supply": "tight",
                "global_relative_value": "cheap",
            },
            "rationale": "Inflation quote matters.",
            "key_quotes": ["Inflation remains elevated."],
            "bp_move": -25,
        },
    )

    assert result["available"] is True
    assert result["numeric_bp_allowed"] is False
    assert result["regime"]["inflation"] == "hot"
    assert result["regime"]["policy"] == "dovish"
    assert result["regime"]["growth"] == "neutral"
    assert result["regime"]["liquidity_supply"] == "tight"
    assert result["regime"]["global_relative_value"] == "neutral"
    assert "bp_move" not in result
