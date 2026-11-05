"""Generation and grade cache keys.

A generation entry is stored under its condition directory. Loading a
condition never opens another condition's directory. Grade entries live
in a separate tree and use a different hash domain.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from framing_study.catalog import CONDITIONS


def _digest(parts: list[bytes]) -> str:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(len(part).to_bytes(8, "big"))
        hasher.update(part)
    return hasher.hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )


def generation_cache_key(
    *,
    condition: str,
    repetition: int,
    model: str,
    settings: dict,
    code_sha: str,
    dataset_sha: str,
    instruction_bytes: bytes,
    contract_bytes: bytes,
    group_id: str,
) -> str:
    """Hash the generation identity, including the instruction and contract bytes."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    return _digest(
        [
            b"generation",
            condition.encode("utf-8"),
            str(repetition).encode("utf-8"),
            model.encode("utf-8"),
            _canonical(settings),
            code_sha.encode("utf-8"),
            dataset_sha.encode("utf-8"),
            instruction_bytes,
            contract_bytes,
            group_id.encode("utf-8"),
        ]
    )


def grade_cache_key(
    *,
    output_bytes: bytes,
    variant_task_id: str,
    rubric_bytes: bytes,
    judge_panel: list[str],
    judge_settings: dict,
) -> str:
    """Hash one variant grade. This domain does not match generation keys."""
    return _digest(
        [
            b"grade",
            output_bytes,
            variant_task_id.encode("utf-8"),
            rubric_bytes,
            _canonical(list(judge_panel)),
            _canonical(judge_settings),
        ]
    )


def _condition_dir(cache_dir: Path, condition: str) -> Path:
    if condition not in CONDITIONS or condition in {".", ".."} or "/" in condition:
        raise ValueError(f"refusing cache path for condition {condition!r}")
    return cache_dir / "generation" / condition


def generation_cache_path(cache_dir: Path, condition: str, key: str) -> Path:
    if not key or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        raise ValueError("generation cache key is not a sha256 hex digest")
    return _condition_dir(cache_dir, condition) / key


def grade_cache_path(cache_dir: Path, key: str) -> Path:
    if not key or len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
        raise ValueError("grade cache key is not a sha256 hex digest")
    return cache_dir / "grade" / key


def store_generation(
    cache_dir: Path,
    *,
    condition: str,
    key: str,
    identity: dict,
    contract_path: Path,
) -> Path:
    """Store one completed generation. Does not write into another condition."""
    if identity.get("condition") != condition or identity.get("domain") != "generation":
        raise ValueError("generation identity does not match the condition directory")
    if identity.get("cache_key") != key:
        raise ValueError("generation identity cache_key does not match")
    dest = generation_cache_path(cache_dir, condition, key)
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "contract.docx"
    data = contract_path.read_bytes()
    if not data:
        raise ValueError("refusing to cache an empty contract")
    if target.is_file() and target.read_bytes() != data:
        raise ValueError("generation cache already holds different output bytes")
    if not target.is_file():
        target.write_bytes(data)
    (dest / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dest


def load_generation(cache_dir: Path, condition: str, key: str) -> Path | None:
    """Load one condition's generation. Never searches other conditions."""
    dest = generation_cache_path(cache_dir, condition, key)
    ident_path = dest / "identity.json"
    contract = dest / "contract.docx"
    if not ident_path.is_file() or not contract.is_file():
        return None
    identity = json.loads(ident_path.read_text(encoding="utf-8"))
    if identity.get("domain") != "generation":
        return None
    if identity.get("condition") != condition:
        return None
    if identity.get("cache_key") != key:
        return None
    return dest


def store_grade(
    cache_dir: Path,
    *,
    key: str,
    identity: dict,
    grade_path: Path,
) -> Path:
    if identity.get("domain") != "grade" or identity.get("cache_key") != key:
        raise ValueError("grade identity does not match the grade cache")
    dest = grade_cache_path(cache_dir, key)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "grade.json").write_bytes(grade_path.read_bytes())
    (dest / "identity.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return dest


def load_grade(cache_dir: Path, key: str) -> Path | None:
    dest = grade_cache_path(cache_dir, key)
    ident_path = dest / "identity.json"
    grade = dest / "grade.json"
    if not ident_path.is_file() or not grade.is_file():
        return None
    identity = json.loads(ident_path.read_text(encoding="utf-8"))
    if identity.get("domain") != "grade" or identity.get("cache_key") != key:
        return None
    return dest
