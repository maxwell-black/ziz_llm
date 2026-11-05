"""Native RedlineBench rewards for the instruction study.

The benchmark package is not imported. The reward for one variant is

    clamp((P - Q) / W, 0, 1)

where W is the sum of positive rubric weights, P is the sum of those
positive weights whose rubric voted PASS, and Q is the sum of the absolute
weights of penalty rubrics that voted PASS. A rubric votes PASS only when
``n_pass * 2 > n_voters``. A missing verdict counts as FAIL. A penalty rubric
is one with a negative weight.

An input-group score is the mean of variant rewards for one generation. If
any variant in that generation is gate-failed, missing a judge, or invalid,
the generation has no score. Repetitions are repeated measures of that same
contract: the group score averages the scored repetitions and leaves failed
repetitions out. It does not fill them with zero. The pilot mean is the mean
of those input-group scores across models and groups. It is not the official
12-cell leaderboard mean.

Paired differences are within model and input group, in this fixed order:
MATCHED_SOFTWARE_REPLACEMENT minus STOCK, STOCK_PLUS_METAPHOR minus STOCK,
STOCK minus TASK_ONLY, MATCHED_SOFTWARE_REPLACEMENT minus TASK_ONLY. If
either side has no score, the pair is missing and is listed, not filled with
zero.

``results["records"]`` entries use ``model``, ``condition``, ``input_group``,
and 0-based ``repetition`` (``range(repetitions)`` when that count is set).
Each record's ``variants`` carry ``gate_passed``, ``n_voters``, and
``rubrics`` of ``{weight, votes}``. A vote list shorter than ``n_voters`` is
incomplete coverage. A present vote that is ``None`` or blank is a missing
verdict and counts as FAIL. ``diagnostics`` may be a count dict or
``docx_path`` / ``docx_pair`` may point at files.
"""

from __future__ import annotations

from framing_study.diagnostics import edit_diagnostics

TASK_ONLY = "TASK_ONLY"
STOCK = "STOCK"
STOCK_PLUS_METAPHOR = "STOCK_PLUS_METAPHOR"
MATCHED_SOFTWARE_REPLACEMENT = "MATCHED_SOFTWARE_REPLACEMENT"

CONDITIONS = (
    TASK_ONLY,
    STOCK,
    STOCK_PLUS_METAPHOR,
    MATCHED_SOFTWARE_REPLACEMENT,
)

# Fixed reporting order. Do not sort these by the size of the difference.
COMPARISONS = (
    (MATCHED_SOFTWARE_REPLACEMENT, STOCK, "primary"),
    (STOCK_PLUS_METAPHOR, STOCK, "secondary"),
    (STOCK, TASK_ONLY, "versus_task_only"),
    (MATCHED_SOFTWARE_REPLACEMENT, TASK_ONLY, "versus_task_only"),
)

_ABSENT = {"ABSENT", "MISSING_JUDGE", "NO_BALLOT"}
_FAILURE_PRIORITY = (
    "invalid_document",
    "gate_failed",
    "missing_judge",
    "unscorable",
    "missing",
)


def _model_name(item) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or item.get("model") or "")
    if item is None:
        return ""
    return str(item)


def canonical_condition(name: str) -> str:
    text = str(name).strip().replace("-", "_").replace(" ", "_").upper()
    return text


def _is_pass(vote: object) -> bool:
    return isinstance(vote, str) and vote.strip().upper() == "PASS"


def _is_absent(vote: object) -> bool:
    return isinstance(vote, str) and vote.strip().upper() in _ABSENT


def _votes_of(rubric: dict) -> list:
    votes = rubric.get("votes")
    if votes is None and "verdicts" in rubric:
        votes = rubric["verdicts"]
    if isinstance(votes, dict):
        return list(votes.values())
    if isinstance(votes, (list, tuple)):
        return list(votes)
    if "verdict" in rubric:
        return [rubric["verdict"]]
    return []


def rubric_passes(votes: list, n_voters: int | None = None) -> bool:
    """Return True when ``n_pass * 2 > n_voters``.

    Votes that are missing (``None`` or blank) count as FAIL. They do not
    increment ``n_pass``. ``n_voters`` defaults to the length of ``votes``.
    """

    panel = list(votes)
    voters = len(panel) if n_voters is None else int(n_voters)
    if voters <= 0:
        return False
    n_pass = sum(1 for vote in panel if _is_pass(vote))
    return n_pass * 2 > voters


