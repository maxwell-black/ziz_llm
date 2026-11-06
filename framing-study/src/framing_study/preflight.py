"""No-cost checks for a live smoke or pilot run.

Provider variables are reported as set or unset. Values are never read
into the report. Exit 2 when a live run would be blocked.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from framing_study.catalog import (
    AGENT,
    CONDITIONS,
    HARBOR_SYSTEM_PROMPT_NOTE,
    PROVIDER_ENV_NAMES,
    fetch_task_ids,
    judge_panel_status,
    representative_tasks,
)
from framing_study.isolate import network_restriction_ready
from framing_study.manifest import read_pins

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
# network_mode / allow_internet=false is enforced from Harbor 0.20 onward.
_NETWORK_MIN = (0, 20, 0)


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.search(text or "")
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def provider_env_report(environ: dict[str, str] | None = None) -> list[dict[str, str]]:
    source = os.environ if environ is None else environ
    rows = []
    for name in PROVIDER_ENV_NAMES:
        rows.append({"name": name, "status": "set" if source.get(name) else "unset"})
    return rows


def egress_report(harbor_version_text: str | None) -> dict:
    """Say whether Harbor can deny agent egress.

    When it cannot, ``state`` is ``uncontrolled`` and ``detail`` contains
    the phrase ``egress is uncontrolled``.
    """
    parsed = parse_version(harbor_version_text or "")
    if parsed is None or parsed < _NETWORK_MIN:
        return {
            "state": "uncontrolled",
            "detail": (
                "egress is uncontrolled; Harbor is missing or older than "
                "0.20 and cannot enforce task.toml network_mode"
            ),
        }
    return {
        "state": "controlled",
        "detail": (
            "agent baseline [environment].network_mode = no-network; "
            "verifier [verifier].network_mode = allowlist of judge API hosts; "
            "identical across conditions. Harbor 0.25 may still allow resolved "
            "inference hosts so the shared terminus-2 agent can call its model. "
            + HARBOR_SYSTEM_PROMPT_NOTE
        ),
    }


def dataset_status(dataset_dir: Path, expected_sha: str | None) -> dict:
    revision_path = dataset_dir / "REVISION"
    recorded = (
        revision_path.read_text(encoding="utf-8").strip() if revision_path.is_file() else None
    )
    missing = []
    for task_id in fetch_task_ids():
        root = dataset_dir / "tasks" / task_id
        instruction = root / "instruction.md"
        contract = root / "environment" / "app" / "contract.docx"
        if not instruction.is_file() or not contract.is_file():
            missing.append(task_id)
    pin_ok = bool(expected_sha) and recorded == expected_sha
    return {
        "ok": pin_ok and not missing,
        "pin_matches": pin_ok,
        "recorded_sha": recorded,
        "expected_sha": expected_sha,
        "missing_tasks": missing,
        "status": "present" if pin_ok and not missing else "missing",
    }


def write_revision(dataset_dir: Path, sha: str) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "REVISION").write_text(sha + "\n", encoding="utf-8")


def transform_self_check(dataset_dir: Path) -> dict:
    try:
        from framing_study.transform import integrity_problems, transform
    except ImportError:
        return {"ok": False, "status": "missing", "detail": "transform is not installed yet"}
    problems = []
    checked = 0
    for row in representative_tasks():
        path = dataset_dir / "tasks" / row["representative"] / "instruction.md"
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        checked += 1
        for condition in CONDITIONS:
            transformed = transform(original, condition)
            found = integrity_problems(original, condition, transformed) or []
            if found:
                problems.append(
                    {
                        "task": row["representative"],
                        "condition": condition,
                        "problems": [str(item) for item in found],
                    }
                )
    if checked == 0:
        return {
            "ok": False,
            "status": "unchecked",
            "detail": "no representative instruction.md in the dataset directory",
        }
    if problems:
        return {
            "ok": False,
            "status": "failed",
            "detail": "integrity_problems is non-empty",
            "problems": problems,
        }
    return {
        "ok": True,
        "status": "passed",
        "detail": f"checked {checked} representative instructions",
    }


def _tool_version(binary: str | None, runner) -> str | None:
    if not binary:
        return None
    try:
        completed = runner(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    return text or None


def preflight_report(
    config: dict,
    *,
    environ: dict[str, str] | None = None,
    which=shutil.which,
    runner=subprocess.run,
) -> dict:
    environ = os.environ if environ is None else environ
    reasons: list[str] = []
    pins = read_pins()
    if pins is None:
        reasons.append("framing_study.pins is not installed yet")
    panel = judge_panel_status(config["judge_panel"])
    if not panel["ok"]:
        reasons.append(panel["reason"])
    if config.get("agent") != AGENT:
        reasons.append(f"agent must be {AGENT} for every model")
    if not config.get("comparisons_ok", True):
        reasons.append("config comparisons do not match the planned contrasts")

    providers = provider_env_report(environ)
    present = {row["name"]: row["status"] == "set" for row in providers}
    # gpt-5.4-mini is called through OpenRouter when that key is present
    # and no platform.openai.com key is. The alias lives in the child
    # interpreter; this check only decides whether a live run may start.
    openai_ready = present["OPENAI_API_KEY"] or bool(environ.get("OPENROUTER_API_KEY"))
    missing_keys = []
    if not openai_ready:
        missing_keys.append("OPENAI_API_KEY")
    if not present["ANTHROPIC_API_KEY"]:
        missing_keys.append("ANTHROPIC_API_KEY")
    if not present["GEMINI_API_KEY"] and not present["GOOGLE_GENERATIVE_AI_API_KEY"]:
        missing_keys.append("GEMINI_API_KEY or GOOGLE_GENERATIVE_AI_API_KEY")
    if missing_keys:
        reasons.append("missing provider env: " + ", ".join(missing_keys))

    docker_bin = which("docker")
    docker = {
        "status": "present" if docker_bin else "missing",
        "path": docker_bin or "",
    }
    if not docker_bin:
        reasons.append("docker is missing")
    else:
        info = _tool_version(docker_bin, runner)
        # `docker --version` is enough to see the client. A dead daemon still
        # blocks a live run; probe `docker info` when the client exists.
        try:
            info_run = runner(
                [docker_bin, "info"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if info_run.returncode != 0:
                docker["status"] = "unavailable"
                reasons.append("docker info failed")
        except (OSError, subprocess.TimeoutExpired):
            docker["status"] = "unavailable"
            reasons.append("docker info failed")
        del info

    harbor_bin = which("harbor")
    harbor_text = _tool_version(harbor_bin, runner) if harbor_bin else None
    harbor = {
        "status": "present" if harbor_bin else "missing",
        "path": harbor_bin or "",
        "version_text": harbor_text or "",
        "configured": config.get("harbor_version"),
    }
    if not harbor_bin:
        reasons.append("harbor is missing")

    egress = egress_report(harbor_text if harbor_bin else None)
    if egress["state"] != "controlled" and not config.get("allows_uncontrolled_egress", False):
        reasons.append(egress["detail"])

    dataset = dataset_status(Path(config["dataset_dir"]), None if pins is None else pins["dataset_sha"])
    if not dataset["ok"]:
        reasons.append("dataset pin is not present at the configured dataset_dir")

    sample_toml = _sample_task_toml(Path(config["dataset_dir"]))
    if sample_toml is not None and not network_restriction_ready(sample_toml):
        reasons.append("task.toml network restriction could not be applied")
        if egress["state"] == "controlled":
            egress = {
                "state": "uncontrolled",
                "detail": "egress is uncontrolled; task.toml has no environment section to restrict",
            }

    transform = transform_self_check(Path(config["dataset_dir"]))
    if not transform["ok"]:
        reasons.append(transform["detail"])

    # Deduplicate while keeping order.
    unique: list[str] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return {
        "blocked": bool(unique),
        "blocked_reasons": unique,
        "providers": providers,
        "openai_route": (
            "openrouter"
            if not present["OPENAI_API_KEY"] and environ.get("OPENROUTER_API_KEY")
            else "openai"
        ),
        "docker": docker,
        "harbor": harbor,
        "dataset": dataset,
        "transform": transform,
        "egress": egress,
        "pins": pins,
        "judge_panel": panel,
        "system_prompt": HARBOR_SYSTEM_PROMPT_NOTE,
    }


def _sample_task_toml(dataset_dir: Path) -> str | None:
    for task_id in fetch_task_ids():
        path = dataset_dir / "tasks" / task_id / "task.toml"
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def format_preflight(report: dict) -> str:
    lines = []
    for row in report["providers"]:
        lines.append(f"{row['name']}: {row['status']}")
    if report.get("openai_route") == "openrouter":
        lines.append("openai_route: openrouter (native id openai/gpt-5.4-mini)")
    lines.append(f"docker: {report['docker']['status']}")
    lines.append(
        "harbor: {status} configured={configured}".format(
            status=report["harbor"]["status"],
            configured=report["harbor"].get("configured") or "",
        )
    )
    if report["harbor"].get("version_text"):
        # Version text is a tool banner, not a credential.
        lines.append("harbor_version_text: " + report["harbor"]["version_text"].splitlines()[0])
    lines.append(f"dataset_pin: {report['dataset']['status']}")
    lines.append(f"transform: {report['transform']['status']}")
    lines.append(f"egress: {report['egress']['state']}")
    lines.append(report["egress"]["detail"])
    lines.append(report["system_prompt"])
    if report["blocked"]:
        lines.append("blocked:")
        for reason in report["blocked_reasons"]:
            lines.append(f"- {reason}")
    return "\n".join(lines) + "\n"
