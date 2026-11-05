"""Condition transforms for the RedlineBench instruction experiment.

Span text and condition names are imported from ``framing_study.pins``.
That module is owned by worker-docs; this module does not redeclare them.
"""

from __future__ import annotations

import difflib

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

SEMANTIC_MATCH_NOTE = (
    "Semantic match between the original spans and the software replacements "
    "is a judgment."
)

_REQUIRED_LINES: tuple[tuple[str, str], ...] = (
    ("HYGIENE_HEADING", HYGIENE_HEADING),
    ("D1_ORIGINAL", D1_ORIGINAL),
    ("D2_ORIGINAL", D2_ORIGINAL),
    ("D3_ORIGINAL", D3_ORIGINAL),
    ("P1", P1),
    ("P2", P2),
    ("P3", P3),
    ("P4", P4),
)

_ORIGINAL_SPANS: tuple[tuple[str, str], ...] = (
    ("D1_ORIGINAL", D1_ORIGINAL),
    ("D2_ORIGINAL", D2_ORIGINAL),
    ("D3_ORIGINAL", D3_ORIGINAL),
)

_SOFTWARE_SPANS: tuple[tuple[str, str], ...] = (
    ("D1_SOFTWARE", D1_SOFTWARE),
    ("D2_SOFTWARE", D2_SOFTWARE),
    ("D3_SOFTWARE", D3_SOFTWARE),
)

_REPLACEMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("D1_ORIGINAL", D1_ORIGINAL, "D1_SOFTWARE", D1_SOFTWARE),
    ("D2_ORIGINAL", D2_ORIGINAL, "D2_SOFTWARE", D2_SOFTWARE),
    ("D3_ORIGINAL", D3_ORIGINAL, "D3_SOFTWARE", D3_SOFTWARE),
)

_PRESERVED_LINES: tuple[tuple[str, str], ...] = (
    ("HYGIENE_HEADING", HYGIENE_HEADING),
    ("P1", P1),
    ("P2", P2),
    ("P3", P3),
    ("P4", P4),
)


class TransformError(ValueError):
    """The text cannot be transformed for the requested condition."""


def transform(text: str, condition: str) -> str:
    """Return the instruction text under ``condition``.

    STOCK is unchanged. STOCK_PLUS_METAPHOR inserts the metaphor sentence
    as its own paragraph between the hygiene heading and D1. MATCHED
    replaces D1–D3. TASK_ONLY deletes those three lines. Any other
    condition, or a missing or duplicate span, raises TransformError.
    """

    _require_text(text)
    _require_known_condition(condition)
    _require_source_shape(text)

    if condition == "STOCK":
        result = text
    elif condition == "STOCK_PLUS_METAPHOR":
        result = _insert_metaphor(text)
    elif condition == "MATCHED_SOFTWARE_REPLACEMENT":
        result = _replace_designated_spans(text)
    elif condition == "TASK_ONLY":
        result = _delete_designated_spans(text)
    else:
        raise TransformError(f"unknown condition: {condition!r}")

    post = _presence_problems(result, condition)
    if post:
        raise TransformError(
            "transform failed closed after editing: " + "; ".join(post)
        )
    return result


def integrity_problems(original: str, condition: str, transformed: str) -> list[str]:
    """Return human-readable problems. An empty list means the pair is valid."""

    if not isinstance(original, str) or not isinstance(transformed, str):
        return ["original and transformed must be str"]
    if not isinstance(condition, str):
        return ["condition must be a str"]
    if condition not in CONDITIONS:
        return [f"unknown condition: {condition!r}"]

    problems: list[str] = []
    problems.extend(_presence_problems(transformed, condition))
    problems.extend(_diff_problems(original, condition, transformed))
    return problems


def length_report(original: str, transformed: str) -> dict[str, object]:
    """Character lengths of the three spans and the metaphor sentence.

    Deltas compare each software sentence with its original span, and
    ``text_delta`` compares the two documents. Semantic match is a judgment.
    """

    _require_text(original)
    _require_text(transformed)
    d1_delta = len(D1_SOFTWARE) - len(D1_ORIGINAL)
    d2_delta = len(D2_SOFTWARE) - len(D2_ORIGINAL)
    d3_delta = len(D3_SOFTWARE) - len(D3_ORIGINAL)
    return {
        "d1_original_chars": len(D1_ORIGINAL),
        "d1_software_chars": len(D1_SOFTWARE),
        "d1_delta": d1_delta,
        "d2_original_chars": len(D2_ORIGINAL),
        "d2_software_chars": len(D2_SOFTWARE),
        "d2_delta": d2_delta,
        "d3_original_chars": len(D3_ORIGINAL),
        "d3_software_chars": len(D3_SOFTWARE),
        "d3_delta": d3_delta,
        "metaphor_chars": len(METAPHOR_SENTENCE),
        "original_chars": len(original),
        "transformed_chars": len(transformed),
        "text_delta": len(transformed) - len(original),
        "note": SEMANTIC_MATCH_NOTE,
    }


