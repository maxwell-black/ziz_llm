"""Markdown report for the RedlineBench instruction experiment.

``write_report`` reads generation records, recomputes native rewards, and
writes the sections the study requires. Comparisons stay in fixed order:
primary, secondary, then the two contrasts versus TASK_ONLY.
"""

from __future__ import annotations

from pathlib import Path

from framing_study.aggregate import summarize

_RESIDUAL = (
    "scenario-1 AgentCo grounding repeats two hygiene rules; "
    "Harbor system prompt uncontrolled"
)


def write_report(results: dict, dest: Path) -> Path:
    """Write the Markdown report and return its path."""

    dest = Path(dest)
    if dest.exists() and dest.is_dir():
        dest = dest / "report.md"
    elif dest.suffix.lower() != ".md":
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / "report.md"
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_report(results), encoding="utf-8")
    return dest


def render_report(results: dict) -> str:
    summary = summarize(results)
    lines: list[str] = []
    if summary["synthetic"]:
        lines.append("SYNTHETIC FIXTURE, not a model result.")
        lines.append("")
    lines.append("# RedlineBench instruction experiment, not an official reproduction")
    lines.append("")
    lines.extend(_pins(results, summary))
    lines.extend(_instruction(results))
    lines.extend(_scoring_note(summary))
    lines.extend(_comparisons(summary))
    lines.extend(_means(summary))
    lines.extend(_group_table(summary))
    lines.extend(_failures(summary))
    lines.extend(_diagnostics(summary))
    lines.extend(_usage(results))
    lines.extend(_audit(results))
    lines.extend(_limits(summary))
    lines.extend(_examples(summary))
    return "\n".join(lines).rstrip() + "\n"


def _pins(results: dict, summary: dict) -> list[str]:
    pins = results.get("pins") or {}
    harness = results.get("harness") or pins.get("harbor_agent") or pins.get("harness") or "terminus-2"
    seed = results.get("seed", results.get("execution_seed", "unknown"))
    repetitions = results.get("repetitions", "unknown")
    lines = [
        "## Pins, models, harness, seed, repetitions",
        "",
        f"Harness: {harness}",
        f"Seed: {seed}",
        f"Repetitions: {repetitions}",
        "Models: " + (", ".join(summary["models"]) if summary["models"] else "unknown"),
        "Input groups in this file: " + (
            ", ".join(summary["input_groups"]) if summary["input_groups"] else "unknown"
        ),
        "",
        "Pins:",
    ]
    if isinstance(pins, dict) and pins:
        for key in sorted(pins):
            lines.append(f"- {key}: {pins[key]}")
    else:
        lines.append("- unknown")
    lines.append("")
    return lines


def _instruction(results: dict) -> list[str]:
    info = results.get("instruction_summary") or {}
    spans = info.get("designated_spans") or info.get("spans") or []
    lines = [
        "## Instruction summary",
        "",
        "The instruction manipulation uses three designated spans.",
    ]
    if len(spans) == 3:
        for index, span in enumerate(spans, start=1):
            lines.append(f"- Span {index}: {span}")
    elif spans:
        lines.append(f"Results listed {len(spans)} span texts (the design specifies three designated spans).")
        for span in spans:
            lines.append(f"- {span}")
    else:
        lines.append("Span text: unknown.")
    sentence = info.get("condition_2_sentence", info.get("condition2_sentence"))
    lines.append("")
    if sentence:
        lines.append("Condition 2 sentence:")
        lines.append("")
        lines.append(str(sentence))
    else:
        lines.append("Condition 2 sentence: unknown.")
    lines.append("")
    lines.append(f"Residual coaching note: {_RESIDUAL}.")
    lines.append("")
    return lines


def _scoring_note(summary: dict) -> list[str]:
    return [
        "## Scoring rule",
        "",
        "Native reward = clamp((sum of positive-weight rubrics voted PASS − sum of absolute weights of penalty rubrics voted PASS) / sum of positive weights, 0, 1).",
        "A rubric PASSes only when n_pass * 2 > n_voters. Missing verdicts count as FAIL. Penalty rubrics are those with negative weight.",
        "The benchmark package is not imported.",
        summary["pilot_mean_definition"],
        "Gate failures and incomplete judge coverage are excluded from the native mean. A missing result is not a zero in the mean.",
        "Paired differences stay in a fixed order: primary, then secondary, then the two contrasts versus TASK_ONLY. They are not ranked by which difference is larger.",
        "These paired differences are descriptive. This report does not claim statistical significance.",
        "",
    ]


