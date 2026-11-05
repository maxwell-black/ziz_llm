"""Synthetic orchestration tests. No network and no provider keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from framing_study.budget import decide_spend, estimate_run  # noqa: E402
from framing_study.cache import (  # noqa: E402
    generation_cache_key,
    generation_cache_path,
    grade_cache_key,
    load_generation,
    store_generation,
)
from framing_study.catalog import (  # noqa: E402
    CONDITIONS,
    NATIVE_JUDGE_PANEL,
    input_group_id,
    pilot_groups,
    smoke_group,
)
from framing_study.cli import main  # noqa: E402
from framing_study.isolate import apply_network_restriction, redact  # noqa: E402
from framing_study.manifest import build_manifest, open_manifest, save_manifest  # noqa: E402
from framing_study.preflight import provider_env_report  # noqa: E402
from framing_study.runner import (  # noqa: E402
    harbor_run_argv,
    is_infrastructure_failure,
    study_results,
)
from framing_study.schedule import build_schedule, generation_slot_id, schedule_keys  # noqa: E402

_SETTINGS = {"agent": "terminus-2", "max_tokens": None, "temperature": None}


def test_input_group_id_from_task_id():
    assert input_group_id("redline-s1-t1-g01a") == "s1-t1-g01"
    assert input_group_id("redline-s1-t1-g01e") == "s1-t1-g01"
    assert input_group_id("redline-s2-t2-g01c") == "s2-t2-g01"
    assert input_group_id("redline-s2-t1-g01d") == "s2-t1-g01"
    assert input_group_id("redline-s2-t4-g03a") == "s2-t4-g03"
    assert input_group_id("redline-s3-t4-g01a") == "s3-t4-g01"


def test_siblings_have_one_generation_slot_and_n_grade_slots():
    group = next(row for row in pilot_groups() if row["group_id"] == "s1-t1-g01")
    schedule = build_schedule(["model-a"], [group], list(CONDITIONS), [0], seed=20261105)
    assert len(schedule) == len(CONDITIONS)
    for slot in schedule:
        assert slot["representative_task"] == "redline-s1-t1-g01a"
        assert len(slot["grades"]) == 5
        assert {grade["variant"] for grade in slot["grades"]} == set("abcde")
        assert {grade["task_id"] for grade in slot["grades"]} == set(group["task_ids"])
    smoke_ids = set(smoke_group()["task_ids"])
    pilot_ids = {task_id for row in pilot_groups() for task_id in row["task_ids"]}
    assert smoke_ids.isdisjoint(pilot_ids)
    assert smoke_group()["scored"] is False
    assert smoke_group()["representative"] == "redline-s2-t1-g01a"


def test_cache_keys_differ_by_condition_and_from_grade_keys(tmp_path):
    common = dict(
        repetition=0,
        model="model-a",
        settings=_SETTINGS,
        code_sha="code",
        dataset_sha="dataset",
        instruction_bytes=b"instruction-bytes",
        contract_bytes=b"contract-bytes",
        group_id="s1-t1-g01",
    )
    stock = generation_cache_key(condition="STOCK", **common)
    other = generation_cache_key(condition="TASK_ONLY", **common)
    assert stock != other
    assert generation_cache_key(
        condition="STOCK", **{**common, "group_id": "s2-t2-g01"}
    ) != stock
    grade = grade_cache_key(
        output_bytes=b"contract-bytes",
        variant_task_id="redline-s1-t1-g01b",
        rubric_bytes=b"{}",
        judge_panel=list(NATIVE_JUDGE_PANEL),
        judge_settings={"mode": "panel", "override": False},
    )
    assert grade != stock
    assert grade != other

    contract = tmp_path / "contract.docx"
    contract.write_bytes(b"PK-not-empty")
    cache = tmp_path / "cache"
    store_generation(
        cache,
        condition="STOCK",
        key=stock,
        identity={"domain": "generation", "condition": "STOCK", "cache_key": stock},
        contract_path=contract,
    )
    assert load_generation(cache, "STOCK", stock) is not None
    assert load_generation(cache, "TASK_ONLY", stock) is None
    leaked = generation_cache_path(cache, "TASK_ONLY", stock)
    leaked.parent.mkdir(parents=True, exist_ok=True)
    leaked.mkdir()
    (leaked / "contract.docx").write_bytes(b"PK-not-empty")
    (leaked / "identity.json").write_text(
        json.dumps({"domain": "generation", "condition": "STOCK", "cache_key": stock}),
        encoding="utf-8",
    )
    assert load_generation(cache, "TASK_ONLY", stock) is None


def test_budget_refuses_missing_limit_empty_prices_and_over_limit():
    missing = decide_spend(estimate_usd=1.0, spend_limit=None, in_flight_usd=0)
    assert missing.allowed is False
    assert "missing" in missing.reason

    unknown = estimate_run(prices={}, generation_calls=["model-a"], judge_calls=["judge"])
    assert unknown["known"] is False
    assert unknown["generation_usd"] is None
    assert unknown["judging_usd"] is None
    assert unknown["total_usd"] is None
    refused = decide_spend(
        estimate_usd=unknown["total_usd"],
        spend_limit=100,
        in_flight_usd=0,
    )
    assert refused.allowed is False
    assert "unknown" in refused.reason

    over = decide_spend(estimate_usd=5, spend_limit=4, in_flight_usd=0)
    assert over.allowed is False
    assert "exceeds" in over.reason

    negative = decide_spend(estimate_usd=0, spend_limit=-1, in_flight_usd=0)
    assert negative.allowed is False


def test_budget_adds_in_flight_before_comparing_to_limit():
    blocked = decide_spend(estimate_usd=3, spend_limit=5, in_flight_usd=2.5)
    assert blocked.allowed is False
    assert blocked.projected_usd == pytest.approx(5.5)

    allowed = decide_spend(estimate_usd=3, spend_limit=5, in_flight_usd=2)
    assert allowed.allowed is True
    assert allowed.projected_usd == pytest.approx(5)


def test_manifest_schedule_is_a_permutation_of_the_grid():
    groups = [
        {
            "group_id": "s1-t1-g01",
            "variants": ["a", "b"],
            "representative": "redline-s1-t1-g01a",
            "task_ids": ["redline-s1-t1-g01a", "redline-s1-t1-g01b"],
        },
        {
            "group_id": "s1-t3-g01",
            "variants": ["a"],
            "representative": "redline-s1-t3-g01a",
            "task_ids": ["redline-s1-t3-g01a"],
        },
    ]
    models = ["model-a", "model-b"]
    conditions = ["STOCK", "TASK_ONLY"]
    manifest = build_manifest(
        scope="pilot",
        models=models,
        groups=groups,
        repetitions=2,
        seed=20261105,
        settings=_SETTINGS,
        prices={},
        spend_limit=None,
        in_flight_usd=0,
        code_sha="code",
        dataset_sha="dataset",
        transform_sha=None,
        judge_panel=list(NATIVE_JUDGE_PANEL),
        judge_panel_overridden=False,
        conditions=conditions,
    )
    keys = schedule_keys(manifest["schedule"])
    expected = [
        (model, group["group_id"], condition, repetition)
        for model in models
        for group in groups
        for condition in conditions
        for repetition in (0, 1)
    ]
    assert sorted(keys) == sorted(expected)
    assert len(keys) == len(set(keys))
    model_order = [slot["model"] for slot in manifest["schedule"]]
    assert model_order == sorted(model_order, key=models.index)
    widths = {group["group_id"]: len(group["variants"]) for group in groups}
    for slot in manifest["schedule"]:
        assert len(slot["grades"]) == widths[slot["group_id"]]
    assert manifest["comparisons"][0] == {
        "name": "primary",
        "treatment": "MATCHED_SOFTWARE_REPLACEMENT",
        "control": "STOCK",
    }
    assert manifest["comparisons"][1]["treatment"] == "STOCK_PLUS_METAPHOR"
    assert {row["control"] for row in manifest["comparisons"][2:]} == {"TASK_ONLY"}
    assert manifest["judge_panel_overridden"] is False
    assert manifest["judge_panel"] == list(NATIVE_JUDGE_PANEL)
    again = build_schedule(models, groups, conditions, [0, 1], seed=20261105)
    assert schedule_keys(again) == schedule_keys(
        build_schedule(models, groups, conditions, [0, 1], seed=20261105)
    )


def test_resume_does_not_reshuffle(tmp_path):
    path = tmp_path / "manifest.json"
    original = {
        "schedule": [
            {
                "model": "model-a",
                "group_id": "s1-t1-g01",
                "condition": "STOCK",
                "repetition": 0,
                "grades": [{"task_id": "redline-s1-t1-g01a", "variant": "a"}],
            }
        ],
        "seed": 20261105,
    }
    save_manifest(path, original)
    calls = {"n": 0}

    def rebuild():
        calls["n"] += 1
        return {"schedule": [{"reshuffled": True}], "seed": 1}

    loaded = open_manifest(path, rebuild)
    assert calls["n"] == 0
    assert loaded["schedule"] == original["schedule"]
    assert loaded["seed"] == 20261105


def test_retry_classifier_accepts_429_and_rejects_low_score():
    assert is_infrastructure_failure(status_code=429) is True
    assert is_infrastructure_failure(status_code=500) is True
    assert is_infrastructure_failure(status_code=503) is True
    assert is_infrastructure_failure(kind="timeout") is True
    assert is_infrastructure_failure(kind="connection_error") is True
    assert is_infrastructure_failure(kind="low_score") is False
    assert is_infrastructure_failure(status_code=200, kind="low_score") is False
    assert is_infrastructure_failure(status_code=400) is False


def test_isolate_redacts_fake_key():
    raw = (
        "Authorization: Bearer sk-test-FAKEKEY1234567890\n"
        "OPENAI_API_KEY=sk-test-FAKEKEY1234567890\n"
    )
    cleaned = redact(raw)
    assert "FAKEKEY1234567890" not in cleaned
    assert "sk-test-FAKEKEY1234567890" not in cleaned
    assert "[REDACTED]" in cleaned


def test_provider_report_does_not_include_secret_values():
    secret = "sk-test-FAKEKEY1234567890"
    report = provider_env_report(
        {
            "OPENAI_API_KEY": secret,
            "ANTHROPIC_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GOOGLE_GENERATIVE_AI_API_KEY": "",
        }
    )
    blob = json.dumps(report)
    assert secret not in blob
    assert "FAKEKEY" not in blob
    assert report[0] == {"name": "OPENAI_API_KEY", "status": "set"}
    assert report[1]["status"] == "unset"


def test_network_restriction_is_identical_and_unlabeled():
    source = "\n".join(
        [
            'schema_version = "1.3"',
            "[environment]",
            "cpus = 2",
            "memory_mb = 4096",
            "",
            "[agent]",
            "timeout_sec = 3600.0",
            "",
            "[verifier]",
            "timeout_sec = 1200.0",
            "",
            "[verifier.env]",
            'OPENAI_API_KEY = "${OPENAI_API_KEY}"',
            "",
        ]
    )
    first = apply_network_restriction(source)
    second = apply_network_restriction(first)
    assert first == second
    assert 'network_mode = "no-network"' in first
    assert 'network_mode = "allowlist"' in first
    for label in ("STOCK", "TASK_ONLY", "METAPHOR", "MATCHED_SOFTWARE"):
        assert label not in first


def test_harbor_argv_uses_shared_terminus_agent():
    argv = harbor_run_argv(
        task_dir=Path("/tmp/isolated/tasks/redline-s1-t1-g01a"),
        agent="terminus-2",
        model="openai/example",
        jobs_dir=Path("/tmp/isolated/jobs"),
    )
    assert argv[:2] == ["harbor", "run"]
    assert "terminus-2" in argv
    assert "claude-code" not in argv
    assert "codex" not in argv
    assert "--agent-kwarg" not in argv
    joined = " ".join(argv)
    assert "STOCK" not in joined
    assert "/tmp/isolated/tasks/redline-s1-t1-g01a" in joined


def _temp_config(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / "pilot.yaml"
    if text is None:
        text = (ROOT / "config" / "pilot.yaml").read_text(encoding="utf-8")
        text = text.replace("output_dir: runs", f"output_dir: {tmp_path / 'runs'}")
        text = text.replace(
            "cache_dir: .cache/framing-study",
            f"cache_dir: {tmp_path / 'cache'}",
        )
        text = text.replace(
            "dataset_dir: .cache/redlinebench",
            f"dataset_dir: {tmp_path / 'dataset'}",
        )
    path.write_text(text, encoding="utf-8")
    return path


def test_smoke_refuses_when_spend_limit_omitted(tmp_path, capsys):
    config = _temp_config(tmp_path)
    code = main(["--config", str(config), "smoke"])
    captured = capsys.readouterr()
    assert code == 2
    assert "missing spend limit" in captured.err
    assert list(tmp_path.rglob("*.docx")) == []
    assert not (tmp_path / "runs" / "smoke" / "manifest.json").exists()


def test_smoke_refuses_when_prices_empty(tmp_path, capsys):
    text = (ROOT / "config" / "pilot.yaml").read_text(encoding="utf-8")
    text = text.replace("output_dir: runs", f"output_dir: {tmp_path / 'runs'}")
    text = text.split("prices_usd_per_million:", 1)[0] + "prices_usd_per_million: {}\n"
    config = _temp_config(tmp_path, text)
    code = main(["--config", str(config), "smoke", "--spend-limit", "10"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown" in captured.err
    assert list(tmp_path.rglob("*.docx")) == []


def test_yaml_spend_limit_is_not_a_default(tmp_path, capsys):
    text = (ROOT / "config" / "pilot.yaml").read_text(encoding="utf-8")
    text = text.replace("spend_limit: null", "spend_limit: 100")
    text = text.replace("output_dir: runs", f"output_dir: {tmp_path / 'runs'}")
    config = _temp_config(tmp_path, text)
    code = main(["--config", str(config), "pilot"])
    captured = capsys.readouterr()
    assert code == 2
    assert "missing spend limit" in captured.err


def test_cost_prints_unknown_components_when_prices_empty(tmp_path, capsys):
    text = (ROOT / "config" / "pilot.yaml").read_text(encoding="utf-8")
    text = text.split("prices_usd_per_million:", 1)[0] + "prices_usd_per_million: {}\n"
    config = _temp_config(tmp_path, text)
    code = main(["--config", str(config), "cost"])
    captured = capsys.readouterr()
    assert code == 0
    for label in ("generation_usd: unknown", "judging_usd: unknown", "infra_usd: unknown"):
        assert label in captured.out
    assert "scope: pilot" in captured.out
    assert "scope: smoke" in captured.out


def test_report_and_blind_when_uninstalled(capsys):
    try:
        import framing_study.report  # noqa: F401
    except ImportError:
        code = main(["report"])
        assert code == 1
        assert "reporting is not installed yet" in capsys.readouterr().err
    else:
        pytest.skip("framing_study.report is installed")
    try:
        import framing_study.blind  # noqa: F401
    except ImportError:
        code = main(["blind"])
        assert code == 1
        assert "reporting is not installed yet" in capsys.readouterr().err
    else:
        pytest.skip("framing_study.blind is installed")


def test_study_results_drop_rubric_text(tmp_path):
    manifest = {
        "scope": "pilot",
        "pilot": {"groups": [{"group_id": "s1-t1-g01"}]},
        "smoke": {"group": {"group_id": "s2-t1-g01"}},
        "schedule": [
            {
                "model": "m",
                "condition": "STOCK",
                "group_id": "s1-t1-g01",
                "repetition": 0,
                "representative_task": "redline-s1-t1-g01a",
                "grades": [{"task_id": "redline-s1-t1-g01a", "variant": "a"}],
            }
        ],
        "models": ["m"],
        "conditions": ["STOCK"],
        "settings": {"agent": "terminus-2", "harbor_version": "0.25.0"},
        "seed": 1,
        "repetitions": 1,
        "code_sha": "c",
        "dataset_sha": "d",
    }
    slot_id = generation_slot_id(manifest["schedule"][0])
    grade_dir = tmp_path / "grades" / slot_id / "redline-s1-t1-g01a"
    grade_dir.mkdir(parents=True)
    (grade_dir / "grade.json").write_text(
        json.dumps(
            {
                "gate": {"passed": True},
                "judges": ["openai/gpt-5.4-mini"],
                "survivors": ["openai/gpt-5.4-mini"],
                "score": {
                    "weighted": 1,
                    "per_rubric": [
                        {
                            "rubric_id": "r1",
                            "verdict": "PASS",
                            "weight": 1,
                            "criteria": "SECRET_CRITERION",
                            "justification": "SECRET_JUSTIFICATION",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    results = study_results(manifest, tmp_path, tmp_path)
    blob = json.dumps(results)
    assert "SECRET_CRITERION" not in blob
    assert "SECRET_JUSTIFICATION" not in blob
    assert results["records"][0]["grades"]["a"]["score"]["per_rubric"][0]["verdict"] == "PASS"


def test_report_without_a_manifest_writes_nothing(tmp_path, capsys):
    config = _temp_config(tmp_path)
    code = main(["--config", str(config), "report"])
    captured = capsys.readouterr()
    assert code == 1
    assert "no scored results" in captured.err
    assert list(tmp_path.rglob("report.md")) == []


def test_manifest_uses_pin_shas_when_present():
    try:
        import framing_study.pins as pins
    except ImportError:
        pytest.skip("framing_study.pins is not installed yet")
    code = getattr(pins, "CODE_SHA", None) or getattr(pins, "code_sha", None)
    dataset = getattr(pins, "DATASET_SHA", None) or getattr(pins, "dataset_sha", None)
    if not code or not dataset:
        pytest.skip("framing_study.pins has no code/dataset sha constants yet")
    from framing_study.manifest import read_pins

    loaded = read_pins()
    assert loaded is not None
    assert loaded["code_sha"] == str(code)
    assert loaded["dataset_sha"] == str(dataset)
