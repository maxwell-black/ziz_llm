"""One Harbor generation per input group, then one grade per variant.

Generation uses the ``harbor run`` argv built by redlinebench's
``run_harbor``. Grading uses each variant's ``tests/judge.py``.
``src/rejudge.py`` is not called. No model output is invented: a failed
attempt stays on disk without a stand-in docx.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from framing_study.budget import PLANNING_ASSUMPTIONS, decide_spend, estimate_run
from framing_study.cache import (
    generation_cache_key,
    grade_cache_key,
    load_generation,
    load_grade,
    store_generation,
    store_grade,
)
from framing_study.catalog import AGENT, JUDGE_SETTINGS, NATIVE_JUDGE_PANEL
from framing_study.isolate import prepare_agent_workspace, redact
from framing_study.manifest import load_manifest, save_manifest
from framing_study.schedule import generation_slot_id

_HTTP_429 = re.compile(r"\b429\b|too many requests", re.IGNORECASE)
_HTTP_5XX = re.compile(r"\b5\d\d\b")
_TIMEOUT = re.compile(r"timeout|timed out", re.IGNORECASE)
_CONNECTION = re.compile(
    r"connectionerror|connect error|connection refused|econnrefused|econnreset|"
    r"temporary failure in name resolution",
    re.IGNORECASE,
)


def is_infrastructure_failure(*, status_code: int | None = None, kind: str | None = None) -> bool:
    """True for timeouts, connection errors, HTTP 429, and HTTP 5xx.

    A low score is not an infrastructure failure and must not be retried.
    """
    if kind in {"low_score", "bad_score", "validity_gate", "integrity", "other"}:
        return False
    if kind in {"timeout", "connection_error", "http_429", "http_5xx"}:
        return True
    if status_code == 429:
        return True
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return True
    return False


def classify_process_failure(returncode: int, stderr: str) -> str | None:
    if returncode == 0:
        return None
    text = stderr or ""
    if _HTTP_429.search(text):
        return "http_429"
    if _TIMEOUT.search(text):
        return "timeout"
    if _CONNECTION.search(text):
        return "connection_error"
    if _HTTP_5XX.search(text) and "reward" not in text.lower():
        return "http_5xx"
    return "other"


def harbor_run_argv(
    *,
    task_dir: Path,
    agent: str,
    model: str,
    jobs_dir: Path,
    n_concurrent: int = 1,
    max_turns: int | None = None,
) -> list[str]:
    """Argv matching redlinebench ``src/reproduce.py`` ``run_harbor`` for one task.

    ``-p`` is the isolated task directory (the same shape as
    ``redlinebench-reproduce --task``). The process cwd is not passed.
    No agent kwarg carries a condition label. Not executed here.
    """
    if agent != AGENT:
        raise ValueError(f"agent must be {AGENT} for every model, got {agent}")
    return [
        "harbor",
        "run",
        "-p",
        str(task_dir),
        "-a",
        agent,
        "-m",
        model,
        "--n-concurrent",
        str(n_concurrent),
        "--jobs-dir",
        str(jobs_dir),
        "--yes",
    ]
    if max_turns is not None:
        argv.extend(["--ak", f"max_turns={int(max_turns)}"])


def redlinebench_reproduce_argv(
    *,
    agent: str,
    model: str,
    workdir: Path,
    task: str,
    n_concurrent: int = 1,
) -> list[str]:
    """Argv of the ``redlinebench-reproduce`` console script.

    Live generation uses ``harbor_run_argv`` on the isolated tree so
    redlinebench's unpinned Hugging Face revision cannot replace the tasks.
    """
    if agent != AGENT:
        raise ValueError(f"agent must be {AGENT} for every model, got {agent}")
    return [
        "redlinebench-reproduce",
        "--agent",
        agent,
        "--model",
        model,
        "--n-concurrent",
        str(n_concurrent),
        "--workdir",
        str(workdir),
        "--task",
        task,
    ]


def judge_argv(*, judge_py: Path, contract: Path, out_dir: Path) -> list[str]:
    """Invoke the task's own ``tests/judge.py``. Not ``src/rejudge.py``."""
    return [
        sys.executable,
        str(judge_py),
        "--contract",
        str(contract),
        "--out-dir",
        str(out_dir),
    ]