def _comparisons(summary: dict) -> list[str]:
    lines: list[str] = []
    versus_started = False
    for comparison in summary["comparisons"]:
        role = comparison["role"]
        if role == "primary":
            lines.extend(
                [
                    "## Primary paired result",
                    "",
                    "This is the designated primary comparison. It is reported first.",
                    "",
                    comparison["name"],
                    "",
                ]
            )
        elif role == "secondary":
            lines.extend(
                [
                    "## Secondary paired result",
                    "",
                    "The secondary comparison is not the main result.",
                    "It is reported after the primary comparison. A larger secondary delta does not change that order.",
                    "",
                    comparison["name"],
                    "",
                ]
            )
        elif role == "versus_task_only":
            if not versus_started:
                lines.extend(["## Comparisons versus TASK_ONLY", ""])
                versus_started = True
            lines.extend([f"### {comparison['name']}", ""])
        lines.extend(_one_comparison(comparison))
    return lines


def _one_comparison(comparison: dict) -> list[str]:
    lines = [
        f"mean delta: {_fmt(comparison['mean_delta']) if comparison['mean_delta'] is not None else 'no scored pairs'}",
        f"n pairs: {comparison['n_pairs']}",
        f"n missing: {comparison['n_missing']}",
        comparison["inference"],
        "",
        "deltas:",
    ]
    if comparison["deltas"]:
        for item in comparison["deltas"]:
            lines.append(f"- {item['model']} / {item['input_group']}: {_fmt(item['delta'])}")
    else:
        lines.append("- no scored pairs")
    lines.append("")
    lines.append("missing pairs:")
    if comparison["missing"]:
        for item in comparison["missing"]:
            lines.append(f"- {item['model']} / {item['input_group']}: {item['reason']}")
    else:
        lines.append("- none")
    lines.append("")
    return lines


def _means(summary: dict) -> list[str]:
    lines = [
        "## Per-condition native means",
        "",
        "Each figure below is a pilot mean (mean of input-group scores; not the official 12-cell leaderboard mean).",
        "Excluded generations are omitted here and listed with the failures.",
        "",
        "| condition | pilot mean | n scored input groups | mean tracked changes beside scored | mean comments beside scored |",
        "| --- | --- | --- | --- | --- |",
    ]
    for condition, payload in summary["conditions"].items():
        diag = payload["diagnostics_beside_scored"]
        lines.append(
            "| {condition} | {mean} | {n} | {tracked} | {comments} |".format(
                condition=condition,
                mean=_fmt(payload["pilot_mean"]),
                n=payload["n_scored_groups"],
                tracked=_fmt(diag["mean_tracked_change_count"]),
                comments=_fmt(diag["mean_comment_count"]),
            )
        )
    lines.append("")
    for condition, payload in summary["conditions"].items():
        shown = _fmt(payload["pilot_mean"]) if payload["pilot_mean"] is not None else "unknown"
        lines.append(f"pilot mean [{condition}]: {shown}")
    lines.append("")
    lines.append("Per-model pilot means use the same input-group scores, still not ranked:")
    lines.append("")
    for model, payload in summary["by_model"].items():
        parts = []
        for condition, block in payload["conditions"].items():
            parts.append(f"{condition}={_fmt(block['pilot_mean'])}")
        lines.append(f"- {model}: " + "; ".join(parts))
    lines.append("")
    return lines


