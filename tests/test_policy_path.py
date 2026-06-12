import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.signals.policy_path import (
    AtlantaFedPolicyPathProvider,
    FredProxyPolicyPathProvider,
    OisPaidPolicyPathProvider,
    merge_policy_paths,
)


def _policy_history() -> pd.DataFrame:
    dates = pd.date_range("2026-05-29", periods=3, freq="D")
    return pd.DataFrame(
        {
            "DFEDTARU": [3.75, 3.75, 3.75],
            "EFFR": [3.64, 3.64, 3.64],
            "DGS3MO": [3.50, 3.50, 3.50],
            "DGS6MO": [3.40, 3.40, 3.40],
            "DGS1": [3.20, 3.20, 3.20],
            "DGS2": [3.10, 3.10, 3.10],
            "DGS5": [3.30, 3.30, 3.30],
            "FEDTARMD": [3.40, 3.40, 3.40],
            "FEDTARMDLR": [3.00, 3.00, 3.00],
        },
        index=dates,
    )


def _bill_basis_history() -> pd.DataFrame:
    dates = pd.date_range("2026-05-29", periods=3, freq="D")
    return pd.DataFrame(
        {
            "DFEDTARU": [3.75, 3.75, 3.75],
            "EFFR": [3.64, 3.64, 3.64],
            "DGS3MO": [3.86, 3.86, 3.86],
            "DGS6MO": [3.875, 3.875, 3.875],
            "DGS1": [3.90, 3.90, 3.90],
            "DGS2": [3.95, 3.95, 3.95],
            "DGS5": [4.05, 4.05, 4.05],
            "FEDTARMD": [3.40, 3.40, 3.40],
            "FEDTARMDLR": [3.00, 3.00, 3.00],
        },
        index=dates,
    )


def test_fred_proxy_contract_uses_short_forward_formula_and_dot_gap():
    result = FredProxyPolicyPathProvider().get_policy_path(
        _policy_history(),
        as_of=pd.Timestamp("2026-06-02"),
    )

    assert result["source"] == "fred_proxy"
    assert result["next_meeting_date"] == pd.Timestamp("2026-06-17").date()
    assert result["next_meeting_cut_prob"] is None
    assert result["implied_policy_rate_3m"] == 3.50
    assert result["implied_policy_rate_6m"] == 3.30
    assert result["implied_policy_rate_12m"] == 3.00
    assert result["fed_dot_median_path"]["2026"] == 3.40
    assert result["fed_dot_median_path"]["longer_run"] == 3.00
    assert result["market_vs_fed_gap_bp"] == -10.0
    assert result["direction"] == "EASING"
    assert result["confidence"] == "low"
    assert "proxy" in result["reason"].lower()


def test_fred_proxy_holds_small_positive_bill_basis_and_keeps_dot_gap_signal():
    result = FredProxyPolicyPathProvider().get_policy_path(
        _bill_basis_history(),
        as_of=pd.Timestamp("2026-06-02"),
    )

    assert result["implied_policy_rate_6m"] == 3.89
    assert result["market_vs_fed_gap_bp"] == 49.0
    assert result["direction"] == "HOLD"
    assert result["confidence"] == "low"
    assert "bill-vs-funds basis" in result["reason"].lower()


def test_fedwatch_csv_overrides_probability_fields_and_keeps_fred_path(tmp_path):
    manual = tmp_path / "fedwatch_latest.csv"
    manual.write_text(
        "meeting_date,cut25_prob,cut50_prob,hold_prob,hike_prob,implied_rate\n"
        "2026-06-17,0.40,0.25,0.30,0.05,3.25\n",
        encoding="utf-8",
    )
    merged = merge_policy_paths(
        _policy_history(),
        as_of=pd.Timestamp("2026-06-02"),
        fedwatch_csv=manual,
        atlanta_provider=AtlantaFedPolicyPathProvider(fetcher=lambda _url: None),
    )

    assert merged["source"] == "fedwatch_csv"
    assert merged["next_meeting_cut_prob"] == 0.65
    assert merged["next_meeting_hold_prob"] == 0.30
    assert merged["next_meeting_hike_prob"] == 0.05
    assert merged["expected_target_rate_after_meeting"] == 3.25
    assert merged["implied_policy_rate_6m"] == 3.30
    assert "FedWatch CSV" in merged["reason"]


def test_atlanta_high_cut_probability_overrides_fred_proxy_direction(tmp_path):
    payload = {
        "ResearchData": [
            {
                "Indicator": "72.0%",
                "UpdatedDate": "2026-05-28T15:30:00",
                "Name": "Market Probability of a Rate Cut by 2026-06-17",
                "IconAlias": "MPT",
            }
        ]
    }

    merged = merge_policy_paths(
        _bill_basis_history(),
        as_of=pd.Timestamp("2026-06-02"),
        fedwatch_csv=tmp_path / "fedwatch_latest.csv",
        atlanta_provider=AtlantaFedPolicyPathProvider(fetcher=lambda _url: payload),
    )

    assert merged["source"] == "atlanta_mpt_object_pod"
    assert merged["next_meeting_cut_prob"] == 0.72
    assert merged["expected_target_rate_after_meeting"] is None
    assert merged["direction"] == "EASING"
    assert merged["market_vs_fed_gap_bp"] == 49.0


def test_atlanta_provider_degrades_when_feed_unavailable():
    result = AtlantaFedPolicyPathProvider(
        fetcher=lambda _url: (_ for _ in ()).throw(RuntimeError("blocked"))
    ).get_policy_path(_policy_history(), as_of=pd.Timestamp("2026-06-02"))

    assert result["source"] == "atlanta_mpt_unavailable"
    assert result["next_meeting_cut_prob"] is None
    assert result["implied_policy_rate_6m"] is None
    assert "unavailable" in result["reason"].lower()
    assert result["confidence"] == "low"


def test_atlanta_provider_parses_object_pod_cut_probability():
    payload = {
        "ResearchData": [
            {
                "Indicator": "1.34%",
                "UpdatedDate": "2026-05-28T15:30:00",
                "Name": "Market Probability of a Rate Cut by 2026-06-17",
                "IconAlias": "MPT",
            }
        ]
    }

    result = AtlantaFedPolicyPathProvider(fetcher=lambda _url: payload).get_policy_path(
        _policy_history(),
        as_of=pd.Timestamp("2026-06-02"),
    )

    assert result["source"] == "atlanta_mpt_object_pod"
    assert result["next_meeting_date"] == pd.Timestamp("2026-06-17").date()
    assert result["next_meeting_cut_prob"] == 0.0134
    assert result["confidence"] == "low"


def test_ois_provider_is_paid_data_stub():
    provider = OisPaidPolicyPathProvider()

    try:
        provider.get_policy_path(_policy_history(), as_of=pd.Timestamp("2026-06-02"))
    except NotImplementedError as exc:
        assert "paid data" in str(exc)
    else:
        raise AssertionError("OIS paid provider must not be implemented")
