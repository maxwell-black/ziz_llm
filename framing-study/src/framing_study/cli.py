"""Command line for ``python -m framing_study``.

Live smoke and pilot runs refuse unless ``--spend-limit`` is an explicit
non-negative number, the price table yields a known estimate, and
estimate + in-flight reservations fit under that limit. The config
``spend_limit`` field is not a default.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

import yaml

from framing_study.budget import (
    InFlightLedger,
    calls_for_schedule,
    decide_spend,
    estimate_run,
    format_cost_report,
)
from framing_study.catalog import (
    AGENT,
    CONDITIONS,
    DEFAULT_MAX_INFRASTRUCTURE_RETRIES,
    DEFAULT_SEED,
    HARBOR_VERSION_PIN,
    comparisons_match,
    fetch_task_ids,
    groups_for_scope,
    judge_panel_status,
    representative_tasks,
)
from framing_study.manifest import (
    build_manifest,
    load_manifest,
    open_manifest,
    read_pins,
    study_settings,
    transform_identity,
)
from framing_study.preflight import format_preflight, preflight_report, write_revision
from framing_study.runner import run_saved_manifest
from framing_study.schedule import build_schedule, generation_slot_id, repetition_indexes


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_path() -> Path:
    return project_root() / "config" / "pilot.yaml"


def load_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    resolved = path.resolve()
    root = resolved.parent.parent if resolved.parent.name == "config" else resolved.parent

    def resolve_dir(key: str, default: str) -> Path:
        value = raw.get(key, default)
        if value is None:
            value = default
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate

    prices = raw.get("prices_usd_per_million") or {}
    if not isinstance(prices, dict):
        raise ValueError("prices_usd_per_million must be a mapping")
    return {
        "models": [str(model) for model in (raw.get("models") or [])],
        "repetitions": int(raw.get("repetitions", 1)),
        "seed": int(raw.get("seed", DEFAULT_SEED)),
        "agent": str(raw.get("agent") or AGENT),
        "harbor_version": str(raw.get("harbor_version") or HARBOR_VERSION_PIN),
        "max_infrastructure_retries": int(
            raw.get("max_infrastructure_retries", DEFAULT_MAX_INFRASTRUCTURE_RETRIES)
        ),
        "prices_usd_per_million": prices,
        "allows_uncontrolled_egress": bool(raw.get("allows_uncontrolled_egress", False)),
        "judge_panel": [str(name) for name in (raw.get("judge_panel") or [])],
        "cache_dir": resolve_dir("cache_dir", ".cache/framing-study"),
        "dataset_dir": resolve_dir("dataset_dir", ".cache/redlinebench"),
        "output_dir": resolve_dir("output_dir", "runs"),
        "audit_sample_size": int(raw.get("audit_sample_size", 2)),
        "comparisons_ok": comparisons_match(raw.get("comparisons")),
        "project_root": root,
        "config_path": resolved,
    }


def _ledger(config: dict) -> InFlightLedger:
    return InFlightLedger(Path(config["output_dir"]) / "in_flight.json")


def _estimate_for(config: dict, schedule: list[dict], judge_ids: list[str]) -> dict:
    generations, judges = calls_for_schedule(schedule, judge_ids)
    return estimate_run(
        prices=config["prices_usd_per_million"],
        generation_calls=generations,
        judge_calls=judges,
    )


def _pending_schedule(config: dict, scope: str, manifest_path: Path) -> tuple[list[dict], list[str], bool]:
    panel = judge_panel_status(config["judge_panel"])
    judge_ids = list(panel["ids"])
    if manifest_path.is_file():
        manifest = load_manifest(manifest_path)
        done = set(manifest.get("completed_slots") or [])
        pending = [
            slot
            for slot in manifest["schedule"]
            if generation_slot_id(slot) not in done
        ]
        return pending, list(manifest.get("judge_panel") or judge_ids), True
    schedule = build_schedule(
        config["models"],
        groups_for_scope(scope),
        list(CONDITIONS),
        repetition_indexes(config["repetitions"]),
        config["seed"],
    )
    return schedule, judge_ids, False


def cmd_fetch(_args, config: dict) -> int:
    pins = read_pins()
    if pins is None:
        print("framing_study.pins is not installed yet", file=sys.stderr)
        return 2
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed", file=sys.stderr)
        return 2
    dest = Path(config["dataset_dir"])
    dest.mkdir(parents=True, exist_ok=True)
    # Task directories are self-contained. The parquet index repeats rubric
    # previews and is not required to run a task, so it is not downloaded.
    patterns = [f"tasks/{task_id}/**" for task_id in fetch_task_ids()]
    snapshot_download(
        repo_id=pins["dataset_repo"],
        repo_type="dataset",
        revision=pins["dataset_sha"],
        local_dir=str(dest),
        allow_patterns=patterns,
    )
    write_revision(dest, pins["dataset_sha"])
    print(f"fetched {pins['dataset_sha']} into {dest}")
    return 0


def write_instruction_bundle(dataset_dir: Path, out_dir: Path) -> list[dict]:
    from framing_study.transform import integrity_problems, transform

    problems = []
    for row in representative_tasks():
        source = dataset_dir / "tasks" / row["representative"] / "instruction.md"
        if not source.is_file():
            raise FileNotFoundError(f"missing instruction: {source}")
        original = source.read_text(encoding="utf-8")
        rendered: dict[str, str] = {}
        for condition in CONDITIONS:
            transformed = transform(original, condition)
            found = list(integrity_problems(original, condition, transformed) or [])
            rendered[condition] = transformed
            dest = out_dir / row["representative"] / condition
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "instruction.md").write_text(transformed, encoding="utf-8")
            if found:
                problems.append(
                    {
                        "task": row["representative"],
                        "condition": condition,
                        "problems": [str(item) for item in found],
                    }
                )
        stock_lines = rendered["STOCK"].splitlines(keepends=True)
        for condition in CONDITIONS:
            diff = "".join(
                difflib.unified_diff(
                    stock_lines,
                    rendered[condition].splitlines(keepends=True),
                    fromfile=f"{row['representative']}/STOCK/instruction.md",
                    tofile=f"{row['representative']}/{condition}/instruction.md",
                )
            )
            (out_dir / row["representative"] / condition / "vs-STOCK.diff").write_text(
                diff,
                encoding="utf-8",
            )
    return problems


def cmd_instructions(args, config: dict) -> int:
    try:
        import framing_study.transform  # noqa: F401
    except ImportError:
        print("transform is not installed yet", file=sys.stderr)
        return 1
    try:
        problems = write_instruction_bundle(Path(config["dataset_dir"]), Path(args.out))
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if problems:
        print("integrity_problems is non-empty", file=sys.stderr)
        for item in problems:
            print(f"{item['task']} {item['condition']}: {item['problems']}", file=sys.stderr)
        return 1
    print(f"wrote instructions under {args.out}")
    return 0


def cmd_preflight(_args, config: dict) -> int:
    report = preflight_report(config)
    sys.stdout.write(format_preflight(report))
    return 2 if report["blocked"] else 0


def cmd_cost(_args, config: dict) -> int:
    panel = judge_panel_status(config["judge_panel"])
    in_flight = _ledger(config).total()
    for scope in ("pilot", "smoke"):
        schedule = build_schedule(
            config["models"],
            groups_for_scope(scope),
            list(CONDITIONS),
            repetition_indexes(config["repetitions"]),
            config["seed"],
        )
        estimate = _estimate_for(config, schedule, list(panel["ids"]))
        sys.stdout.write(format_cost_report(scope, estimate, in_flight_usd=in_flight))
    return 0


def cmd_live(args, config: dict) -> int:
    scope = args.scope
    manifest_path = Path(config["output_dir"]) / scope / "manifest.json"
    ledger = _ledger(config)
    run_id = f"{scope}:{manifest_path}"
    pending, judge_ids, resuming = _pending_schedule(config, scope, manifest_path)
    estimate = _estimate_for(config, pending, judge_ids)
    decision = decide_spend(
        estimate_usd=estimate["total_usd"] if estimate["known"] else None,
        spend_limit=args.spend_limit,
        in_flight_usd=ledger.total(exclude=run_id),
    )
    if not decision.allowed:
        print(decision.reason, file=sys.stderr)
        return 2
    if not config["models"]:
        print("no models configured", file=sys.stderr)
        return 2
    report = preflight_report(config)
    sys.stdout.write(format_preflight(report))
    if report["blocked"]:
        return 2
    pins = report["pins"]
    assert pins is not None

    def rebuild():
        return build_manifest(
            scope=scope,
            models=config["models"],
            groups=groups_for_scope(scope),
            repetitions=config["repetitions"],
            seed=config["seed"],
            settings=study_settings(config),
            prices=config["prices_usd_per_million"],
            spend_limit=args.spend_limit,
            in_flight_usd=decision.in_flight_usd,
            code_sha=pins["code_sha"],
            dataset_sha=pins["dataset_sha"],
            transform_sha=transform_identity(),
            judge_panel=judge_ids,
            judge_panel_overridden=False,
        )

    if resuming:
        manifest = load_manifest(manifest_path)
        if manifest.get("seed") != config["seed"]:
            print(
                "saved manifest seed differs from config; resume keeps the saved schedule",
                file=sys.stderr,
            )
    else:
        manifest = open_manifest(manifest_path, rebuild)
        del manifest
    # Schedule file exists before any generation, including on resume.
    if not manifest_path.is_file():
        print("manifest was not written before generation", file=sys.stderr)
        return 2
    ledger.set_reservation(run_id, float(decision.estimate_usd or 0))
    try:
        return run_saved_manifest(
            manifest_path,
            config,
            spend_limit=float(args.spend_limit),
            ledger=ledger,
            run_id=run_id,
        )
    finally:
        ledger.release(run_id)


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_for_report(config: dict, scope: str | None) -> tuple[Path, dict] | None:
    output = Path(config["output_dir"])
    scopes = [scope] if scope else ("pilot", "smoke")
    for name in scopes:
        path = output / name / "manifest.json"
        if path.is_file():
            return path, load_manifest(path)
    return None


def cmd_report(args, config: dict) -> int:
    try:
        from framing_study.report import write_report
    except ImportError:
        print("reporting is not installed yet", file=sys.stderr)
        return 1
    if args.results is not None:
        results = _load_json(Path(args.results))
    else:
        found = _manifest_for_report(config, args.scope)
        if found is None:
            print("no scored results to report", file=sys.stderr)
            return 1
        manifest_path, manifest = found
        from framing_study.runner import study_results

        results = study_results(manifest, manifest_path.parent, Path(config["dataset_dir"]))
        # study_results does not copy scope. The report reads this field so a
        # later `report --scope smoke` rerun still labels the file as a smoke.
        results["scope"] = manifest.get("scope") or args.scope
    if args.scope and isinstance(results, dict) and not results.get("scope"):
        results["scope"] = args.scope
    dest = Path(args.out) if args.out else Path(config["output_dir"]) / "report.md"
    written = write_report(results, dest)
    print(written)
    return 0


def cmd_blind(args, config: dict) -> int:
    try:
        from framing_study.blind import write_packet
    except ImportError:
        print("reporting is not installed yet", file=sys.stderr)
        return 1
    if args.cases is not None:
        loaded = _load_json(Path(args.cases))
        cases = loaded["cases"] if isinstance(loaded, dict) and "cases" in loaded else loaded
    else:
        found = _manifest_for_report(config, args.scope)
        if found is None:
            print("no scored results to report", file=sys.stderr)
            return 1
        manifest_path, manifest = found
        from framing_study.runner import blind_cases

        cases = blind_cases(manifest, manifest_path.parent)
    dest = Path(args.out) if args.out else Path(config["output_dir"]) / "blind"
    write_packet(
        cases,
        dest,
        seed=int(config["seed"]),
        audit_n=int(config["audit_sample_size"]),
    )
    print(dest)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="framing_study")
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="snapshot the pinned pilot and smoke tasks")
    fetch.set_defaults(func=cmd_fetch)

    instructions = sub.add_parser("instructions", help="write transformed instruction.md files")
    instructions.add_argument("--out", type=Path, required=True)
    instructions.set_defaults(func=cmd_instructions)

    preflight = sub.add_parser("preflight", help="report whether a live run would be blocked")
    preflight.set_defaults(func=cmd_preflight)

    cost = sub.add_parser("cost", help="print generation, judging, and infra estimates")
    cost.set_defaults(func=cmd_cost)

    for name in ("smoke", "pilot"):
        command = sub.add_parser(name, help=f"run the {name} scope")
        command.add_argument(
            "--spend-limit",
            type=float,
            default=None,
            help="explicit non-negative USD ceiling; omitting it refuses the run",
        )
        command.set_defaults(func=cmd_live, scope=name)

    report = sub.add_parser("report", help="call framing_study.report.write_report")
    report.add_argument("--results", type=Path, default=None)
    report.add_argument("--out", type=Path, default=None)
    report.add_argument("--scope", choices=("pilot", "smoke"), default=None)
    report.set_defaults(func=cmd_report)
    blind = sub.add_parser("blind", help="call framing_study.blind.write_packet")
    blind.add_argument("--cases", type=Path, default=None)
    blind.add_argument("--out", type=Path, default=None)
    blind.add_argument("--scope", choices=("pilot", "smoke"), default=None)
    blind.set_defaults(func=cmd_blind)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = args.config or default_config_path()
    if not config_path.is_file():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 2
    try:
        config = load_config(config_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"could not load config: {exc}", file=sys.stderr)
        return 2
    return int(args.func(args, config))