def _compute_reward(rubrics: list[dict], n_voters: int | None) -> float | None:
    positive = 0.0
    earned = 0.0
    for rubric in rubrics:
        weight = float(rubric.get("weight") or 0)
        votes = _votes_of(rubric)
        voters = len(votes) if n_voters is None else int(n_voters)
        passed = rubric_passes(votes, voters)
        if weight > 0:
            positive += weight
            if passed:
                earned += weight
        elif weight < 0 and passed:
            earned -= abs(weight)
    if positive <= 0:
        return None
    raw = earned / positive
    if raw < 0:
        return 0.0
    if raw > 1:
        return 1.0
    return raw


def reward_from_rubrics(rubrics: list[dict], n_voters: int | None = None) -> float:
    """Recompute one variant reward from rubric weights and votes."""

    reward = _compute_reward(rubrics, n_voters)
    if reward is None:
        raise ValueError("rubrics have no positive weight")
    return reward


def _gate_passed(variant: dict) -> bool:
    if "gate_passed" in variant:
        return bool(variant["gate_passed"])
    gate = variant.get("gate")
    if isinstance(gate, dict) and "passed" in gate:
        return bool(gate["passed"])
    status = str(variant.get("status") or "")
    if status in {"gate_failed", "gate_failure"}:
        return False
    return True


def score_variant(variant: dict) -> dict:
    """Score one rubric variant.

    Returns ``reward`` and ``status``. ``reward`` is ``None`` when the variant
    is gate-failed, missing a judge, invalid, or otherwise unscored. Callers
    must not treat that ``None`` as zero.
    """

    if not isinstance(variant, dict):
        return {"reward": None, "status": "missing"}
    if variant.get("invalid_document") or variant.get("status") == "invalid_document":
        return {"reward": None, "status": "invalid_document"}
    if not _gate_passed(variant):
        return {"reward": None, "status": "gate_failed"}
    coverage = str(variant.get("judge_coverage") or "")
    if variant.get("missing_judge") or coverage in {"incomplete", "missing"}:
        return {"reward": None, "status": "missing_judge"}
    status = str(variant.get("status") or "")
    if status in {"missing_judge", "incomplete_judges", "panel_incomplete"}:
        return {"reward": None, "status": "missing_judge"}

    rubrics = list(variant.get("rubrics") or [])
    n_voters = variant.get("n_voters", variant.get("n_judges"))
    if not rubrics:
        if variant.get("native_reward") is not None and status in {"", "scored"}:
            return {"reward": float(variant["native_reward"]), "status": "scored"}
        return {"reward": None, "status": "missing"}

    vote_lists = []
    for rubric in rubrics:
        votes = _votes_of(rubric)
        if any(_is_absent(vote) for vote in votes):
            return {"reward": None, "status": "missing_judge"}
        vote_lists.append(votes)
    if n_voters is not None:
        expected = int(n_voters)
        if any(len(votes) < expected for votes in vote_lists):
            return {"reward": None, "status": "missing_judge"}
        reward = _compute_reward(rubrics, expected)
    else:
        reward = _compute_reward(rubrics, None)
    if reward is None:
        return {"reward": None, "status": "unscorable"}
    return {"reward": reward, "status": "scored"}


def _variants_of(record: dict) -> list[dict]:
    variants = record.get("variants")
    if isinstance(variants, list) and variants:
        return [item for item in variants if isinstance(item, dict)]
    grades = record.get("grades")
    if isinstance(grades, dict) and grades:
        converted = []
        for name, grade in grades.items():
            if not isinstance(grade, dict):
                continue
            per = (grade.get("score") or {}).get("per_rubric") or grade.get("rubrics") or []
            rubrics = []
            collapsed = True
            for item in per:
                if not isinstance(item, dict):
                    continue
                if "votes" in item or "verdicts" in item:
                    collapsed = False
                    rubrics.append(item)
                else:
                    rubrics.append(
                        {
                            "id": item.get("id") or item.get("criteria"),
                            "weight": item.get("weight") or 0,
                            "votes": [item.get("verdict")],
                        }
                    )
            judges = list(grade.get("judges") or [])
            survivors = grade.get("survivors")
            variant: dict = {
                "variant": name,
                "rubrics": rubrics,
            }
            if "gate" in grade or "gate_passed" in grade:
                gate = grade.get("gate") or {}
                variant["gate_passed"] = bool(grade.get("gate_passed", gate.get("passed", False)))
            if collapsed:
                variant["n_voters"] = 1
            elif grade.get("n_voters") is not None:
                variant["n_voters"] = grade["n_voters"]
            elif judges:
                variant["n_voters"] = len(judges)
            if judges and survivors is not None and list(survivors) != judges:
                variant["missing_judge"] = True
            if grade.get("missing_judge"):
                variant["missing_judge"] = True
            converted.append(variant)
        return converted
    if record.get("rubrics") or "gate_passed" in record or record.get("n_voters") is not None:
        return [record]
    return []