def _require_text(text: str) -> None:
    if not isinstance(text, str):
        raise TransformError("text must be a str")


def _require_known_condition(condition: str) -> None:
    if not isinstance(condition, str):
        raise TransformError("condition must be a str")
    if condition not in CONDITIONS:
        raise TransformError(f"unknown condition: {condition!r}")


def _require_source_shape(text: str) -> None:
    for label, span in _REQUIRED_LINES:
        _require_once_line(text, span, label)
    _require_absent(text, METAPHOR_SENTENCE, "METAPHOR_SENTENCE")
    for label, span in _SOFTWARE_SPANS:
        _require_absent(text, span, label)


def _require_once_line(text: str, span: str, label: str) -> None:
    found = text.count(span)
    if found != 1:
        raise TransformError(f"{label} occurs {found} times; expected exactly once")
    idx = text.find(span)
    if idx > 0 and text[idx - 1] != "\n":
        raise TransformError(f"{label} is not a whole line")
    end = idx + len(span)
    if end != len(text) and not (
        text.startswith("\n", end) or text.startswith("\r\n", end)
    ):
        raise TransformError(f"{label} is not a whole line")


def _require_absent(text: str, span: str, label: str) -> None:
    found = text.count(span)
    if found != 0:
        raise TransformError(f"{label} occurs {found} times; expected it to be absent")


def _insert_metaphor(text: str) -> str:
    for newline in ("\r\n", "\n"):
        anchor = HYGIENE_HEADING + newline + newline + D1_ORIGINAL
        found = text.count(anchor)
        if found == 0:
            continue
        if found != 1:
            raise TransformError(
                "STOCK_PLUS_METAPHOR insertion point occurs "
                f"{found} times; expected exactly once"
            )
        inserted = (
            HYGIENE_HEADING
            + newline
            + newline
            + METAPHOR_SENTENCE
            + newline
            + newline
            + D1_ORIGINAL
        )
        return text.replace(anchor, inserted, 1)
    raise TransformError(
        "STOCK_PLUS_METAPHOR insertion point is missing: expected the hygiene "
        "heading, one blank line, then D1"
    )


def _replace_designated_spans(text: str) -> str:
    result = text
    for old_label, old, new_label, new in _REPLACEMENTS:
        found = result.count(old)
        if found != 1:
            raise TransformError(
                f"{old_label} occurs {found} times; expected exactly once"
            )
        if result.count(new) != 0:
            raise TransformError(f"{new_label} was already present")
        result = result.replace(old, new, 1)
    return result


def _delete_designated_spans(text: str) -> str:
    result = text
    for label, span in _ORIGINAL_SPANS:
        result = _delete_line(result, span, label)
    return result


def _delete_line(text: str, span: str, label: str) -> str:
    _require_once_line(text, span, label)
    idx = text.find(span)
    end = idx + len(span)
    if text.startswith("\r\n", end):
        end += 2
    elif text.startswith("\n", end):
        end += 1
    elif end != len(text):
        raise TransformError(f"{label} is not a whole line")
    return text[:idx] + text[end:]


