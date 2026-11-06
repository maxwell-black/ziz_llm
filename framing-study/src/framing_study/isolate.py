"""Fresh agent workspaces and log redaction.

The workspace is a copy of one dataset task. The starting contract is
that dataset file. The process cwd, Cursor rules, and the study report
are not copied. Harbor receives only the task directory.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from framing_study.catalog import HARBOR_SYSTEM_PROMPT_NOTE, JUDGE_ALLOW_HOSTS

_KEY_ASSIGN = re.compile(
    r"(?i)\b("
    r"OPENAI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_GENERATIVE_AI_API_KEY|"
    r"HF_TOKEN|HUGGING_FACE_HUB_TOKEN|"
    r"[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)"
    r")\b(\s*[=:]\s*)(\S+)"
)
_SK = re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}")

_FORBIDDEN_NAMES = {
    ".cursorrules",
    "AGENTS.md",
    ".cursor",
}


def redact(text: str) -> str:
    """Replace credential values. Names of variables are kept."""
    text = _KEY_ASSIGN.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _SK.sub("[REDACTED]", text)
    return text


def apply_network_restriction(text: str) -> str:
    """Deny agent egress and allowlist judge hosts on the verifier.

    The same text is applied for every condition. Condition names are
    not written into the task file.
    """
    updated = _upsert_section(text, "environment", {"network_mode": '"no-network"'})
    hosts = ", ".join(f'"{host}"' for host in JUDGE_ALLOW_HOSTS)
    updated = _upsert_section(
        updated,
        "verifier",
        {
            "network_mode": '"allowlist"',
            "allowed_hosts": f"[{hosts}]",
        },
    )
    return updated


def _upsert_section(text: str, section: str, keys: dict[str, str]) -> str:
    lines = text.splitlines(keepends=True)
    header = f"[{section}]"
    start = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        raise ValueError(f"task.toml missing [{section}]")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    body = lines[start + 1 : end]
    kept: list[str] = []
    seen: set[str] = set()
    for line in body:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in keys:
            kept.append(f"{name} = {keys[name]}\n")
            seen.add(name)
            continue
        kept.append(line if line.endswith("\n") else line + "\n")
    missing = [f"{name} = {keys[name]}\n" for name in keys if name not in seen]
    rendered = "".join([*lines[: start + 1], *missing, *kept, *lines[end:]])
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def network_restriction_ready(sample_toml: str) -> bool:
    try:
        updated = apply_network_restriction(sample_toml)
    except ValueError:
        return False
    return (
        updated.count('network_mode = "no-network"') == 1
        and 'network_mode = "allowlist"' in updated
        and all(host in updated for host in JUDGE_ALLOW_HOSTS)
    )


def ensure_terminus_packages(dockerfile: str) -> str:
    """Install tmux and asciinema in the task image.

    Terminus-2 starts a tmux session after the network lock, so apt inside
    the running container cannot fetch them. The same packages are added
    for every condition. The rest of the Dockerfile stays as published.
    """
    needed = ("tmux", "asciinema")
    if all(package in dockerfile for package in needed):
        return dockerfile
    needle = "ca-certificates curl git unzip"
    if needle not in dockerfile:
        raise ValueError("Dockerfile has no apt package line for terminus tools")
    return dockerfile.replace(needle, needle + " tmux asciinema", 1)


def prepare_agent_workspace(
    *,
    dest: Path,
    dataset_task_dir: Path,
    dataset_root: Path,
    transformed_instruction: str,
) -> Path:
    """Copy ``dataset_task_dir`` into a new workspace and return that task dir.

    ``dest`` must not already exist. The contract bytes stay equal to the
    dataset file. ``instruction.md`` is replaced with the transformed text.
    ``task.toml`` receives the shared network restriction and nothing else.
    """
    if dest.exists():
        raise FileExistsError(f"refusing to reuse workspace {dest}")
    source = dataset_task_dir.resolve()
    root = dataset_root.resolve()
    if source != root and root not in source.parents:
        raise RuntimeError("starting task is not under the dataset directory")
    source_contract = source / "environment" / "app" / "contract.docx"
    if not source_contract.is_file():
        raise FileNotFoundError(f"dataset contract missing: {source_contract}")
    if not (source / "instruction.md").is_file():
        raise FileNotFoundError(f"dataset instruction missing: {source / 'instruction.md'}")
    if not (source / "task.toml").is_file():
        raise FileNotFoundError(f"dataset task.toml missing: {source / 'task.toml'}")

    dest.mkdir(parents=True)
    (dest / "HARBOR_SYSTEM_PROMPT.txt").write_text(
        HARBOR_SYSTEM_PROMPT_NOTE + "\n",
        encoding="utf-8",
    )
    task_dir = dest / "tasks" / source.name
    shutil.copytree(source, task_dir, symlinks=False)
    contract = task_dir / "environment" / "app" / "contract.docx"
    if contract.read_bytes() != source_contract.read_bytes():
        raise RuntimeError("workspace contract does not match the dataset file")
    (task_dir / "instruction.md").write_text(transformed_instruction, encoding="utf-8")
    dockerfile = task_dir / "environment" / "Dockerfile"
    dockerfile.write_text(
        ensure_terminus_packages(dockerfile.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    toml_path = task_dir / "task.toml"
    toml_path.write_text(
        apply_network_restriction(toml_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    _reject_host_contamination(task_dir)
    return task_dir


def _reject_host_contamination(task_dir: Path) -> None:
    for path in task_dir.rglob("*"):
        if path.name in _FORBIDDEN_NAMES or ".cursor" in path.parts:
            raise RuntimeError(f"refusing to leave {path.name} in the agent workspace")
