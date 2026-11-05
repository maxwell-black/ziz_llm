"""Deterministic trial order.

Within each model, shuffle input groups. Within each group, shuffle
conditions, then repetitions. Models stay in the configured order.
The same seed rebuilds the same permutation. Resume must not call this
again; it reuses the schedule already stored in the manifest.
"""

from __future__ import annotations

import random

from framing_study.catalog import task_id_for


def repetition_indexes(repetitions: int) -> list[int]:
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    return list(range(repetitions))


def _grade_task_id(group: dict, variant: str) -> str:
    by_variant = group.get("task_ids_by_variant") or {}
    if variant in by_variant:
        return by_variant[variant]
    task_ids = group.get("task_ids") or []
    variants = list(group["variants"])
    if task_ids and len(task_ids) == len(variants):
        return task_ids[variants.index(variant)]
    return task_id_for(group["group_id"], variant)


def build_schedule(
    models: list[str],
    groups: list[dict],
    conditions: list[str],
    repetitions: list[int],
    seed: int,
) -> list[dict]:
    """One generation slot per group, model, condition, and repetition.

    Each slot carries one grade entry per variant. Variants are not
    separate generations.
    """
    rng = random.Random(seed)
    slots: list[dict] = []
    for model in models:
        group_order = list(groups)
        rng.shuffle(group_order)
        for group in group_order:
            condition_order = list(conditions)
            rng.shuffle(condition_order)
            for condition in condition_order:
                rep_order = list(repetitions)
                rng.shuffle(rep_order)
                for repetition in rep_order:
                    grades = [
                        {
                            "task_id": _grade_task_id(group, variant),
                            "variant": variant,
                        }
                        for variant in group["variants"]
                    ]
                    representative = group.get("representative") or grades[0]["task_id"]
                    slots.append(
                        {
                            "model": model,
                            "group_id": group["group_id"],
                            "condition": condition,
                            "repetition": repetition,
                            "representative_task": representative,
                            "grades": grades,
                        }
                    )
    return slots


def generation_slot_id(slot: dict) -> str:
    model = str(slot["model"]).replace("/", "__")
    return (
        f"{model}__{slot['group_id']}__{slot['condition']}__r{slot['repetition']}"
    )


def schedule_keys(schedule: list[dict]) -> list[tuple]:
    return [
        (slot["model"], slot["group_id"], slot["condition"], slot["repetition"])
        for slot in schedule
    ]