def _presence_problems(text: str, condition: str) -> list[str]:
    problems: list[str] = []
    for label, span in _PRESERVED_LINES:
        found = text.count(span)
        if found != 1:
            problems.append(f"{label} occurs {found} times; expected exactly once")

    metaphor = text.count(METAPHOR_SENTENCE)
    if condition == "STOCK_PLUS_METAPHOR":
        if metaphor != 1:
            problems.append(
                f"METAPHOR_SENTENCE occurs {metaphor} times; expected exactly once"
            )
    elif metaphor != 0:
        problems.append(
            f"METAPHOR_SENTENCE occurs {metaphor} times; expected it only in "
            "STOCK_PLUS_METAPHOR"
        )

    for label, span in _SOFTWARE_SPANS:
        found = text.count(span)
        if condition == "MATCHED_SOFTWARE_REPLACEMENT":
            if found != 1:
                problems.append(f"{label} occurs {found} times; expected exactly once")
        elif found != 0:
            problems.append(
                f"{label} occurs {found} times; expected it only in "
                "MATCHED_SOFTWARE_REPLACEMENT"
            )

    keep_originals = condition in ("STOCK", "STOCK_PLUS_METAPHOR")
    for label, span in _ORIGINAL_SPANS:
        found = text.count(span)
        if keep_originals and found != 1:
            problems.append(f"{label} occurs {found} times; expected exactly once")
        if not keep_originals and found != 0:
            problems.append(
                f"{label} occurs {found} times; expected it to be absent after "
                f"{condition}"
            )
    return problems


def _diff_problems(original: str, condition: str, transformed: str) -> list[str]:
    if not _splitlines_roundtrip(original) or not _splitlines_roundtrip(transformed):
        return ["line diff cannot see a non-line difference in the documents"]

    original_lines = original.splitlines(keepends=True)
    transformed_lines = transformed.splitlines(keepends=True)
    opcodes = difflib.SequenceMatcher(
        a=original_lines,
        b=transformed_lines,
        autojunk=False,
    ).get_opcodes()

    if condition == "STOCK":
        return _stock_diff_problems(original, transformed, opcodes)
    if condition == "STOCK_PLUS_METAPHOR":
        return _stock_plus_diff_problems(
            original, transformed, original_lines, transformed_lines, opcodes
        )
    if condition == "MATCHED_SOFTWARE_REPLACEMENT":
        return _matched_diff_problems(original, transformed, original_lines, transformed_lines, opcodes)
    if condition == "TASK_ONLY":
        return _task_only_diff_problems(original_lines, transformed_lines, opcodes)
    return [f"unknown condition: {condition!r}"]


def _splitlines_roundtrip(text: str) -> bool:
    return "".join(text.splitlines(keepends=True)) == text