def child_environ(base: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for Harbor and judge subprocesses.

    Drops judge-panel overrides and framing labels. Does not print values.
    """
    env = dict(os.environ if base is None else base)
    env.pop("JUDGE_PANEL", None)
    env.pop("JUDGE_MODEL", None)
    env.pop("FRAMING_CONDITION", None)
    return env


def find_contract_artifact(jobs_dir: Path) -> Path | None:
    artifacts = [
        path
        for path in jobs_dir.rglob("contract.docx")
        if path.parent.name == "artifacts" and path.is_file() and path.stat().st_size > 0
    ]
    if not artifacts:
        return None
    return artifacts[0]


def find_verifier_grade(jobs_dir: Path, task_name: str) -> Path | None:
    matches = [path for path in jobs_dir.glob(f"{task_name}__*/verifier/grade.json") if path.is_file()]
    if not matches:
        matches = [path for path in jobs_dir.glob("**/verifier/grade.json") if path.is_file()]
    return matches[0] if matches else None


def _run_logged(argv: list[str], env: dict[str, str], log_dir: Path) -> subprocess.CompletedProcess:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "argv.txt").write_text(redact(" ".join(argv)) + "\n", encoding="utf-8")
    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    (log_dir / "stdout.txt").write_text(redact(completed.stdout or ""), encoding="utf-8")
    (log_dir / "stderr.txt").write_text(redact(completed.stderr or ""), encoding="utf-8")
    (log_dir / "returncode.txt").write_text(str(completed.returncode) + "\n", encoding="utf-8")
    return completed


def _slot_estimate(slot: dict, prices: dict, judge_panel: list[str]) -> float | None:
    estimate = estimate_run(
        prices=prices,
        generation_calls=[slot["model"]],
        judge_calls=list(judge_panel) * len(slot["grades"]),
        assumptions=dict(PLANNING_ASSUMPTIONS),
    )
    return estimate["total_usd"] if estimate["known"] else None


def _retry_fits(slot: dict, config: dict, ledger, run_id: str, spend_limit: float) -> bool:
    extra = _slot_estimate(slot, config["prices_usd_per_million"], list(NATIVE_JUDGE_PANEL))
    in_flight = ledger.total(exclude=run_id)
    reserved = ledger.total() - in_flight
    decision = decide_spend(
        estimate_usd=extra,
        spend_limit=spend_limit,
        in_flight_usd=in_flight + reserved,
    )
    return decision.allowed


def run_saved_manifest(
    path: Path,
    config: dict,
    *,
    spend_limit: float,
    ledger,
    run_id: str,
    execute=None,
) -> int:
    """Run the schedule already stored at ``path``. Does not reshuffle."""
    if not path.is_file():
        raise RuntimeError("manifest must be saved before generation")
    manifest = load_manifest(path)
    if manifest.get("settings", {}).get("agent") != AGENT:
        raise RuntimeError(f"manifest agent is not {AGENT}")
    dataset_dir = Path(config["dataset_dir"])
    cache_dir = Path(config["cache_dir"])
    run_dir = path.parent
    (run_dir / "HARBOR_SYSTEM_PROMPT.txt").write_text(
        manifest["harbor_terminus2_system_prompt"]["note"] + "\n",
        encoding="utf-8",
    )
    settings = manifest["settings"]
    code_sha = manifest.get("code_sha") or ""
    dataset_sha = manifest.get("dataset_sha") or ""
    judge_panel = list(manifest.get("judge_panel") or NATIVE_JUDGE_PANEL)
    failures = 0
    for slot in manifest["schedule"]:
        slot_id = generation_slot_id(slot)
        if slot_id in manifest.get("completed_slots", []):
            continue
        try:
            _run_slot(
                slot,
                slot_id=slot_id,
                settings=settings,
                code_sha=code_sha,
                dataset_sha=dataset_sha,
                judge_panel=judge_panel,
                dataset_dir=dataset_dir,
                cache_dir=cache_dir,
                run_dir=run_dir,
                config=config,
                spend_limit=spend_limit,
                ledger=ledger,
                run_id=run_id,
                execute=execute or _run_logged,
            )
        except _SlotFailure as exc:
            failures += 1
            with (run_dir / "failures.txt").open("a", encoding="utf-8") as handle:
                handle.write(redact(f"{slot_id}: {exc}\n"))
            continue
        fresh = load_manifest(path)
        done = fresh.setdefault("completed_slots", [])
        if slot_id not in done:
            done.append(slot_id)
        save_manifest(path, fresh)
    return 1 if failures else 0


class _SlotFailure(RuntimeError):
    pass


def _run_slot(
    slot: dict,
    *,
    slot_id: str,
    settings: dict,
    code_sha: str,
    dataset_sha: str,
    judge_panel: list[str],
    dataset_dir: Path,
    cache_dir: Path,
    run_dir: Path,
    config: dict,
    spend_limit: float,
    ledger,
    run_id: str,
    execute,
) -> None:
    from framing_study.transform import integrity_problems, transform

    condition = slot["condition"]
    representative = slot["representative_task"]
    source = dataset_dir / "tasks" / representative
    original = (source / "instruction.md").read_text(encoding="utf-8")
    contract_bytes = (source / "environment" / "app" / "contract.docx").read_bytes()
    transformed = transform(original, condition)
    problems = integrity_problems(original, condition, transformed) or []
    if problems:
        raise _SlotFailure("integrity_problems is non-empty; generation was not started")
    instruction_bytes = transformed.encode("utf-8")
    key = generation_cache_key(
        condition=condition,
        repetition=int(slot["repetition"]),
        model=slot["model"],
        settings=settings,
        code_sha=code_sha,
        dataset_sha=dataset_sha,
        instruction_bytes=instruction_bytes,
        contract_bytes=contract_bytes,
        group_id=slot["group_id"],
    )
    cached = load_generation(cache_dir, condition, key)
    generation_dir = run_dir / "generations" / slot_id
    generation_dir.mkdir(parents=True, exist_ok=True)
    output_contract = generation_dir / "contract.docx"
    if cached is not None:
        shutil.copy2(cached / "contract.docx", output_contract)
    else:
        output_contract = _generate(
            slot,
            slot_id=slot_id,
            transformed=transformed,
            key=key,
            settings=settings,
            code_sha=code_sha,
            dataset_sha=dataset_sha,
            dataset_dir=dataset_dir,
            cache_dir=cache_dir,
            run_dir=run_dir,
            output_contract=output_contract,
            config=config,
            spend_limit=spend_limit,
            ledger=ledger,
            run_id=run_id,
            execute=execute,
        )
    if not output_contract.is_file() or output_contract.stat().st_size == 0:
        raise _SlotFailure("generation produced no contract; no stand-in docx was written")
    _grade_variants(
        slot,
        output_contract=output_contract,
        dataset_dir=dataset_dir,
        cache_dir=cache_dir,
        run_dir=run_dir,
        slot_id=slot_id,
        judge_panel=judge_panel,
        config=config,
        spend_limit=spend_limit,
        ledger=ledger,
        run_id=run_id,
        execute=execute,
        jobs_dir=run_dir / "attempts" / slot_id,
    )


def _generate(
    slot: dict,
    *,
    slot_id: str,
    transformed: str,
    key: str,
    settings: dict,
    code_sha: str,
    dataset_sha: str,
    dataset_dir: Path,
    cache_dir: Path,
    run_dir: Path,
    output_contract: Path,
    config: dict,
    spend_limit: float,
    ledger,
    run_id: str,
    execute,
) -> Path:
    retries = int(settings.get("max_infrastructure_retries", config["max_infrastructure_retries"]))
    source = dataset_dir / "tasks" / slot["representative_task"]
    env = child_environ()
    attempts_root = run_dir / "attempts" / slot_id
    recovered = _recover_existing_artifact(attempts_root)
    if recovered is not None:
        shutil.copy2(recovered, output_contract)
        store_generation(
            cache_dir,
            condition=slot["condition"],
            key=key,
            identity=_generation_identity(slot, key, code_sha, dataset_sha),
            contract_path=output_contract,
        )
        return output_contract
    existing = _attempt_count(attempts_root)
    if existing > retries:
        raise _SlotFailure("infrastructure retries already exhausted")
    if existing:
        kind = _last_attempt_kind(attempts_root)
        if kind is not None and not is_infrastructure_failure(kind=kind):
            raise _SlotFailure(f"previous attempt failed ({kind}); not an infrastructure retry")
    last_kind = "other"
    for attempt in range(existing, retries + 1):
        if attempt > 0 and not _retry_fits(slot, config, ledger, run_id, spend_limit):
            raise _SlotFailure("infrastructure retry would exceed the spend limit")
        attempt_dir = attempts_root / f"attempt-{attempt}"
        workspace = attempt_dir / "workspace"
        task_dir = prepare_agent_workspace(
            dest=workspace,
            dataset_task_dir=source,
            dataset_root=dataset_dir,
            transformed_instruction=transformed,
        )
        jobs_dir = attempt_dir / "jobs"
        argv = harbor_run_argv(
            task_dir=task_dir,
            agent=settings["agent"],
            model=slot["model"],
            jobs_dir=jobs_dir,
            n_concurrent=int(settings.get("n_concurrent") or 1),
            max_turns=settings.get("max_turns"),
        )
        completed = execute(argv, env, attempt_dir / "logs")
        artifact = find_contract_artifact(jobs_dir)
        if artifact is not None:
            shutil.copy2(artifact, output_contract)
            store_generation(
                cache_dir,
                condition=slot["condition"],
                key=key,
                identity=_generation_identity(slot, key, code_sha, dataset_sha),
                contract_path=output_contract,
            )
            return output_contract
        last_kind = classify_process_failure(completed.returncode, completed.stderr or "") or "other"
        if not is_infrastructure_failure(kind=last_kind):
            raise _SlotFailure(
                f"generation failed ({last_kind}); not an infrastructure retry"
            )
    raise _SlotFailure(f"generation failed after infrastructure retries ({last_kind})")


def _grade_variants(
    slot: dict,
    *,
    output_contract: Path,
    dataset_dir: Path,
    cache_dir: Path,
    run_dir: Path,
    slot_id: str,
    judge_panel: list[str],
    config: dict,
    spend_limit: float,
    ledger,
    run_id: str,
    execute,
    jobs_dir: Path,
) -> None:
    output_bytes = output_contract.read_bytes()
    representative = slot["representative_task"]
    harbor_grade = None
    for attempt_dir in sorted((jobs_dir).glob("attempt-*/jobs")):
        harbor_grade = find_verifier_grade(attempt_dir, representative)
        if harbor_grade is not None:
            break
    for grade in slot["grades"]:
        task_id = grade["task_id"]
        variant_dir = dataset_dir / "tasks" / task_id
        rubric_path = variant_dir / "tests" / "rubrics.json"
        judge_py = variant_dir / "tests" / "judge.py"
        if not rubric_path.is_file() or not judge_py.is_file():
            raise _SlotFailure(f"variant grader files missing for {task_id}")
        rubric_bytes = rubric_path.read_bytes()
        key = grade_cache_key(
            output_bytes=output_bytes,
            variant_task_id=task_id,
            rubric_bytes=rubric_bytes,
            judge_panel=judge_panel,
            judge_settings=dict(JUDGE_SETTINGS),
        )
        if load_grade(cache_dir, key) is not None:
            continue
        dest = run_dir / "grades" / slot_id / task_id
        dest.mkdir(parents=True, exist_ok=True)
        if task_id == representative and harbor_grade is not None:
            _import_verifier_dir(harbor_grade.parent, dest)
            _store_grade_file(
                cache_dir,
                key=key,
                task_id=task_id,
                judge_panel=judge_panel,
                grade_path=dest / "grade.json",
            )
            continue
        _grade_with_judge(
            slot,
            judge_py=judge_py,
            contract=output_contract,
            dest=dest,
            cache_dir=cache_dir,
            key=key,
            task_id=task_id,
            judge_panel=judge_panel,
            config=config,
            spend_limit=spend_limit,
            ledger=ledger,
            run_id=run_id,
            execute=execute,
        )


def _grade_with_judge(
    slot: dict,
    *,
    judge_py: Path,
    contract: Path,
    dest: Path,
    cache_dir: Path,
    key: str,
    task_id: str,
    judge_panel: list[str],
    config: dict,
    spend_limit: float,
    ledger,
    run_id: str,
    execute,
) -> None:
    retries = int(config["max_infrastructure_retries"])
    env = child_environ()
    for previous in sorted(dest.glob("attempt-*")):
        previous_grade = previous / "verifier" / "grade.json"
        if previous_grade.is_file():
            _import_verifier_dir(previous_grade.parent, dest)
            _store_grade_file(
                cache_dir,
                key=key,
                task_id=task_id,
                judge_panel=judge_panel,
                grade_path=dest / "grade.json",
            )
            return
    existing = _attempt_count(dest)
    if existing > retries:
        raise _SlotFailure(f"grade retries already exhausted for {task_id}")
    if existing:
        kind = _last_attempt_kind(dest)
        if kind is not None and not is_infrastructure_failure(kind=kind):
            raise _SlotFailure(f"previous grade failed ({kind}); not retried")
    last_kind = "other"
    for attempt in range(existing, retries + 1):
        if attempt > 0 and not _retry_fits(slot, config, ledger, run_id, spend_limit):
            raise _SlotFailure("judge retry would exceed the spend limit")
        attempt_dir = dest / f"attempt-{attempt}"
        out_dir = attempt_dir / "verifier"
        argv = judge_argv(judge_py=judge_py, contract=contract, out_dir=out_dir)
        completed = execute(argv, env, attempt_dir / "logs")
        grade_path = out_dir / "grade.json"
        if grade_path.is_file():
            # A recorded score, including a low score, is final.
            _import_verifier_dir(out_dir, dest)
            _store_grade_file(
                cache_dir,
                key=key,
                task_id=task_id,
                judge_panel=judge_panel,
                grade_path=dest / "grade.json",
            )
            return
        last_kind = classify_process_failure(completed.returncode, completed.stderr or "") or "other"
        if not is_infrastructure_failure(kind=last_kind):
            raise _SlotFailure(f"grade failed for {task_id} ({last_kind}); not retried")
    raise _SlotFailure(f"grade failed for {task_id} after infrastructure retries ({last_kind})")


def _import_verifier_dir(verifier_dir: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("grade.json", "reward.json", "annotated_view.md"):
        source = verifier_dir / name
        if source.is_file():
            shutil.copy2(source, dest / name)
    judges = verifier_dir / "judges"
    if judges.is_dir():
        target = dest / "judges"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(judges, target)


def study_results(manifest: dict, run_dir: Path, dataset_dir: Path | None = None) -> dict:
    """Build the results object ``write_report`` reads.

    Rubric criteria and justifications are not copied into this object.
    """
    from framing_study.diagnostics import edit_diagnostics
    from framing_study.manifest import read_pins

    scope = manifest.get("scope") or "pilot"
    if scope == "smoke":
        groups = [manifest["smoke"]["group"]["group_id"]]
    else:
        groups = [group["group_id"] for group in manifest["pilot"]["groups"]]
    records = []
    for slot in manifest.get("schedule") or []:
        slot_id = generation_slot_id(slot)
        grade_root = run_dir / "grades" / slot_id
        grades: dict[str, dict] = {}
        for grade in slot["grades"]:
            path = grade_root / grade["task_id"] / "grade.json"
            if not path.is_file():
                continue
            grades[grade["variant"]] = _grade_for_report(json.loads(path.read_text(encoding="utf-8")))
        diagnostics = _pair_diagnostics(slot, slot_id, run_dir, dataset_dir, edit_diagnostics)
        records.append(
            {
                "model": slot["model"],
                "condition": slot["condition"],
                "input_group": slot["group_id"],
                "repetition": slot["repetition"],
                "retries": _retry_count(run_dir / "attempts" / slot_id),
                "grades": grades,
                "diagnostics": diagnostics,
            }
        )
    pins = read_pins() or {}
    settings = manifest.get("settings") or {}
    return {
        "synthetic": False,
        "pins": {
            "redlinebench_git_sha": manifest.get("code_sha") or pins.get("code_sha"),
            "dataset_revision": manifest.get("dataset_sha") or pins.get("dataset_sha"),
            "dataset_repo": pins.get("dataset_repo"),
            "harbor_version": settings.get("harbor_version"),
            "harbor_agent": settings.get("agent") or AGENT,
            "dataset_license": "CC-BY-4.0",
            "code_license": "MIT",
        },
        "models": list(manifest.get("models") or []),
        "harness": settings.get("agent") or AGENT,
        "seed": manifest.get("seed"),
        "repetitions": manifest.get("repetitions"),
        "input_groups": groups,
        "conditions": list(manifest.get("conditions") or []),
        "instruction_summary": _instruction_summary(),
        "records": records,
        "harbor_terminus2_system_prompt": manifest.get("harbor_terminus2_system_prompt"),
    }


def blind_cases(manifest: dict, run_dir: Path) -> list[dict]:
    """Primary STOCK vs MATCHED pairs for ``write_packet``.

    Output text is the saved annotated view. No redline text is invented.
    """
    by_key: dict[tuple, dict] = {}
    for slot in manifest.get("schedule") or []:
        if slot["condition"] not in {"STOCK", "MATCHED_SOFTWARE_REPLACEMENT"}:
            continue
        key = (slot["model"], slot["group_id"], slot["repetition"])
        by_key.setdefault(key, {})[slot["condition"]] = slot
    cases = []
    for (model, group_id, repetition), pair in by_key.items():
        if "STOCK" not in pair or "MATCHED_SOFTWARE_REPLACEMENT" not in pair:
            continue
        outputs = []
        flags: list[str] = []
        for condition in ("STOCK", "MATCHED_SOFTWARE_REPLACEMENT"):
            slot = pair[condition]
            slot_id = generation_slot_id(slot)
            view = _annotated_view(run_dir, slot_id, slot["representative_task"])
            grade_path = (
                run_dir / "grades" / slot_id / slot["representative_task"] / "grade.json"
            )
            if grade_path.is_file():
                payload = json.loads(grade_path.read_text(encoding="utf-8"))
                judges = list(payload.get("judges") or [])
                survivors = payload.get("survivors")
                if judges and survivors is not None and list(survivors) != judges:
                    flags.append("judge_disagreement")
                gate = payload.get("gate") or {}
                if gate.get("passed") is False:
                    flags.append("conspicuous_failure")
            outputs.append({"condition": condition, "text": view})
        representative = pair["STOCK"]["representative_task"]
        cases.append(
            {
                "id": f"{model}-{group_id}-r{repetition}",
                "role": "primary",
                "model": model,
                "input_group": group_id,
                "assignment": f"Task {representative}.",
                "flags": sorted(set(flags)),
                "outputs": outputs,
            }
        )
    return cases


def _annotated_view(run_dir: Path, slot_id: str, task_id: str) -> str:
    path = run_dir / "grades" / slot_id / task_id / "annotated_view.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "Annotated view was not saved. No document text was invented."


def _grade_for_report(payload: dict) -> dict:
    score = payload.get("score") or {}
    per = []
    for item in score.get("per_rubric") or []:
        if not isinstance(item, dict):
            continue
        per.append(
            {
                "id": item.get("rubric_id") or item.get("id"),
                "verdict": item.get("verdict"),
                "weight": item.get("weight"),
                "is_penalty": item.get("is_penalty"),
            }
        )
    kept_score = {
        key: value
        for key, value in score.items()
        if key not in {"per_rubric", "criteria", "justification"}
    }
    kept_score["per_rubric"] = per
    return {
        "gate": payload.get("gate"),
        "judges": payload.get("judges"),
        "survivors": payload.get("survivors"),
        "score": kept_score,
    }


def _pair_diagnostics(slot, slot_id, run_dir, dataset_dir, edit_diagnostics) -> dict:
    output = run_dir / "generations" / slot_id / "contract.docx"
    if dataset_dir is not None:
        source = (
            Path(dataset_dir)
            / "tasks"
            / slot["representative_task"]
            / "environment"
            / "app"
            / "contract.docx"
        )
        if source.is_file() and output.is_file():
            return edit_diagnostics((str(source), str(output)))
    if output.is_file():
        return edit_diagnostics(str(output))
    return {}


def _retry_count(attempts_root: Path) -> int:
    return max(0, _attempt_count(attempts_root) - 1)


def _instruction_summary() -> dict:
    try:
        import framing_study.pins as pins
    except ImportError:
        return {}
    spans = [
        getattr(pins, name)
        for name in ("D1_ORIGINAL", "D2_ORIGINAL", "D3_ORIGINAL")
        if getattr(pins, name, None)
    ]
    sentence = getattr(pins, "METAPHOR_SENTENCE", None)
    return {"designated_spans": spans, "condition_2_sentence": sentence}


def _generation_identity(slot: dict, key: str, code_sha: str, dataset_sha: str) -> dict:
    return {
        "domain": "generation",
        "condition": slot["condition"],
        "cache_key": key,
        "model": slot["model"],
        "group_id": slot["group_id"],
        "repetition": slot["repetition"],
        "code_sha": code_sha,
        "dataset_sha": dataset_sha,
    }


def _attempt_count(parent: Path) -> int:
    if not parent.is_dir():
        return 0
    return sum(
        1 for path in parent.iterdir() if path.is_dir() and path.name.startswith("attempt-")
    )


def _recover_existing_artifact(attempts_root: Path) -> Path | None:
    if not attempts_root.is_dir():
        return None
    for attempt_dir in sorted(attempts_root.glob("attempt-*")):
        artifact = find_contract_artifact(attempt_dir / "jobs")
        if artifact is not None:
            return artifact
    return None


def _last_attempt_kind(parent: Path) -> str | None:
    attempts = sorted(
        path for path in parent.iterdir() if path.is_dir() and path.name.startswith("attempt-")
    )
    if not attempts:
        return None
    last = attempts[-1]
    code_path = last / "logs" / "returncode.txt"
    stderr_path = last / "logs" / "stderr.txt"
    if not code_path.is_file():
        return "other"
    code = int(code_path.read_text(encoding="utf-8").strip() or "1")
    stderr = stderr_path.read_text(encoding="utf-8") if stderr_path.is_file() else ""
    return classify_process_failure(code, stderr)


def _store_grade_file(
    cache_dir: Path,
    *,
    key: str,
    task_id: str,
    judge_panel: list[str],
    grade_path: Path,
) -> None:
    payload = json.loads(grade_path.read_text(encoding="utf-8"))
    if "score" not in payload:
        raise _SlotFailure(f"grade.json for {task_id} has no score")
    store_grade(
        cache_dir,
        key=key,
        identity={
            "domain": "grade",
            "cache_key": key,
            "variant_task_id": task_id,
            "judge_panel": list(judge_panel),
            "judge_settings": dict(JUDGE_SETTINGS),
        },
        grade_path=grade_path,
    )
