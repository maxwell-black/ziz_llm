"""Offline tests for the four instruction conditions.

worker-docs owns ``framing_study.pins``. This module imports that module and
skips only when the import is missing. It does not redeclare the pins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import framing_study.pins  # noqa: F401  # worker-docs owns this module
except ImportError as exc:
    pytest.skip(
        "worker-docs owns framing_study.pins; import unavailable: " + str(exc),
        allow_module_level=True,
    )

from framing_study.pins import (
    CONDITIONS,
    D1_ORIGINAL,
    D1_SOFTWARE,
    D2_ORIGINAL,
    D2_SOFTWARE,
    D3_ORIGINAL,
    D3_SOFTWARE,
    HYGIENE_HEADING,
    METAPHOR_SENTENCE,
    P1,
    P2,
    P3,
    P4,
)
from framing_study.transform import (
    TransformError,
    integrity_problems,
    length_report,
    transform,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hygiene_synthetic.md"
SUBSTANTIVE = (
    "Represented party: ExampleCo. Accept the liability cap already agreed."
)
PRESERVED = (P1, P2, P3, P4)
ORIGINALS = (D1_ORIGINAL, D2_ORIGINAL, D3_ORIGINAL)
SOFTWARE = (D1_SOFTWARE, D2_SOFTWARE, D3_SOFTWARE)


def _source() -> str:
    text = FIXTURE.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert "synthetic" in first.lower(), (
        "fixture hygiene_synthetic.md must be labeled synthetic"
    )
    return text


def test_fixture_is_labeled_synthetic() -> None:
    text = _source()
    assert text.splitlines()[0].startswith("<!-- synthetic"), (
        "fixture hygiene_synthetic.md must be labeled synthetic"
    )
    assert SUBSTANTIVE in text


def test_exact_character_lengths_and_d1_delta() -> None:
    d1_delta = len(D1_SOFTWARE) - len(D1_ORIGINAL)
    assert len(D2_SOFTWARE) == len(D2_ORIGINAL)
    assert len(D3_SOFTWARE) == len(D3_ORIGINAL)
    assert d1_delta == 2
    assert len(D1_ORIGINAL) == 75
    assert len(D1_SOFTWARE) == 77
    assert len(D2_ORIGINAL) == 152
    assert len(D2_SOFTWARE) == 152
    assert len(D3_ORIGINAL) == 119
    assert len(D3_SOFTWARE) == 119
    assert len(METAPHOR_SENTENCE) == 148

    source = _source()
    report = length_report(source, source)
    assert report["d1_original_chars"] == len(D1_ORIGINAL)
    assert report["d1_software_chars"] == len(D1_SOFTWARE)
    assert report["d1_delta"] == d1_delta
    assert report["d2_original_chars"] == len(D2_ORIGINAL)
    assert report["d2_software_chars"] == len(D2_SOFTWARE)
    assert report["d2_delta"] == 0
    assert report["d3_original_chars"] == len(D3_ORIGINAL)
    assert report["d3_software_chars"] == len(D3_SOFTWARE)
    assert report["d3_delta"] == 0
    assert report["metaphor_chars"] == len(METAPHOR_SENTENCE)
    assert report["text_delta"] == 0
    assert isinstance(report["note"], str)
    assert "judgment" in str(report["note"]).lower()


def test_conditions_and_stock_bytes_equal_the_fixture() -> None:
    source = _source()
    assert CONDITIONS == (
        "STOCK",
        "STOCK_PLUS_METAPHOR",
        "MATCHED_SOFTWARE_REPLACEMENT",
        "TASK_ONLY",
    )
    assert transform(source, "STOCK") == source
    assert transform(source, "STOCK") == transform(source, "STOCK")


def test_integrity_is_empty_for_all_four_and_transforms_are_deterministic() -> None:
    source = _source()
    d1_delta = len(D1_SOFTWARE) - len(D1_ORIGINAL)
    expected_deltas = {
        "STOCK": 0,
        "STOCK_PLUS_METAPHOR": len(METAPHOR_SENTENCE) + len("\n\n"),
        "MATCHED_SOFTWARE_REPLACEMENT": d1_delta,
        "TASK_ONLY": -(
            len(D1_ORIGINAL) + 1 + len(D2_ORIGINAL) + 1 + len(D3_ORIGINAL) + 1
        ),
    }
    for condition in CONDITIONS:
        first = transform(source, condition)
        second = transform(source, condition)
        assert first == second
        assert integrity_problems(source, condition, first) == []
        report = length_report(source, first)
        assert report["text_delta"] == expected_deltas[condition]
        assert report["text_delta"] == len(first) - len(source)
        assert SUBSTANTIVE in first


def test_stock_plus_inserts_one_paragraph_and_keeps_d1_through_d3() -> None:
    source = _source()
    out = transform(source, "STOCK_PLUS_METAPHOR")
    paragraph = (
        f"{HYGIENE_HEADING}\n\n{METAPHOR_SENTENCE}\n\n{D1_ORIGINAL}"
    )
    assert paragraph in out
    assert out.count(METAPHOR_SENTENCE) == 1
    for span in ORIGINALS:
        assert out.count(span) == 1
    for span in SOFTWARE:
        assert span not in out
    assert SUBSTANTIVE in out


def test_matched_replaces_spans_and_omits_the_metaphor() -> None:
    source = _source()
    out = transform(source, "MATCHED_SOFTWARE_REPLACEMENT")
    for span in ORIGINALS:
        assert span not in out
    for span in SOFTWARE:
        assert out.count(span) == 1
    assert METAPHOR_SENTENCE not in out
    assert HYGIENE_HEADING in out
    for span in PRESERVED:
        assert span in out
    assert SUBSTANTIVE in out


def test_task_only_deletes_designated_lines_and_keeps_the_substantive_line() -> None:
    source = _source()
    out = transform(source, "TASK_ONLY")
    for span in ORIGINALS:
        assert span not in out
    assert METAPHOR_SENTENCE not in out
    for span in SOFTWARE:
        assert span not in out
    assert HYGIENE_HEADING in out
    for span in PRESERVED:
        assert span in out
    assert SUBSTANTIVE in out


def test_mutated_source_raises_transform_error() -> None:
    source = _source()
    missing_d1 = source.replace(D1_ORIGINAL + "\n", "", 1)
    duplicated_d2 = source.replace(D2_ORIGINAL, D2_ORIGINAL + "\n" + D2_ORIGINAL, 1)
    no_blank_before_d1 = source.replace(
        f"{HYGIENE_HEADING}\n\n{D1_ORIGINAL}",
        f"{HYGIENE_HEADING}\n{D1_ORIGINAL}",
        1,
    )
    with pytest.raises(TransformError):
        transform(missing_d1, "STOCK")
    with pytest.raises(TransformError):
        transform(duplicated_d2, "MATCHED_SOFTWARE_REPLACEMENT")
    with pytest.raises(TransformError):
        transform(no_blank_before_d1, "STOCK_PLUS_METAPHOR")
    with pytest.raises(TransformError):
        transform(source, "NOT_A_CONDITION")


def test_integrity_rejects_a_tampered_transform() -> None:
    source = _source()
    plus = transform(source, "STOCK_PLUS_METAPHOR")
    tampered = plus.replace(METAPHOR_SENTENCE, METAPHOR_SENTENCE + " extra", 1)
    assert integrity_problems(source, "STOCK_PLUS_METAPHOR", tampered)
    assert integrity_problems(source, "NOT_A_CONDITION", source)
