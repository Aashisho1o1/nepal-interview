"""Provider usage pricing.

Usage quantities are stored exactly as metered. Cost is derived from a versioned
price table so historical rows keep the price that applied when they were settled.
Meters without a price stay "unpriced" rather than being guessed.

Rounding: each ledger row's cost is rounded half-up to whole USD micro-units
(1e-6 USD). Totals are sums of rounded rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

DEFAULT_PRICE_FILE = Path(__file__).resolve().parents[3] / "config" / "prices.json"


@dataclass(frozen=True)
class PriceTable:
    version: str
    usd_per_unit: dict[str, Decimal]
    fx_npr_per_usd: Decimal
    fx_as_of: str
    raw: dict[str, Any]

    def cost_usd_micros(self, meter: str, quantity: Decimal) -> int | None:
        price = self.usd_per_unit.get(meter)
        if price is None:
            return None
        return int((quantity * price * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def load_price_table(path: str | Path | None = None) -> PriceTable:
    data = json.loads(Path(path or DEFAULT_PRICE_FILE).read_text())
    prices = {
        k: Decimal(str(v["usd_per_unit"]))
        for k, v in data["meters"].items()
        if v.get("usd_per_unit") is not None
    }
    return PriceTable(
        version=data["version"],
        usd_per_unit=prices,
        fx_npr_per_usd=Decimal(str(data["fx"]["npr_per_usd"])),
        fx_as_of=data["fx"]["as_of"],
        raw=data,
    )