def _choose_failure(statuses: list[str]) -> str:
    for status in _FAILURE_PRIORITY:
        if status in statuses:
            return status
    return statuses[0] if statuses else "missing"


def score_record(record: dict) -> dict:
    """Score one generation. Any failed variant excludes the generation."""

    if record.get("invalid_document") or record.get("status") == "invalid_document":
        return {"score": None, "status": "invalid_document", "variant_rewards": []}
    if record.get("gate_passed") is False or record.get("status") in {"gate_failed", "gate_failure"}:
        return {"score": None, "status": "gate_failed", "variant_rewards": []}
    if record.get("missing_judge") or record.get("status") in {
        "missing_judge",
        "incomplete_judges",
        "panel_incomplete",
    }:
        return {"score": None, "status": "missing_judge", "variant_rewards": []}

    variants = _variants_of(record)
    if not variants:
        return {"score": None, "status": "missing", "variant_rewards": []}
    rewards = []
    statuses = []
    for variant in variants:
        scored = score_variant(variant)
        statuses.append(scored["status"])
        if scored["status"] == "scored":
            rewards.append(scored["reward"])
    if any(status != "scored" for status in statuses):
        return {
            "score": None,
            "status": _choose_failure([status for status in statuses if status != "scored"]),
            "variant_rewards": rewards,
            "variant_statuses": statuses,
        }
    return {
        "score": sum(rewards) / len(rewards),
        "status": "scored",
        "variant_rewards": rewards,
        "variant_statuses": statuses,
    }


def _diagnostics_of(record: dict) -> dict | None:
    raw = record.get("diagnostics")
    if isinstance(raw, dict):
        if "error" in raw and "tracked_change_count" not in raw and "insertion_count" not in raw:
            return dict(raw)
        return edit_diagnostics(raw)
    pair = record.get("docx_pair") or record.get("diagnostics_paths")
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return edit_diagnostics(pair)
    path = record.get("docx_path") or record.get("output_docx")
    if path:
        return edit_diagnostics(path)
    return None


def _rep_id(record: dict) -> int:
    if record.get("repetition") is None:
        return 0
    return int(record["repetition"])


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _diag_mean(rows: list[dict], key: str) -> float | None:
    values = []
    for row in rows:
        diag = row.get("diagnostics") or {}
        if isinstance(diag, dict) and diag.get(key) is not None and "error" not in diag:
            values.append(float(diag[key]))
    return _mean(values)


def _blank_rates() -> dict:
    return {
        "n_expected": 0,
        "n_scored": 0,
        "n_gate_failed": 0,
        "n_missing_judge": 0,
        "n_invalid_document": 0,
        "n_missing": 0,
        "n_other_unscored": 0,
        "n_records_with_retries": 0,
        "retry_attempts_sum": 0,
        "gate_failure_rate": None,
        "missing_judge_rate": None,
        "invalid_document_rate": None,
        "missing_rate": None,
    }


def _rate(count: int, expected: int) -> float | None:
    if expected <= 0:
        return None
    return count / expected


