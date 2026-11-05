"""Spend estimates from config prices only.

Empty ``prices_usd_per_million`` makes the estimate unknown. Token
ceilings below are planning assumptions, not measurements and not prices.
They are the same for every condition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Above the largest sampled agent-visible text budget in the dataset
# notes (~44k tokens). Identical for every condition and repetition.
PLANNING_ASSUMPTIONS: dict[str, object] = {
    "generation_input_tokens": 80_000,
    "generation_output_tokens": 64_000,
    "judge_input_tokens_per_call": 40_000,
    "judge_output_tokens_per_call": 8_000,
    "identical_across_conditions": True,
    "retries_not_prepaid": True,
    "note": (
        "Planning ceilings, not measured usage and not prices. "
        "The same ceilings are used for every condition. "
        "Infrastructure retries are not prepaid; a retry is reserved only "
        "when that extra attempt still fits the spend limit. "
        "Local Docker has no rate in prices_usd_per_million."
    ),
}


def _rates(prices: dict, model: str) -> tuple[float, float] | None:
    entry = prices.get(model)
    if not isinstance(entry, dict):
        return None
    incoming = entry.get("input", entry.get("input_usd_per_million"))
    outgoing = entry.get("output", entry.get("output_usd_per_million"))
    if incoming is None or outgoing is None:
        return None
    return float(incoming), float(outgoing)


def _token_cost(input_tokens: int, output_tokens: int, rates: tuple[float, float]) -> float:
    incoming, outgoing = rates
    return (input_tokens / 1_000_000) * incoming + (output_tokens / 1_000_000) * outgoing


def estimate_run(
    *,
    prices: dict,
    generation_calls: list[str],
    judge_calls: list[str],
    assumptions: dict | None = None,
) -> dict:
    """Estimate one scope. Unknown when prices are empty or a model has no rate."""
    assumptions = dict(PLANNING_ASSUMPTIONS if assumptions is None else assumptions)
    if not prices:
        return {
            "known": False,
            "generation_usd": None,
            "judging_usd": None,
            "infra_usd": None,
            "total_usd": None,
            "missing_prices": ["prices_usd_per_million is empty"],
            "assumptions": assumptions,
            "infra_note": "unknown because prices_usd_per_million is empty",
        }

    missing: list[str] = []
    generation_usd = 0.0
    generation_known = True
    for model in generation_calls:
        rates = _rates(prices, model)
        if rates is None:
            missing.append(model)
            generation_known = False
            continue
        generation_usd += _token_cost(
            int(assumptions["generation_input_tokens"]),
            int(assumptions["generation_output_tokens"]),
            rates,
        )

    judging_usd = 0.0
    judging_known = True
    for model in judge_calls:
        rates = _rates(prices, model)
        if rates is None:
            missing.append(model)
            judging_known = False
            continue
        judging_usd += _token_cost(
            int(assumptions["judge_input_tokens_per_call"]),
            int(assumptions["judge_output_tokens_per_call"]),
            rates,
        )

    known = generation_known and judging_known
    infra_usd = 0.0 if known else None
    total = None
    if known and infra_usd is not None:
        total = generation_usd + judging_usd + infra_usd
    return {
        "known": known,
        "generation_usd": round(generation_usd, 6) if generation_known else None,
        "judging_usd": round(judging_usd, 6) if judging_known else None,
        "infra_usd": infra_usd,
        "total_usd": round(total, 6) if total is not None else None,
        "missing_prices": sorted(set(missing)),
        "assumptions": assumptions,
        "infra_note": (
            "0 USD; local Docker is unmetered because prices_usd_per_million "
            "has no infra rate"
            if known
            else "infra is not added while a token price is missing"
        ),
    }


def calls_for_schedule(schedule: list[dict], judge_models: list[str]) -> tuple[list[str], list[str]]:
    generations: list[str] = []
    judges: list[str] = []
    for slot in schedule:
        generations.append(slot["model"])
        for _grade in slot["grades"]:
            judges.extend(judge_models)
    return generations, judges


@dataclass(frozen=True)
class SpendDecision:
    allowed: bool
    reason: str
    estimate_usd: float | None
    in_flight_usd: float
    spend_limit: float | None

    @property
    def projected_usd(self) -> float | None:
        if self.estimate_usd is None:
            return None
        return self.estimate_usd + self.in_flight_usd


def decide_spend(
    *,
    estimate_usd: float | None,
    spend_limit: float | None,
    in_flight_usd: float = 0.0,
) -> SpendDecision:
    """Refuse unless the limit is an explicit non-negative number and the sum fits.

    A missing limit is a refusal. It is not treated as zero.
    """
    if spend_limit is None:
        return SpendDecision(
            False,
            "missing spend limit",
            estimate_usd,
            in_flight_usd,
            None,
        )
    if spend_limit < 0:
        return SpendDecision(
            False,
            "spend limit must be an explicit non-negative number",
            estimate_usd,
            in_flight_usd,
            spend_limit,
        )
    if estimate_usd is None:
        return SpendDecision(
            False,
            "estimate is unknown",
            None,
            in_flight_usd,
            spend_limit,
        )
    if in_flight_usd < 0:
        return SpendDecision(
            False,
            "in-flight reservation is negative",
            estimate_usd,
            in_flight_usd,
            spend_limit,
        )
    projected = estimate_usd + in_flight_usd
    if projected > spend_limit + 1e-9:
        return SpendDecision(
            False,
            "estimate plus in-flight exceeds spend limit",
            estimate_usd,
            in_flight_usd,
            spend_limit,
        )
    return SpendDecision(
        True,
        "within spend limit",
        estimate_usd,
        in_flight_usd,
        spend_limit,
    )


class InFlightLedger:
    """Reservations for runs that have started and not yet finished."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"reservations": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def total(self, *, exclude: str | None = None) -> float:
        data = self._read()
        total = 0.0
        for key, usd in (data.get("reservations") or {}).items():
            if key == exclude:
                continue
            total += float(usd)
        return total

    def set_reservation(self, run_id: str, usd: float) -> None:
        data = self._read()
        reservations = data.setdefault("reservations", {})
        reservations[run_id] = usd
        self._write(data)

    def release(self, run_id: str) -> None:
        data = self._read()
        (data.get("reservations") or {}).pop(run_id, None)
        self._write(data)


def format_cost_report(scope: str, estimate: dict, *, in_flight_usd: float = 0.0) -> str:
    def money(value: float | None) -> str:
        if value is None:
            return "unknown"
        return f"{value:.6f}"

    lines = [
        f"scope: {scope}",
        f"generation_usd: {money(estimate['generation_usd'])}",
        f"judging_usd: {money(estimate['judging_usd'])}",
        f"infra_usd: {money(estimate['infra_usd'])}",
        f"total_usd: {money(estimate['total_usd'])}",
        f"in_flight_usd: {in_flight_usd:.6f}",
        f"infra: {estimate['infra_note']}",
        "assumptions:",
        json.dumps(estimate["assumptions"], indent=2, sort_keys=True),
    ]
    if estimate["missing_prices"]:
        lines.append("missing_prices: " + ", ".join(estimate["missing_prices"]))
    if not estimate["known"]:
        lines.append("estimate: unknown")
    return "\n".join(lines) + "\n"
