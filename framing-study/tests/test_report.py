"""Report, native score, diagnostics, and blinding tests. No network."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from framing_study.aggregate import (  # noqa: E402
    reward_from_rubrics,
    rubric_passes,
    score_record,
    score_variant,
    summarize,
)
from framing_study.blind import write_packet  # noqa: E402
from framing_study.diagnostics import edit_diagnostics  # noqa: E402
from framing_study.report import write_report  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_results.json"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


@pytest.fixture
def results() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["synthetic"] is True
    assert payload["label"] == "synthetic"
    return payload


def test_reward_formula_majority_penalty_and_clamp():
    rubrics = [
        {"weight": 5, "votes": ["PASS", "PASS", "FAIL"]},
        {"weight": 5, "votes": ["PASS", "FAIL", "FAIL"]},
        {"weight": -3, "votes": ["PASS", "PASS", "FAIL"]},
    ]
    # Positive passes contribute 5. The second positive rubric fails the
    # strict majority. The penalty passes and subtracts 3. (5 - 3) / 10 = 0.2.
    assert reward_from_rubrics(rubrics, n_voters=3) == pytest.approx(0.2)
    assert rubric_passes(["PASS", "PASS", None], 3) is True
    assert rubric_passes(["PASS", None], 3) is False
    assert rubric_passes(["PASS", "FAIL"], 2) is False
    clamped = reward_from_rubrics(
        [
            {"weight": 1, "votes": ["PASS"]},
            {"weight": -5, "votes": ["PASS"]},
        ],
        n_voters=1,
    )
    assert clamped == 0.0


def test_gate_failure_and_missing_judge_are_not_zeros():
    gated = score_variant(
        {
            "gate_passed": False,
            "n_voters": 1,
            "rubrics": [{"weight": 1, "votes": ["PASS"]}],
        }
    )
    assert gated["status"] == "gate_failed"
    assert gated["reward"] is None
    missing = score_variant(
        {
            "gate_passed": True,
            "n_voters": 3,
            "rubrics": [{"weight": 1, "votes": ["PASS", "PASS"]}],
        }
    )
    assert missing["status"] == "missing_judge"
    assert missing["reward"] is None


def test_input_group_score_averages_variants_and_drops_failed_reps():
    both = score_record(
        {
            "variants": [
                {
                    "variant": "a",
                    "gate_passed": True,
                    "n_voters": 1,
                    "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                },
                {
                    "variant": "b",
                    "gate_passed": True,
                    "n_voters": 1,
                    "rubrics": [{"weight": 1, "votes": ["FAIL"]}],
                },
            ]
        }
    )
    assert both["status"] == "scored"
    assert both["score"] == pytest.approx(0.5)
    poisoned = score_record(
        {
            "variants": [
                {
                    "variant": "a",
                    "gate_passed": True,
                    "n_voters": 1,
                    "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                },
                {
                    "variant": "b",
                    "gate_passed": False,
                    "n_voters": 1,
                    "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                },
            ]
        }
    )
    assert poisoned["score"] is None
    assert poisoned["status"] == "gate_failed"

    summary = summarize(
        {
            "models": ["m"],
            "input_groups": ["g"],
            "repetitions": 2,
            "records": [
                {
                    "model": "m",
                    "condition": "STOCK",
                    "input_group": "g",
                    "repetition": 0,
                    "variants": [
                        {
                            "variant": "v",
                            "gate_passed": False,
                            "n_voters": 1,
                            "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                        }
                    ],
                },
                {
                    "model": "m",
                    "condition": "STOCK",
                    "input_group": "g",
                    "repetition": 1,
                    "variants": [
                        {
                            "variant": "v",
                            "gate_passed": True,
                            "n_voters": 1,
                            "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                        }
                    ],
                },
                {
                    "model": "m",
                    "condition": "MATCHED_SOFTWARE_REPLACEMENT",
                    "input_group": "g",
                    "repetition": 0,
                    "variants": [
                        {
                            "variant": "v",
                            "gate_passed": True,
                            "n_voters": 1,
                            "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                        }
                    ],
                },
                {
                    "model": "m",
                    "condition": "MATCHED_SOFTWARE_REPLACEMENT",
                    "input_group": "g",
                    "repetition": 1,
                    "variants": [
                        {
                            "variant": "v",
                            "gate_passed": True,
                            "n_voters": 1,
                            "rubrics": [{"weight": 1, "votes": ["PASS"]}],
                        }
                    ],
                },
            ],
        }
    )
    stock = summary["by_model"]["m"]["conditions"]["STOCK"]["groups"]["g"]
    assert stock["score"] == pytest.approx(1.0)
    assert stock["n_scored_repetitions"] == 1
    assert summary["conditions"]["STOCK"]["pilot_mean"] == pytest.approx(1.0)
    assert summary["failures"]["gate_failures"]
    primary = summary["comparisons"][0]
    assert primary["role"] == "primary"
    assert primary["n_pairs"] == 1
    assert primary["mean_delta"] == pytest.approx(0.0)


def test_fixture_excludes_gate_failure_and_keeps_primary_first(results, tmp_path):
    summary = summarize(results)
    comparisons = summary["comparisons"]
    assert [item["role"] for item in comparisons] == [
        "primary",
        "secondary",
        "versus_task_only",
        "versus_task_only",
    ]
    assert comparisons[0]["name"] == "MATCHED_SOFTWARE_REPLACEMENT minus STOCK"
    assert comparisons[1]["name"] == "STOCK_PLUS_METAPHOR minus STOCK"
    assert comparisons[2]["name"] == "STOCK minus TASK_ONLY"
    assert comparisons[3]["name"] == "MATCHED_SOFTWARE_REPLACEMENT minus TASK_ONLY"
    assert comparisons[1]["mean_delta"] > comparisons[0]["mean_delta"]

    stock_groups = []
    for model, payload in summary["by_model"].items():
        for group, row in payload["conditions"]["STOCK"]["groups"].items():
            if row["score"] is not None:
                stock_groups.append(row["score"])
    assert len(stock_groups) == 3
    expected_stock = sum(stock_groups) / len(stock_groups)
    assert expected_stock == pytest.approx((0.5 + 0.4 + 0.4) / 3)
    assert summary["conditions"]["STOCK"]["pilot_mean"] == pytest.approx(expected_stock)
    zero_filled = (0.5 + 0.0 + 0.4 + 0.4) / 4
    passed_filled = (0.5 + 1.0 + 0.4 + 0.4) / 4
    assert abs(expected_stock - zero_filled) > 0.05
    assert abs(expected_stock - passed_filled) > 0.05
    failed = summary["by_model"]["model-alpha"]["conditions"]["STOCK"]["groups"]["g2"]
    assert failed["score"] is None
    assert failed["status"] == "gate_failed"
    missing = summary["by_model"]["model-beta"]["conditions"]["TASK_ONLY"]["groups"]["g1"]
    assert missing["score"] is None
    assert missing["status"] == "missing_judge"
    primary_missing = {(item["model"], item["input_group"]) for item in comparisons[0]["missing"]}
    assert ("model-alpha", "g2") in primary_missing
    assert comparisons[0]["n_missing"] == 1

    dest = write_report(results, tmp_path / "report.md")
    text = dest.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert "SYNTHETIC FIXTURE" in first
    assert "not a model result" in first
    assert "not an official reproduction" in text.lower()
    assert text.index("## Primary paired result") < text.index("## Secondary paired result")
    assert text.index("## Secondary paired result") < text.index("## Comparisons versus TASK_ONLY")
    assert text.index("MATCHED_SOFTWARE_REPLACEMENT minus STOCK") < text.index(
        "STOCK_PLUS_METAPHOR minus STOCK"
    )
    assert text.index("STOCK_PLUS_METAPHOR minus STOCK") < text.index("STOCK minus TASK_ONLY")
    assert text.index("STOCK minus TASK_ONLY") < text.index(
        "MATCHED_SOFTWARE_REPLACEMENT minus TASK_ONLY"
    )
    primary_block = text.split("## Primary paired result", 1)[1].split("## Secondary paired result", 1)[0]
    assert "MATCHED_SOFTWARE_REPLACEMENT minus STOCK" in primary_block
    assert "STOCK_PLUS_METAPHOR minus STOCK" not in primary_block
    secondary_window = text.lower().split("secondary paired result", 1)[1][:800]
    assert "not the main result" in secondary_window
    assert "is the main result" not in text.lower().replace("is not the main result", "")
    means = [float(line.split(": ", 1)[1]) for line in text.splitlines() if line.startswith("mean delta:")]
    assert means[0] < means[1]
    assert means[0] == pytest.approx(comparisons[0]["mean_delta"])
    assert means[1] == pytest.approx(comparisons[1]["mean_delta"])
    assert "statistically significant" not in text.lower()

    stock_line = text.split("pilot mean [STOCK]:", 1)[1].splitlines()[0].strip()
    assert float(stock_line) == pytest.approx(expected_stock)
    assert abs(float(stock_line) - zero_filled) > 0.05
    task_line = text.split("pilot mean [TASK_ONLY]:", 1)[1].splitlines()[0].strip()
    assert float(task_line) == pytest.approx((0.4 + 0.4 + 0.3) / 3)
    assert abs(float(task_line) - ((0.4 + 0.4 + 0.0 + 0.3) / 4)) > 0.05

    failures = text.split("## Failures, invalid documents, retries, missing judges", 1)[1].split("\n## ", 1)[0]
    assert "gate failure" in failures.lower()
    assert "model-alpha" in failures and "g2" in failures and "STOCK" in failures
    assert "missing judge" in failures.lower()
    assert "model-beta" in failures and "g1" in failures and "TASK_ONLY" in failures
    assert "excluded from the native mean" in failures.lower()
    assert "invalid documents: none" in failures.lower()
    assert "retry: model-alpha / g1 / STOCK" in failures

    for line in text.splitlines():
        if line.startswith("| model-alpha | g2 |"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            assert "gate_failed" in cells[3]
            assert cells[3] != "0.000000"
            break
    else:
        raise AssertionError("missing per-group row for the gate failure")

    assert "not the official 12-cell leaderboard mean" in text.lower()
    assert "Harness: terminus-2" in text
    assert "Seed: 7" in text
    assert "three designated spans" in text.lower()
    assert "Condition 2 sentence:" in text
    assert "Synthetic condition 2 sentence." in text
    assert "scenario-1 AgentCo grounding repeats two hygiene rules" in text
    assert "Harbor system prompt uncontrolled" in text
    assert "fewer words are not automatically better" in text.lower()
    assert "beside scored [STOCK]: n=3; mean tracked changes 3.000000" in text
    assert "estimated total_usd: 12.500000" in text
    assert "reported total_usd: unknown" in text
    assert "reported cost is not filled in from the estimate" in text.lower()
    assert "No human audit entries." in text
    lowered = text.lower()
    for phrase in (
        "semantic match is a judgment",
        "condition 2 adds text",
        "condition 4 retains residual coaching",
        "judge variability",
        "public data contamination",
        "six input groups",
        "shared harness",
        "internal mechanisms",
        "all legal work",
    ):
        assert phrase in lowered

    examples = text.split("## Examples", 1)[1]
    helped, rest = examples.split("### Hurt", 1)
    hurt, same = rest.split("### No discernible difference", 1)
    assert "model-alpha / g1" in helped
    assert "no scored pairs" not in helped
    assert "no scored pairs" in hurt
    assert "no scored pairs" in same
    assert "model-alpha / g2" not in examples
    assert "0.400000" not in examples
    assert "0.500000" not in examples
    assert "0.050000" in examples


def test_smoke_report_records_why_no_edit_cells_stay(tmp_path):
    payload = {
        "synthetic": False,
        "scope": "smoke",
        "models": ["m"],
        "input_groups": ["s2-t1-g01"],
        "harness": "terminus-2",
        "seed": 1,
        "repetitions": 1,
        "records": [],
        "usage": {"estimated": {"total_usd": None}, "reported": {"total_usd": None}},
        "human_audit": [],
    }
    text = write_report(payload, tmp_path / "report.md").read_text(encoding="utf-8")
    assert "Why six cells have no edits" in text
    assert "never call propose_edits.py" in text
    assert "The smoke was not rerun." in text
    plain = dict(payload)
    plain["scope"] = "pilot"
    pilot = write_report(plain, tmp_path / "pilot.md").read_text(encoding="utf-8")
    assert "Why six cells have no edits" not in pilot


def test_non_synthetic_report_has_no_banner(tmp_path):
    payload = {
        "synthetic": False,
        "models": ["m"],
        "input_groups": ["g"],
        "harness": "terminus-2",
        "seed": 1,
        "repetitions": 1,
        "records": [],
        "usage": {"estimated": {"total_usd": None}, "reported": {"total_usd": None}},
        "human_audit": [],
    }
    text = write_report(payload, tmp_path / "report.md").read_text(encoding="utf-8")
    assert "SYNTHETIC FIXTURE" not in text.splitlines()[0]
    assert text.splitlines()[0].startswith("# RedlineBench instruction experiment")
    examples = text.split("## Examples", 1)[1]
    assert examples.count("no scored pairs") >= 3


def _docx(path: Path, document_xml: str, comments_xml: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        if comments_xml is not None:
            archive.writestr("word/comments.xml", comments_xml)


def _document(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'
    )


def _comments(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{W}">{body}</w:comments>'
    )


def test_edit_diagnostics_docx_dict_pair_and_missing(tmp_path):
    document = _document(
        """
        <w:p>
          <w:ins w:author="Reviewing Counsel" w:id="1"><w:r><w:t>added</w:t></w:r></w:ins>
          <w:del w:author="Reviewing Counsel" w:id="2"><w:r><w:delText>old</w:delText></w:r></w:del>
          <w:ins w:author="Original Author" w:id="3"><w:r><w:t>prior</w:t></w:r></w:ins>
          <w:del w:author="Reviewing Counsel Extra" w:id="4"><w:r><w:delText>x</w:delText></w:r></w:del>
        </w:p>
        """
    )
    comments = _comments(
        """
        <w:comment w:author="Reviewing Counsel" w:id="1"><w:p><w:r><w:t>note</w:t></w:r></w:p></w:comment>
        <w:comment w:author="Someone Else" w:id="2"><w:p><w:r><w:t>no</w:t></w:r></w:p></w:comment>
        """
    )
    path = tmp_path / "after.docx"
    _docx(path, document, comments)
    got = edit_diagnostics(str(path))
    assert got["insertion_count"] == 1
    assert got["deletion_count"] == 2
    assert got["tracked_change_count"] == 3
    assert got["comment_count"] == 1
    assert got["lower_count_is_not_a_better_score"] is True
    assert "score" not in got

    assert edit_diagnostics(str(tmp_path / "absent.docx")) == {"error": "missing"}
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    assert edit_diagnostics(str(bad))["error"] == "unreadable"

    normalized = edit_diagnostics({"insertion_count": 4, "deletion_count": 1, "comment_count": 2})
    assert normalized["tracked_change_count"] == 5
    assert normalized["comment_count"] == 2
    assert normalized["lower_count_is_not_a_better_score"] is True
    partial = edit_diagnostics({"tracked_change_count": 3})
    assert partial["tracked_change_count"] == 3
    assert partial["insertion_count"] is None
    assert partial["comment_count"] is None

    before = tmp_path / "before.docx"
    _docx(
        before,
        _document(
            '<w:p><w:ins w:author="Reviewing Counsel" w:id="1"><w:r><w:t>a</w:t></w:r></w:ins></w:p>'
        ),
    )
    after = tmp_path / "grown.docx"
    _docx(
        after,
        _document(
            """
            <w:p>
              <w:ins w:author="Reviewing Counsel" w:id="1"><w:r><w:t>a</w:t></w:r></w:ins>
              <w:ins w:author="Reviewing Counsel" w:id="2"><w:r><w:t>b</w:t></w:r></w:ins>
              <w:del w:author="Reviewing Counsel" w:id="3"><w:r><w:delText>c</w:delText></w:r></w:del>
            </w:p>
            """
        ),
        _comments(
            '<w:comment w:author="Reviewing Counsel" w:id="1"><w:p><w:r><w:t>n</w:t></w:r></w:p></w:comment>'
        ),
    )
    delta = edit_diagnostics((str(before), str(after)))
    assert delta["new_insertion_count"] == 1
    assert delta["new_deletion_count"] == 1
    assert delta["new_tracked_change_count"] == 2
    assert delta["new_comment_count"] == 1
    assert delta["lower_count_is_not_a_better_score"] is True


def _blind_cases() -> list[dict]:
    return [
        {
            "id": "pair-1",
            "role": "primary",
            "model": "model-alpha",
            "input_group": "g1",
            "assignment": "Amend the notice clause in section 8.",
            "flags": ["successful"],
            "outputs": [
                {
                    "condition": "STOCK",
                    "text": "OUTPUT_RED_APPLE",
                    "score": 0.5,
                    "expected": "EXPECTED_SECRET",
                },
                {
                    "condition": "MATCHED_SOFTWARE_REPLACEMENT",
                    "text": "OUTPUT_BLUE_PEAR",
                    "score": 0.6,
                    "expected": "EXPECTED_SECRET",
                },
            ],
        },
        {
            "id": "pair-2",
            "model": "model-beta",
            "input_group": "g2",
            "assignment": "Delete the auto-renewal sentence.",
            "flags": ["judge_disagreement"],
            "outputs": [
                {"condition": "STOCK", "text": "OUTPUT_GREEN_FIG", "score": 0.2},
                {
                    "condition": "MATCHED_SOFTWARE_REPLACEMENT",
                    "text": "OUTPUT_YELLOW_PLUM",
                    "score": 0.9,
                    "expected": "EXPECTED_SECRET",
                },
            ],
        },
    ]


def _html_bundle(dest: Path) -> str:
    chunks = []
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_blind_packet_hides_labels_and_keeps_the_key_outside(tmp_path):
    dest = tmp_path / "packet"
    key = write_packet(_blind_cases(), dest, seed=123, audit_n=1)
    html = _html_bundle(dest)
    for banned in (
        "TASK_ONLY",
        "STOCK_PLUS_METAPHOR",
        "MATCHED_SOFTWARE_REPLACEMENT",
        "STOCK",
        "model-alpha",
        "model-beta",
        "EXPECTED_SECRET",
    ):
        assert banned not in html
    assert "OUTPUT_RED_APPLE" in html
    assert "OUTPUT_BLUE_PEAR" in html
    assert "Amend the notice clause in section 8." in html
    assert 'value="left"' in html
    assert 'value="right"' in html
    assert 'value="tie"' in html
    assert 'value="uncertain"' in html
    assert "Achieved required result" in html
    assert "Missed a material requirement" in html
    assert "Introduced a material defect" in html
    assert "Made unnecessary substantive changes" in html
    assert "<textarea" in html
    assert 'onsubmit="return false;"' in html
    assert "http://" not in html
    assert "https://" not in html
    assert "not an error-rate sample" in html
    assert "style may still identify a condition" in html
    assert "documents are wrapped, not paraphrased" in html
    assert list(dest.rglob("*.key.json")) == []

    key_path = dest.parent / f"{dest.name}.key.json"
    assert key_path.is_file()
    assert dest.resolve() not in key_path.resolve().parents
    written = json.loads(key_path.read_text(encoding="utf-8"))
    assert written == key
    assert "STOCK" in key_path.read_text(encoding="utf-8")
    assert "model-alpha" in key_path.read_text(encoding="utf-8")
    audit = [item for item in key["items"] if item["section"] == "audit"]
    flagged = [item for item in key["items"] if item["section"] == "flagged"]
    assert [item["case_id"] for item in audit] == ["pair-1"]
    assert [item["case_id"] for item in flagged] == ["pair-2"]
    primary = [item for item in key["items"] if item["section"] == "primary" and item["case_id"] == "pair-1"]
    assert primary
    sides = {primary[0]["left"]["condition"], primary[0]["right"]["condition"]}
    assert sides == {"STOCK", "MATCHED_SOFTWARE_REPLACEMENT"}

    seen = set()
    for seed in range(30):
        packet = write_packet(_blind_cases(), tmp_path / f"p{seed}", seed=seed, audit_n=1)
        row = next(
            item
            for item in packet["items"]
            if item["section"] == "primary" and item["case_id"] == "pair-1"
        )
        seen.add(row["left"]["condition"])
        leaked = _html_bundle(tmp_path / f"p{seed}")
        assert "model-alpha" not in leaked
        assert "STOCK" not in leaked
    assert seen == {"STOCK", "MATCHED_SOFTWARE_REPLACEMENT"}