def summarize(results: dict) -> dict:
    """Aggregate a results mapping into pilot means and paired deltas.

    ``results["records"]`` holds one generation each. See the module docstring
    for the record shape consumed by :func:`score_record`.
    """

    records = []
    for record in results.get("records") or []:
        if not isinstance(record, dict):
            continue
        item = dict(record)
        item["model"] = _model_name(record.get("model"))
        records.append(item)
    models = [_model_name(item) for item in (results.get("models") or [])]
    models = [model for model in models if model]
    for record in records:
        model = record["model"]
        if model and model not in models:
            models.append(model)
    groups = [str(item) for item in (results.get("input_groups") or [])]
    for record in records:
        group = str(record.get("input_group") or record.get("group") or "")
        if group and group not in groups:
            groups.append(group)
    conditions = [canonical_condition(item) for item in (results.get("conditions") or CONDITIONS)]
    for name in CONDITIONS:
        if name not in conditions:
            conditions.append(name)
    for record in records:
        name = canonical_condition(record.get("condition") or "")
        if name and name not in conditions:
            conditions.append(name)

    declared_reps = results.get("repetitions")
    if declared_reps:
        rep_ids = list(range(int(declared_reps)))
    else:
        rep_ids = sorted({_rep_id(record) for record in records}) or [0]

    indexed: dict[tuple[str, str, str, int], list[dict]] = {}
    for record in records:
        model = str(record.get("model") or "")
        condition = canonical_condition(record.get("condition") or "")
        group = str(record.get("input_group") or record.get("group") or "")
        indexed.setdefault((model, condition, group, _rep_id(record)), []).append(record)

    failures = {
        "gate_failures": [],
        "missing_judges": [],
        "invalid_documents": [],
        "missing_results": [],
        "retries": [],
        "other_unscored": [],
    }
    by_model: dict[str, dict] = {}
    condition_group_scores: dict[str, list[float]] = {name: [] for name in conditions}
    condition_scored_diags: dict[str, list[dict]] = {name: [] for name in conditions}
    rates = {name: _blank_rates() for name in conditions}

    for model in models:
        model_conditions: dict[str, dict] = {}
        for condition in conditions:
            group_rows = {}
            for group in groups:
                rep_rows = []
                for rep in rep_ids:
                    matches = indexed.get((model, condition, group, rep), [])
                    if not matches:
                        rep_rows.append(
                            {
                                "repetition": rep,
                                "score": None,
                                "status": "missing",
                                "variant_rewards": [],
                                "diagnostics": None,
                                "retries": 0,
                            }
                        )
                        failures["missing_results"].append(
                            {
                                "model": model,
                                "condition": condition,
                                "input_group": group,
                                "repetition": rep,
                                "status": "missing",
                            }
                        )
                        continue
                    scored_reps = []
                    for record in matches:
                        scored = score_record(record)
                        diag = _diagnostics_of(record)
                        retries = int(record.get("retries") or record.get("retry_count") or 0)
                        row = {
                            "repetition": rep,
                            "score": scored["score"],
                            "status": scored["status"],
                            "variant_rewards": scored.get("variant_rewards") or [],
                            "diagnostics": diag,
                            "retries": retries,
                        }
                        scored_reps.append(row)
                        _record_failure(failures, model, condition, group, row)
                    rep_rows.extend(scored_reps)
                scored_values = [row["score"] for row in rep_rows if row["status"] == "scored" and row["score"] is not None]
                if scored_values:
                    group_status = "scored"
                    group_score = _mean(scored_values)
                else:
                    group_score = None
                    group_status = _choose_failure([row["status"] for row in rep_rows])
                group_rows[group] = {
                    "score": group_score,
                    "status": group_status,
                    "n_scored_repetitions": len(scored_values),
                    "n_repetitions": len(rep_rows),
                    "repetitions": rep_rows,
                }
                if group_score is not None:
                    condition_group_scores[condition].append(group_score)
            scored_diags = []
            for group, row in group_rows.items():
                for rep in row["repetitions"]:
                    if rep["status"] == "scored":
                        scored_diags.append(rep)
                        condition_scored_diags[condition].append(rep)
            model_conditions[condition] = {
                "groups": group_rows,
                "pilot_mean": _mean(
                    [row["score"] for row in group_rows.values() if row["score"] is not None]
                ),
                "n_scored_groups": sum(1 for row in group_rows.values() if row["score"] is not None),
                "diagnostics_beside_scored": _diag_block(scored_diags),
            }
        by_model[model] = {"conditions": model_conditions}

    for condition in conditions:
        bucket = rates[condition]
        expected = len(models) * len(groups) * len(rep_ids)
        bucket["n_expected"] = expected
        for model in models:
            for group in groups:
                for rep in by_model[model]["conditions"][condition]["groups"][group]["repetitions"]:
                    status = rep["status"]
                    if status == "scored":
                        bucket["n_scored"] += 1
                    elif status == "gate_failed":
                        bucket["n_gate_failed"] += 1
                    elif status == "missing_judge":
                        bucket["n_missing_judge"] += 1
                    elif status == "invalid_document":
                        bucket["n_invalid_document"] += 1
                    elif status == "missing":
                        bucket["n_missing"] += 1
                    else:
                        bucket["n_other_unscored"] += 1
                    if rep.get("retries"):
                        bucket["n_records_with_retries"] += 1
                        bucket["retry_attempts_sum"] += int(rep["retries"])
        bucket["gate_failure_rate"] = _rate(bucket["n_gate_failed"], expected)
        bucket["missing_judge_rate"] = _rate(bucket["n_missing_judge"], expected)
        bucket["invalid_document_rate"] = _rate(bucket["n_invalid_document"], expected)
        bucket["missing_rate"] = _rate(bucket["n_missing"], expected)

    condition_summary = {}
    for condition in conditions:
        scores = condition_group_scores[condition]
        condition_summary[condition] = {
            "pilot_mean": _mean(scores),
            "n_scored_groups": len(scores),
            "rates": rates[condition],
            "diagnostics_beside_scored": _diag_block(condition_scored_diags[condition]),
        }

    comparisons = [
        _paired(by_model, models, groups, left, right, role) for left, right, role in COMPARISONS
    ]
    return {
        "synthetic": results.get("synthetic") is True or results.get("synthetic") == "true",
        "models": models,
        "input_groups": groups,
        "conditions_order": conditions,
        "repetitions": rep_ids,
        "by_model": by_model,
        "conditions": condition_summary,
        "comparisons": comparisons,
        "failures": failures,
        "pilot_mean_definition": (
            "Mean of scored input-group scores. An input-group score averages "
            "variant rewards for one generation, then averages scored repetitions. "
            "This is a pilot mean, not the official 12-cell leaderboard mean."
        ),
    }


