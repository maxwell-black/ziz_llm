"""Frozen pilot and smoke input groups.

Task ids look like ``redline-s1-t1-g01a``. The input group is that id
without the final variant letter. Variants in one group share the
model-facing contract and instruction and differ in grader files.
Code and dataset SHAs are not stored here; they come from
``framing_study.pins``.
"""

from __future__ import annotations

import re

CONDITIONS: tuple[str, ...] = (
    "STOCK",
    "STOCK_PLUS_METAPHOR",
    "MATCHED_SOFTWARE_REPLACEMENT",
    "TASK_ONLY",
)

# Native verifier panel from the benchmark's tests/judge.py.
# This study does not set JUDGE_PANEL or JUDGE_MODEL.
NATIVE_JUDGE_PANEL: tuple[str, ...] = (
    "openai/gpt-5.4-mini",
    "anthropic/claude-haiku-4-5-20251001",
    "gemini/gemini-3.1-flash-lite",
)

CONFIG_JUDGE_PANEL: tuple[str, ...] = tuple(
    model.split("/", 1)[-1] for model in NATIVE_JUDGE_PANEL
)

JUDGE_SETTINGS: dict[str, object] = {
    "mode": "panel",
    "override": False,
    "max_tokens": None,
    "temperature": None,
}

COMPARISONS: tuple[dict[str, str], ...] = (
    {
        "name": "primary",
        "treatment": "MATCHED_SOFTWARE_REPLACEMENT",
        "control": "STOCK",
    },
    {
        "name": "secondary",
        "treatment": "STOCK_PLUS_METAPHOR",
        "control": "STOCK",
    },
    {
        "name": "stock_vs_task_only",
        "treatment": "STOCK",
        "control": "TASK_ONLY",
    },
    {
        "name": "matched_vs_task_only",
        "treatment": "MATCHED_SOFTWARE_REPLACEMENT",
        "control": "TASK_ONLY",
    },
)

AGENT = "terminus-2"
DATASET_REPO = "crosbylegal/RedlineBench"
DEFAULT_SEED = 20261105
DEFAULT_MAX_INFRASTRUCTURE_RETRIES = 2
HARBOR_VERSION_PIN = "0.25.0"

PROVIDER_ENV_NAMES: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
)

# Verifier-phase allowlist. Identical on every condition's task.toml.
# The agent baseline is no-network; these hosts are judge APIs only.
JUDGE_ALLOW_HOSTS: tuple[str, ...] = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
)

HARBOR_SYSTEM_PROMPT_NOTE = (
    "Harbor's own terminus-2 system prompt is outside this repo and "
    "uncontrolled, identical across conditions."
)

_TASK_ID = re.compile(r"^redline-(s\d+-t\d+-g\d+)([a-z])$")


def input_group_id(task_id: str) -> str:
    """Return the input group id for a RedlineBench task id."""
    match = _TASK_ID.match(task_id)
    if match is None:
        raise ValueError(f"not a redline task id: {task_id!r}")
    return match.group(1)


def variant_of(task_id: str) -> str:
    match = _TASK_ID.match(task_id)
    if match is None:
        raise ValueError(f"not a redline task id: {task_id!r}")
    return match.group(2)


def task_id_for(group_id: str, variant: str) -> str:
    if len(variant) != 1 or not variant.isalpha() or not variant.islower():
        raise ValueError(f"variant must be one lowercase letter, got {variant!r}")
    return f"redline-{group_id}{variant}"


def _group(
    group_id: str,
    variants: str,
    *,
    acceptance_oriented: bool = False,
    scored: bool = True,
) -> dict:
    letters = tuple(variants)
    if "a" not in letters:
        raise ValueError(f"{group_id} is missing representative variant a")
    return {
        "group_id": group_id,
        "variants": list(letters),
        "representative": task_id_for(group_id, "a"),
        "task_ids": [task_id_for(group_id, letter) for letter in letters],
        "acceptance_oriented": acceptance_oriented,
        "scored": scored,
    }


def pilot_groups() -> list[dict]:
    """Scored pilot. Generate once per group, then grade every variant."""
    return [
        _group("s1-t1-g01", "abcde"),
        _group("s2-t2-g01", "abc"),
        _group("s1-t3-g01", "a"),
        _group("s3-t2-g01", "abc"),
        _group("s2-t4-g03", "a", acceptance_oriented=True),
        _group("s3-t4-g01", "a", acceptance_oriented=True),
    ]


def smoke_group() -> dict:
    """Disjoint harness check. Not a scored cell."""
    return _group("s2-t1-g01", "abcd", scored=False)


def groups_for_scope(scope: str) -> list[dict]:
    if scope == "pilot":
        return pilot_groups()
    if scope == "smoke":
        return [smoke_group()]
    raise ValueError(f"unknown scope: {scope}")


def fetch_task_ids() -> list[str]:
    """Pilot and smoke variant directories. No other tasks."""
    ids: list[str] = []
    for group in [*pilot_groups(), smoke_group()]:
        ids.extend(group["task_ids"])
    return ids


def representative_tasks() -> list[dict]:
    rows = [{**group, "scope": "pilot"} for group in pilot_groups()]
    rows.append({**smoke_group(), "scope": "smoke"})
    return rows


def judge_panel_status(config_names: list[str] | tuple[str, ...]) -> dict:
    names = tuple(config_names)
    if names != CONFIG_JUDGE_PANEL:
        return {
            "ok": False,
            "overridden": True,
            "ids": list(NATIVE_JUDGE_PANEL),
            "reason": (
                "config judge_panel does not match the native default panel; "
                "this study does not override JUDGE_PANEL"
            ),
        }
    return {
        "ok": True,
        "overridden": False,
        "ids": list(NATIVE_JUDGE_PANEL),
        "reason": "native default panel; JUDGE_PANEL is not set",
    }


def comparisons_match(rows: list[dict] | None) -> bool:
    if not rows:
        return False
    normalized = [
        {
            "name": row.get("name"),
            "treatment": row.get("treatment"),
            "control": row.get("control"),
        }
        for row in rows
    ]
    return normalized == [dict(row) for row in COMPARISONS]