def _group_table(summary: dict) -> list[str]:
    conditions = summary["conditions_order"]
    header = ["model", "input group", *conditions]
    lines = [
        "## Per-group table",
        "",
        "Each cell is the input-group score: the mean of variant rewards for a generation, then the mean of scored repetitions. Repetitions are repeated measures, not extra contracts. An excluded cell is not a zero.",
        "",
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for model, payload in summary["by_model"].items():
        groups = summary["input_groups"]
        for group in groups:
            cells = [model, group]
            for condition in conditions:
                row = payload["conditions"][condition]["groups"][group]
                if row["score"] is None:
                    cells.append(f"excluded ({row['status']})")
                else:
                    cells.append(_fmt(row["score"]))
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _failures(summary: dict) -> list[str]:
    failures = summary["failures"]
    lines = [
        "## Failures, invalid documents, retries, missing judges",
        "",
        "Gate failures and incomplete judge coverage are excluded from the native mean and are not entered as zeros. Rates use the expected model × input group × repetition grid as the denominator.",
        "",
        "| condition | expected | scored | gate failures | gate failure rate | missing judges | missing judge rate | invalid documents | missing results |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for condition, payload in summary["conditions"].items():
        rates = payload["rates"]
        lines.append(
            "| {condition} | {expected} | {scored} | {gate} | {gate_rate} | {judges} | {judge_rate} | {invalid} | {missing} |".format(
                condition=condition,
                expected=rates["n_expected"],
                scored=rates["n_scored"],
                gate=rates["n_gate_failed"],
                gate_rate=_fmt(rates["gate_failure_rate"]),
                judges=rates["n_missing_judge"],
                judge_rate=_fmt(rates["missing_judge_rate"]),
                invalid=rates["n_invalid_document"],
                missing=rates["n_missing"],
            )
        )
    lines.append("")
    lines.extend(_failure_bucket("Gate failures", failures["gate_failures"], "gate failure"))
    lines.extend(_failure_bucket("Missing judges", failures["missing_judges"], "missing judge"))
    if failures["invalid_documents"]:
        lines.extend(_failure_bucket("Invalid documents", failures["invalid_documents"], "invalid document"))
    else:
        lines.extend(["### Invalid documents", "", "invalid documents: none", ""])
    if failures["retries"]:
        lines.append("### Retries")
        lines.append("")
        for item in failures["retries"]:
            lines.append(
                f"- retry: {item['model']} / {item['input_group']} / {item['condition']} / repetition {item['repetition']} / count {item['retries']}"
            )
        lines.append("")
    else:
        lines.extend(["### Retries", "", "retries: none", ""])
    if failures["missing_results"]:
        lines.extend(_failure_bucket("Missing results", failures["missing_results"], "missing result"))
    else:
        lines.extend(["### Missing results", "", "missing results: none", ""])
    if failures["other_unscored"]:
        lines.extend(_failure_bucket("Other unscored generations", failures["other_unscored"], "unscored"))
    return lines


def _failure_bucket(title: str, rows: list[dict], label: str) -> list[str]:
    lines = [f"### {title}", ""]
    if not rows:
        lines.append("none")
        lines.append("")
        return lines
    for item in rows:
        tracked = item.get("tracked_change_count")
        comments = item.get("comment_count")
        extra = ""
        if tracked is not None or comments is not None:
            extra = f" / tracked changes {_fmt(tracked)} / comments {_fmt(comments)}"
        lines.append(
            f"- {label}: {item['model']} / {item['input_group']} / {item['condition']} / repetition {item['repetition']}{extra}"
        )
    lines.append("")
    return lines


def _diagnostics(summary: dict) -> list[str]:
    lines = [
        "## Edit diagnostics",
        "",
        "Edit diagnostics sit beside the native scores. Fewer words are not automatically better. A lower tracked-change count or a lower comment count is not a better score.",
        'Counts are descriptive. When they were computed from docx XML, they are w:ins and w:del elements, and comments, whose author startswith "Reviewing Counsel". Unknown counts stay unknown.',
        "",
    ]
    for condition, payload in summary["conditions"].items():
        diag = payload["diagnostics_beside_scored"]
        lines.append(
            "beside scored [{condition}]: n={n}; mean tracked changes {tracked}; mean comments {comments}; mean insertions {insertions}; mean deletions {deletions}".format(
                condition=condition,
                n=diag["n"],
                tracked=_fmt(diag["mean_tracked_change_count"]),
                comments=_fmt(diag["mean_comment_count"]),
                insertions=_fmt(diag["mean_insertion_count"]),
                deletions=_fmt(diag["mean_deletion_count"]),
            )
        )
    lines.append("")
    return lines


def _usage(results: dict) -> list[str]:
    usage = results.get("usage") if isinstance(results.get("usage"), dict) else {}
    estimated = _norm_usage((usage or {}).get("estimated", results.get("estimated")))
    reported = _norm_usage((usage or {}).get("reported", results.get("reported")))
    lines = [
        "## Usage and cost",
        "",
        "Estimated and reported figures are separate. Unknown stays unknown. An estimate is not measured spend, and reported cost is not filled in from the estimate.",
        "",
        "### Estimated",
        "",
        f"estimated total_usd: {_fmt_money(estimated['total_usd'])}",
        f"estimated input_tokens: {_fmt_count(estimated['input_tokens'])}",
        f"estimated output_tokens: {_fmt_count(estimated['output_tokens'])}",
        "",
        "### Reported",
        "",
        f"reported total_usd: {_fmt_money(reported['total_usd'])}",
        f"reported input_tokens: {_fmt_count(reported['input_tokens'])}",
        f"reported output_tokens: {_fmt_count(reported['output_tokens'])}",
        "",
    ]
    return lines


def _norm_usage(block) -> dict:
    if isinstance(block, bool) or block is None:
        return {"total_usd": None, "input_tokens": None, "output_tokens": None}
    if isinstance(block, (int, float)):
        return {"total_usd": float(block), "input_tokens": None, "output_tokens": None}
    if not isinstance(block, dict):
        return {"total_usd": None, "input_tokens": None, "output_tokens": None}
    total = block.get("total_usd", block.get("usd", block.get("cost_usd")))
    return {
        "total_usd": None if total is None else float(total),
        "input_tokens": block.get("input_tokens"),
        "output_tokens": block.get("output_tokens"),
    }


def _audit(results: dict) -> list[str]:
    entries = results.get("human_audit")
    lines = ["## Human audit", ""]
    if not entries:
        lines.append("No human audit entries.")
        lines.append("")
        return lines
    for entry in entries:
        if isinstance(entry, str):
            lines.append(f"- {entry}")
        else:
            lines.append(f"- {entry}")
    lines.append("")
    return lines


def _limits(summary: dict) -> list[str]:
    n_groups = len(summary["input_groups"])
    return [
        "## Limits",
        "",
        "Semantic match is a judgment. Condition 2 adds text. Condition 4 retains residual coaching. "
        "Judge variability can change a rubric vote. Public data contamination can affect generations on published contracts. "
        f"This file contains {n_groups} input groups. The study is limited to six input groups. "
        "The compared conditions use a shared harness. "
        "This report makes no claim about internal mechanisms or about all legal work.",
        "",
    ]


def _examples(summary: dict) -> list[str]:
    primary = next(item for item in summary["comparisons"] if item["role"] == "primary")
    helped = [item for item in primary["deltas"] if item["delta"] > 0]
    hurt = [item for item in primary["deltas"] if item["delta"] < 0]
    same = [item for item in primary["deltas"] if item["delta"] == 0]
    lines = [
        "## Examples",
        "",
        f"Slots are filled only from scored primary pairs ({primary['name']}). Helped means that primary delta is positive. Hurt means it is negative. No discernible difference means the paired scores are equal. The sign is not an explanation of the redline.",
        "",
        "### Helped",
        "",
    ]
    lines.extend(_example_slot(helped))
    lines.extend(["### Hurt", ""])
    lines.extend(_example_slot(hurt))
    lines.extend(["### No discernible difference", ""])
    lines.extend(_example_slot(same))
    return lines


def _example_slot(rows: list[dict]) -> list[str]:
    if not rows:
        return ["no scored pairs", ""]
    lines = [f"- {item['model']} / {item['input_group']}: delta {_fmt(item['delta'])}" for item in rows]
    lines.append("")
    return lines


def _fmt(value) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):.6f}"


def _fmt_money(value) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):.6f}"


def _fmt_count(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