def _stock_diff_problems(
    original: str,
    transformed: str,
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[str]:
    problems: list[str] = []
    if transformed != original:
        problems.append("STOCK must be byte-identical to the original")
    for tag, i1, i2, _j1, _j2 in opcodes:
        if tag != "equal":
            problems.append(
                f"STOCK line diff has a {tag} at original lines [{i1}:{i2}]"
            )
    return problems


def _stock_plus_diff_problems(
    original: str,
    transformed: str,
    original_lines: list[str],
    transformed_lines: list[str],
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[str]:
    problems: list[str] = []
    stripped = _strip_metaphor_paragraph(transformed)
    if stripped != original:
        problems.append(
            "STOCK_PLUS diff may only add the metaphor sentence and the blank "
            "line that makes it a paragraph, immediately after the hygiene heading"
        )

    inserted: list[str] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if tag != "insert":
            problems.append(
                f"STOCK_PLUS line diff has a {tag} at original lines [{i1}:{i2}]"
            )
            continue
        inserted.extend(transformed_lines[j1:j2])
        if not _insert_sits_on_hygiene_boundary(original_lines, i1):
            problems.append(
                "STOCK_PLUS insertion is not on the blank line between the "
                "hygiene heading and D1"
            )

    if not _inserted_lines_are_metaphor_paragraph(inserted):
        problems.append(
            "STOCK_PLUS line diff may only add the metaphor sentence and one "
            "blank line"
        )
    return problems


def _strip_metaphor_paragraph(text: str) -> str | None:
    for newline in ("\r\n", "\n"):
        block = (
            HYGIENE_HEADING
            + newline
            + newline
            + METAPHOR_SENTENCE
            + newline
            + newline
            + D1_ORIGINAL
        )
        plain = HYGIENE_HEADING + newline + newline + D1_ORIGINAL
        if text.count(block) != 1:
            continue
        return text.replace(block, plain, 1)
    return None


def _insert_sits_on_hygiene_boundary(original_lines: list[str], index: int) -> bool:
    """True when the insert is the paragraph between the heading and D1.

    Identical blank lines let the line diff attach the new blank to either
    side of the metaphor sentence. Both alignments are the same paragraph.
    """

    if index < 1 or index >= len(original_lines):
        return False
    heading_before_blank = (
        index >= 2
        and _is_exact_line(original_lines[index - 2], HYGIENE_HEADING)
        and _is_blank_line(original_lines[index - 1])
        and _is_exact_line(original_lines[index], D1_ORIGINAL)
    )
    heading_then_insert = (
        _is_exact_line(original_lines[index - 1], HYGIENE_HEADING)
        and _is_blank_line(original_lines[index])
        and index + 1 < len(original_lines)
        and _is_exact_line(original_lines[index + 1], D1_ORIGINAL)
    )
    return heading_before_blank or heading_then_insert


def _inserted_lines_are_metaphor_paragraph(lines: list[str]) -> bool:
    if len(lines) != 2:
        return False
    for newline in ("\n", "\r\n"):
        metaphor_line = METAPHOR_SENTENCE + newline
        blank = newline
        if lines in ([metaphor_line, blank], [blank, metaphor_line]):
            return True
    return False


def _matched_diff_problems(
    original: str,
    transformed: str,
    original_lines: list[str],
    transformed_lines: list[str],
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[str]:
    problems: list[str] = []
    reverted = _revert_software_replacements(transformed)
    if reverted != original:
        problems.append(
            "MATCHED diff may only replace D1, D2, and D3 with the software sentences"
        )

    expected = {
        _with_newline(D1_ORIGINAL, newline): _with_newline(D1_SOFTWARE, newline)
        for newline in ("", "\n", "\r\n")
    }
    expected.update(
        {
            _with_newline(D2_ORIGINAL, newline): _with_newline(D2_SOFTWARE, newline)
            for newline in ("", "\n", "\r\n")
        }
    )
    expected.update(
        {
            _with_newline(D3_ORIGINAL, newline): _with_newline(D3_SOFTWARE, newline)
            for newline in ("", "\n", "\r\n")
        }
    )
    seen: list[str] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if tag != "replace" or i2 != i1 + 1 or j2 != j1 + 1:
            problems.append(
                "MATCHED line diff may only replace the three designated lines"
            )
            continue
        old = original_lines[i1]
        new = transformed_lines[j1]
        if expected.get(old) != new:
            problems.append(
                "MATCHED line diff replaced a line that is not one designated span"
            )
            continue
        seen.append(_line_body(old))
    if sorted(seen) != sorted((D1_ORIGINAL, D2_ORIGINAL, D3_ORIGINAL)):
        problems.append(
            "MATCHED line diff must replace each of D1, D2, and D3 exactly once"
        )
    return problems


def _revert_software_replacements(text: str) -> str | None:
    result = text
    for _label, software, original in (
        ("D1", D1_SOFTWARE, D1_ORIGINAL),
        ("D2", D2_SOFTWARE, D2_ORIGINAL),
        ("D3", D3_SOFTWARE, D3_ORIGINAL),
    ):
        if result.count(software) != 1:
            return None
        result = result.replace(software, original, 1)
    return result


def _task_only_diff_problems(
    original_lines: list[str],
    transformed_lines: list[str],
    opcodes: list[tuple[str, int, int, int, int]],
) -> list[str]:
    problems: list[str] = []
    deleted: list[str] = []
    for tag, i1, i2, _j1, _j2 in opcodes:
        if tag == "equal":
            continue
        if tag != "delete":
            problems.append("TASK_ONLY line diff may only delete the three designated lines")
            continue
        for line in original_lines[i1:i2]:
            if not any(_is_exact_line(line, span) for _label, span in _ORIGINAL_SPANS):
                problems.append(
                    "TASK_ONLY line diff deleted a line that is not D1, D2, or D3"
                )
                continue
            deleted.append(_line_body(line))
    if sorted(deleted) != sorted((D1_ORIGINAL, D2_ORIGINAL, D3_ORIGINAL)):
        problems.append("TASK_ONLY line diff must delete each of D1, D2, and D3 exactly once")

    kept = [
        line
        for line in original_lines
        if _line_body(line) not in {D1_ORIGINAL, D2_ORIGINAL, D3_ORIGINAL}
    ]
    if kept != transformed_lines:
        problems.append(
            "TASK_ONLY diff may only delete the three designated spans"
        )
    return problems


def _with_newline(span: str, newline: str) -> str:
    return span + newline


def _line_body(line: str) -> str:
    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line


def _is_exact_line(line: str, span: str) -> bool:
    return _line_body(line) == span


def _is_blank_line(line: str) -> bool:
    return line in ("\n", "\r\n")
