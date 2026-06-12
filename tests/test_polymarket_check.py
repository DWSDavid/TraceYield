import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.polymarket_check import (
    PolymarketGammaProvider,
    attach_polymarket_check,
)


def _trajectory() -> dict:
    ten_year = []
    for month in range(1, 13):
        central = 4.43 - 0.01 * month
        ten_year.append(
            {
                "month": month,
                "current": 4.43,
                "central": central,
                "p10": central - 0.30,
                "p25": central - 0.15,
                "p50": central,
                "p75": central + 0.15,
                "p90": central + 0.30,
            }
        )
    return {
        "as_of": "2026-05-30",
        "tenors": {"10Y": ten_year},
        "metadata": {},
    }


def _search_payload() -> dict:
    return {
        "events": [
            {
                "id": "79104",
                "slug": "how-high-will-10-year-treasury-yield-go-before-2027",
                "title": "How high will 10-year Treasury yield go before 2027?",
                "active": True,
                "closed": False,
                "markets": [
                    {
                        "id": "m48",
                        "slug": "will-the-10-year-treasury-yield-hit-4pt8-before-2027",
                        "question": "Will the 10-year Treasury yield hit 4.8% before 2027?",
                        "description": "Resolves Yes if the 10-year yield reaches 4.8%.",
                        "endDate": "2026-12-31T00:00:00Z",
                        "active": True,
                        "closed": False,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.245", "0.755"]',
                        "volume": "50000",
                        "liquidity": "1181",
                        "spread": "0.03",
                        "lastTradePrice": 0.25,
                        "bestBid": 0.23,
                        "bestAsk": 0.26,
                    }
                ],
            },
            {
                "id": "79123",
                "slug": "how-low-will-10-year-treasury-yield-get-before-2027",
                "title": "How low will 10-year Treasury yield get before 2027?",
                "active": True,
                "closed": False,
                "markets": [
                    {
                        "id": "m39",
                        "slug": "will-the-10-year-treasury-yield-dip-below-3pt9-before-2027",
                        "question": "Will the 10-year Treasury yield dip below 3.9% before 2027?",
                        "description": "Resolves Yes if the 10-year yield dips below 3.9%.",
                        "endDate": "2026-12-31T00:00:00Z",
                        "active": True,
                        "closed": False,
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.475", "0.525"]',
                        "volume": "40796",
                        "liquidity": "7208",
                        "spread": "0.01",
                        "lastTradePrice": 0.47,
                        "bestBid": 0.47,
                        "bestAsk": 0.48,
                    }
                ],
            },
        ]
    }


def test_polymarket_provider_returns_contract_and_alignment(tmp_path):
    calls = []

    def fetcher(url: str) -> dict:
        calls.append(url)
        return _search_payload()

    result = PolymarketGammaProvider(fetcher=fetcher).get_check(
        _trajectory(),
        snapshot_dir=tmp_path,
    )

    assert result["source"] == "polymarket_gamma"
    assert result["status"] == "available"
    assert result["model_usage"] == "external_check_only_no_central_shift"
    assert result["traceyield_alignment"] == "agree"
    assert "external check only" in result["alignment_reason"].lower()
    assert len(result["markets"]) == 2
    dip_market = next(
        market for market in result["markets"] if "dip-below-3pt9" in market["slug"]
    )
    assert dip_market["yes_price"] == 0.475
    assert dip_market["relevance_score"] >= 0.80
    assert dip_market["confidence"] in {"med", "high"}
    assert calls

    latest = tmp_path / "polymarket_check_latest.json"
    assert latest.exists()
    saved = json.loads(latest.read_text(encoding="utf-8"))
    assert saved["contract"]["model_usage"] == "external_check_only_no_central_shift"
    assert saved["raw_responses"]


def test_polymarket_provider_degrades_when_no_relevant_market():
    result = PolymarketGammaProvider(
        fetcher=lambda _url: {
            "events": [
                {
                    "title": "New Rihanna Album before GTA VI?",
                    "markets": [
                        {
                            "id": "music",
                            "question": "New Rihanna Album before GTA VI?",
                            "active": True,
                            "closed": False,
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.2", "0.8"]',
                        }
                    ],
                }
            ]
        }
    ).get_check(_trajectory(), save_snapshot=False)

    assert result["status"] == "no_relevant_market"
    assert result["markets"] == []
    assert result["traceyield_alignment"] == "unavailable"


def test_attach_polymarket_check_does_not_change_curve_values(tmp_path):
    base = _trajectory()
    before = json.dumps(base["tenors"], sort_keys=True)

    adjusted = attach_polymarket_check(
        base,
        provider=PolymarketGammaProvider(fetcher=lambda _url: _search_payload()),
        snapshot_dir=tmp_path,
    )

    assert json.dumps(adjusted["tenors"], sort_keys=True) == before
    assert "polymarket_check" in adjusted["metadata"]
    assert base["metadata"] == {}