def _record_failure(failures: dict, model: str, condition: str, group: str, row: dict) -> None:
    entry = {
        "model": model,
        "condition": condition,
        "input_group": group,
        "repetition": row["repetition"],
        "status": row["status"],
        "tracked_change_count": (row.get("diagnostics") or {}).get("tracked_change_count")
        if isinstance(row.get("diagnostics"), dict)
        else None,
        "comment_count": (row.get("diagnostics") or {}).get("comment_count")
        if isinstance(row.get("diagnostics"), dict)
        else None,
        "retries": row.get("retries") or 0,
    }
    if row["status"] == "gate_failed":
        failures["gate_failures"].append(entry)
    elif row["status"] == "missing_judge":
        failures["missing_judges"].append(entry)
    elif row["status"] == "invalid_document":
        failures["invalid_documents"].append(entry)
    elif row["status"] not in {"scored", "missing"}:
        failures["other_unscored"].append(entry)
    if row.get("retries"):
        failures["retries"].append(entry)


def _diag_block(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "mean_tracked_change_count": _diag_mean(rows, "tracked_change_count"),
        "mean_comment_count": _diag_mean(rows, "comment_count"),
        "mean_insertion_count": _diag_mean(rows, "insertion_count"),
        "mean_deletion_count": _diag_mean(rows, "deletion_count"),
        "lower_count_is_not_a_better_score": True,
    }


def _paired(by_model: dict, models: list[str], groups: list[str], left: str, right: str, role: str) -> dict:
    deltas = []
    missing = []
    for model in models:
        left_groups = by_model[model]["conditions"][left]["groups"]
        right_groups = by_model[model]["conditions"][right]["groups"]
        for group in groups:
            left_row = left_groups[group]
            right_row = right_groups[group]
            if left_row["score"] is None or right_row["score"] is None:
                reasons = []
                if left_row["score"] is None:
                    reasons.append(f"{left}:{left_row['status']}")
                if right_row["score"] is None:
                    reasons.append(f"{right}:{right_row['status']}")
                missing.append(
                    {
                        "model": model,
                        "input_group": group,
                        "reason": "; ".join(reasons),
                        "left_status": left_row["status"],
                        "right_status": right_row["status"],
                    }
                )
                continue
            deltas.append(
                {
                    "model": model,
                    "input_group": group,
                    "delta": round(left_row["score"] - right_row["score"], 6),
                    "left_score": left_row["score"],
                    "right_score": right_row["score"],
                }
            )
    values = [item["delta"] for item in deltas]
    mean_delta = round(sum(values) / len(values), 6) if values else None
    return {
        "role": role,
        "name": f"{left} minus {right}",
        "left": left,
        "right": right,
        "deltas": deltas,
        "missing": missing,
        "mean_delta": mean_delta,
        "n_pairs": len(deltas),
        "n_missing": len(missing),
        "inference": "descriptive paired difference only; not a significance test",
    }
