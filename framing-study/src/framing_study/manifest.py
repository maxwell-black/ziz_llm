"""Run manifest. The schedule is written before any generation.

Resume loads the saved JSON and does not rebuild the schedule.
Comparisons are the planned contrasts, stored before scores exist.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from framing_study.budget import calls_for_schedule, estimate_run
from framing_study.catalog import (
    AGENT,
    COMPARISONS,
    CONDITIONS,
    DATASET_REPO,
    HARBOR_SYSTEM_PROMPT_NOTE,
    NATIVE_JUDGE_PANEL,
    pilot_groups,
    smoke_group,
)
from framing_study.schedule import build_schedule, repetition_indexes


def read_pins() -> dict | None:
    """Import code and dataset SHAs from ``framing_study.pins``.

    Returns None when that module is not importable or has no SHAs.
    """
    try:
        import framing_study.pins as pins
    except ImportError:
        return None
    code = _first(pins, "CODE_SHA", "code_sha", "CODE_PIN")
    dataset = _first(pins, "DATASET_SHA", "dataset_sha", "DATASET_PIN")
    blob = getattr(pins, "PINS", None)
    if isinstance(blob, dict):
        code = code or blob.get("code_sha") or blob.get("CODE_SHA")
        dataset = dataset or blob.get("dataset_sha") or blob.get("DATASET_SHA")
    repo = _first(pins, "DATASET_REPO", "HF_REPO_ID", "dataset_repo") or DATASET_REPO
    if isinstance(blob, dict) and not _first(pins, "DATASET_REPO", "HF_REPO_ID", "dataset_repo"):
        repo = blob.get("dataset_repo") or blob.get("DATASET_REPO") or repo
    if not code or not dataset:
        return None
    return {
        "code_sha": str(code),
        "dataset_sha": str(dataset),
        "dataset_repo": str(repo),
    }


def _first(module: object, *names: str) -> str | None:
    for name in names:
        value = getattr(module, name, None)
        if value:
            return str(value)
    return None


def transform_identity() -> str | None:
    """SHA-256 of ``transform.py``. None when the module is not installed."""
    try:
        import framing_study.transform as transform_mod
    except ImportError:
        return None
    path = getattr(transform_mod, "__file__", None)
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def study_settings(config: dict) -> dict:
    return {
        "agent": config.get("agent") or AGENT,
        "harbor_version": str(config.get("harbor_version") or ""),
        "max_infrastructure_retries": int(config["max_infrastructure_retries"]),
        "n_concurrent": 1,
        "max_turns": (
            None if config.get("max_turns") in (None, "") else int(config["max_turns"])
        ),
        "max_tokens": None,
        "temperature": None,
        "judge_panel_override": False,
        "allows_uncontrolled_egress": bool(config.get("allows_uncontrolled_egress", False)),
    }


def build_manifest(
    *,
    scope: str,
    models: list[str],
    groups: list[dict],
    repetitions: int,
    seed: int,
    settings: dict,
    prices: dict,
    spend_limit: float | None,
    in_flight_usd: float,
    code_sha: str | None,
    dataset_sha: str | None,
    transform_sha: str | None,
    judge_panel: list[str],
    judge_panel_overridden: bool,
    conditions: list[str] | None = None,
) -> dict:
    condition_list = list(CONDITIONS if conditions is None else conditions)
    schedule = build_schedule(
        list(models),
        list(groups),
        condition_list,
        repetition_indexes(repetitions),
        seed,
    )
    generation_calls, judge_calls = calls_for_schedule(schedule, list(judge_panel))
    estimate = estimate_run(
        prices=prices,
        generation_calls=generation_calls,
        judge_calls=judge_calls,
    )
    return {
        "code_sha": code_sha,
        "dataset_sha": dataset_sha,
        "conditions": condition_list,
        "models": list(models),
        "settings": settings,
        "repetitions": repetitions,
        "seed": seed,
        "schedule": schedule,
        "pilot": {"groups": pilot_groups()},
        "smoke": {"group": smoke_group(), "scored": False},
        "scope": scope,
        "judge_panel": list(judge_panel or NATIVE_JUDGE_PANEL),
        "judge_panel_overridden": bool(judge_panel_overridden),
        "budget": {
            "prices_usd_per_million": prices,
            "assumptions": estimate["assumptions"],
            "estimate": {
                "known": estimate["known"],
                "generation_usd": estimate["generation_usd"],
                "judging_usd": estimate["judging_usd"],
                "infra_usd": estimate["infra_usd"],
                "total_usd": estimate["total_usd"],
                "missing_prices": estimate["missing_prices"],
                "infra_note": estimate["infra_note"],
            },
            "spend_limit_usd": spend_limit,
            "in_flight_usd": in_flight_usd,
            "in_flight_accounted": True,
        },
        "comparisons": [dict(row) for row in COMPARISONS],
        "instruction_transform_identity": transform_sha,
        "harbor_terminus2_system_prompt": {
            "controlled": False,
            "identical_across_conditions": True,
            "note": HARBOR_SYSTEM_PROMPT_NOTE,
        },
        "completed_slots": [],
    }


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def open_manifest(path: Path, rebuild) -> dict:
    """Return the on-disk manifest when it exists. ``rebuild`` is not called."""
    if path.is_file():
        return load_manifest(path)
    manifest = rebuild()
    save_manifest(path, manifest)
    return manifest
