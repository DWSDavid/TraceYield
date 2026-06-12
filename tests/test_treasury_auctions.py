import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.treasury_auctions import (
    auction_stress_asof,
    normalize_auction_records,
)


def test_normalize_auction_records_keeps_10y_30y_and_metrics():
    records = [
        {
            "auctionDate": "2026-05-12T00:00:00",
            "securityTerm": "10-Year",
            "type": "Note",
            "bidToCoverRatio": "2.40",
            "highYield": "4.468",
            "whenIssuedYield": "4.430",
            "indirectBidderAccepted": "26775518000",
            "totalAccepted": "51972791100",
            "offeringAmount": "42000000000",
        },
        {
            "auctionDate": "2026-05-08T00:00:00",
            "securityTerm": "3-Year",
            "type": "Note",
            "bidToCoverRatio": "2.50",
        },
        {
            "auctionDate": "2026-05-14T00:00:00",
            "securityTerm": "30-Year",
            "type": "Bond",
            "bidToCoverRatio": "2.20",
            "highYield": "4.900",
            "indirectBidderAccepted": "100",
            "totalAccepted": "200",
            "offeringAmount": "22000000000",
        },
    ]

    out = normalize_auction_records(records)

    assert out["tenor"].tolist() == ["10Y", "30Y"]
    assert out.loc[out["tenor"] == "10Y", "tail_bp"].iloc[0] == 3.8
    assert out.loc[out["tenor"] == "10Y", "indirect_pct"].iloc[0] > 50


def test_poor_auction_adds_positive_stress():
    dates = pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"])
    df = pd.DataFrame(
        {
            "auction_date": dates,
            "tenor": ["10Y", "10Y", "30Y"],
            "bid_to_cover": [2.8, 2.0, 1.9],
            "tail_bp": [-1.0, 4.0, 5.0],
            "indirect_pct": [75.0, 55.0, 50.0],
            "offering_amount": [40000000000, 42000000000, 22000000000],
        }
    )

    assert auction_stress_asof("2026-03-15", df=df) > 0
