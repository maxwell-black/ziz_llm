"""Static blinded review packet. No web server and no de-blinding key inside it."""

from __future__ import annotations

import hashlib
import html
import json
import random
from pathlib import Path

from framing_study.aggregate import MATCHED_SOFTWARE_REPLACEMENT, STOCK

_PRIMARY = {STOCK, MATCHED_SOFTWARE_REPLACEMENT}
_FLAG_REASONS = {"judge_disagreement", "conspicuous_failure"}
_BLINDING_LIMITS = (
    "Blinding limits: style may still identify a condition; documents are wrapped, not paraphrased."
)


def write_packet(
    cases: list,
    dest_dir: Path,
    seed: int,
    audit_n: int | None = None,
    key_path: Path | None = None,
) -> dict:
    """Write a blinded HTML packet and a reviewer form. Return the key mapping.

    The de-blinding key is written to ``key_path`` or, by default, to
    ``dest_dir.parent / (dest_dir.name + ".key.json")``, which is outside
    ``dest_dir``. Condition names, model names, scores, and expected outcomes
    are omitted from the HTML. Assignment and output text are copied verbatim.
    """

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    key_path = _outside_key_path(dest_dir, key_path)
    prepared = _prepare(list(cases), seed)
    if audit_n is None:
        audit_n = min(5, len(prepared)) if prepared else 0
    audit_n = max(0, min(int(audit_n), len(prepared)))
    audit = _audit_sample(prepared, audit_n, random.Random(seed + 1009))
    flagged = [item for item in prepared if item["flags"] & _FLAG_REASONS]
    primary = [item for item in prepared if item["is_primary"]]

    items: list[dict] = []
    parts = [_page_start()]
    parts.append("<h2>Blinded primary pairs</h2>")
    if primary:
        for index, item in enumerate(primary, start=1):
            packet_id = f"primary-{index:02d}"
            parts.append(_render_pair(packet_id, item))
            items.append(_key_item("primary", packet_id, item))
    else:
        parts.append("<p>No primary pairs.</p>")

    parts.append("<h2>Audit sample</h2>")
    if any("successful" in item["flags"] for item in audit):
        audit_note = "This sample includes items flagged successful."
    else:
        audit_note = "No items in this sample were flagged successful."
    parts.append(f"<p>Seeded audit sample of size {audit_n}. {audit_note}</p>")
    if audit:
        for index, item in enumerate(audit, start=1):
            packet_id = f"audit-{index:02d}"
            parts.append(_render_pair(packet_id, item))
            items.append(_key_item("audit", packet_id, item))
    else:
        parts.append("<p>No audit items.</p>")

    parts.append("<h2>Flagged items</h2>")
    parts.append(
        "<p>Items in this section were marked judge disagreement or conspicuous failure. "
        "This flagged section is not an error-rate sample.</p>"
    )
    if flagged:
        for index, item in enumerate(flagged, start=1):
            packet_id = f"flagged-{index:02d}"
            parts.append(_render_pair(packet_id, item))
            items.append(_key_item("flagged", packet_id, item))
    else:
        parts.append("<p>No items flagged judge disagreement or conspicuous failure.</p>")

    parts.append(_form_close())
    parts.append("</body></html>")
    html_text = "\n".join(parts)
    packet_html = dest_dir / "index.html"
    packet_html.write_text(html_text, encoding="utf-8")
    # The form is the same static page. A short pointer file keeps the form discoverable.
    (dest_dir / "response-form.html").write_text(html_text, encoding="utf-8")

    payload = {
        "seed": int(seed),
        "audit_n": audit_n,
        "dest_dir": str(dest_dir),
        "key_path": str(key_path),
        "packet_html": str(packet_html),
        "blinding_limits": _BLINDING_LIMITS,
        "items": items,
    }
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _outside_key_path(dest_dir: Path, key_path: Path | None) -> Path:
    default = dest_dir.parent / f"{dest_dir.name}.key.json"
    if key_path is None:
        return default
    candidate = Path(key_path)
    try:
        candidate.resolve().relative_to(dest_dir.resolve())
    except ValueError:
        return candidate
    return default


def _prepare(cases: list, seed: int) -> list[dict]:
    rng = random.Random(int(seed))
    prepared = []
    ordered = sorted(enumerate(cases), key=lambda pair: str(_case_id(pair[1], pair[0])))
    for index, case in ordered:
        outputs = _two_outputs(case)
        rng.shuffle(outputs)
        flags = set(_flags(case))
        prepared.append(
            {
                "case_id": _case_id(case, index),
                "model": _as_text(case.get("model") or case.get("model_id")),
                "input_group": _as_text(case.get("input_group") or case.get("group")),
                "assignment": _as_text(case.get("assignment") or case.get("assignment_text")),
                "flags": flags,
                "is_primary": _is_primary(case, outputs),
                "outputs": outputs,
            }
        )
    return prepared


def _audit_sample(prepared: list[dict], audit_n: int, rng: random.Random) -> list[dict]:
    successful = [item for item in prepared if "successful" in item["flags"]]
    others = [item for item in prepared if "successful" not in item["flags"]]
    rng.shuffle(successful)
    rng.shuffle(others)
    if len(successful) >= audit_n:
        return successful[:audit_n]
    return successful + others[: audit_n - len(successful)]


def _is_primary(case: dict, outputs: list[dict]) -> bool:
    if str(case.get("role") or "") == "primary":
        return True
    names = {item["condition"] for item in outputs}
    return _PRIMARY.issubset(names) or names == _PRIMARY


def _case_id(case: dict, index: int) -> str:
    if case.get("id") is not None:
        return str(case["id"])
    return f"case-{index + 1}"


def _flags(case: dict) -> list[str]:
    raw = case.get("flags") or []
    if isinstance(raw, dict):
        return [str(key) for key, value in raw.items() if value]
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw]


def _two_outputs(case: dict) -> list[dict]:
    outputs = _normalize_outputs(case)
    primary = [item for item in outputs if item["condition"] in _PRIMARY]
    chosen = primary if len(primary) >= 2 else outputs
    return [dict(item) for item in chosen[:2]]


def _normalize_outputs(case: dict) -> list[dict]:
    raw = case.get("outputs")
    items: list[dict] = []
    if isinstance(raw, dict):
        for condition, value in raw.items():
            items.append(_one_output(condition, value))
    elif isinstance(raw, list):
        for value in raw:
            if isinstance(value, dict):
                items.append(_one_output(value.get("condition") or value.get("label") or "", value))
            else:
                items.append(_one_output("", value))
    return items


def _one_output(condition: str, value) -> dict:
    if isinstance(value, dict):
        text = value.get("text", value.get("document", value.get("body", value.get("output", ""))))
        output_id = value.get("id") or value.get("output_id") or ""
        return {
            "condition": str(value.get("condition") or condition),
            "text": "" if text is None else str(text),
            "output_id": str(output_id),
        }
    return {"condition": str(condition), "text": "" if value is None else str(value), "output_id": ""}


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _key_item(section: str, packet_id: str, item: dict) -> dict:
    left = item["outputs"][0] if item["outputs"] else None
    right = item["outputs"][1] if len(item["outputs"]) > 1 else None
    return {
        "section": section,
        "packet_id": packet_id,
        "case_id": item["case_id"],
        "model": item["model"],
        "input_group": item["input_group"],
        "flags": sorted(item["flags"]),
        "left": _key_side("A", "left", left),
        "right": _key_side("B", "right", right),
    }


def _key_side(anon_id: str, position: str, output: dict | None) -> dict | None:
    if output is None:
        return None
    text = output["text"]
    return {
        "anon_id": anon_id,
        "position": position,
        "condition": output["condition"],
        "output_id": output["output_id"],
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
    }


def _page_start() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Blinded review packet</title>
<style>
body { font-family: Georgia, serif; margin: 2rem; line-height: 1.4; }
pre { white-space: pre-wrap; border: 1px solid #ccc; padding: 0.75rem; }
fieldset { margin: 0.75rem 0; }
.pair { border-top: 2px solid #333; margin-top: 2rem; padding-top: 1rem; }
textarea { width: 100%; min-height: 6rem; }
#response-json { min-height: 10rem; }
</style>
</head>
<body>
<h1>Blinded review packet</h1>
<p>Blinding limits: style may still identify a condition; documents are wrapped, not paraphrased.</p>
<p>Reviewer response form: this form does not submit anywhere. Responses stay in the textarea and can be copied or downloaded as JSON.</p>
<form id="review-form" onsubmit="return false;">
"""


def _render_pair(packet_id: str, item: dict) -> str:
    left = item["outputs"][0] if item["outputs"] else {"text": ""}
    right = item["outputs"][1] if len(item["outputs"]) > 1 else None
    chunks = [
        f'<section class="pair" data-pair="{html.escape(packet_id, quote=True)}">',
        f"<h3>Item {html.escape(packet_id)}</h3>",
        "<h4>Assignment</h4>",
        f"<pre>{html.escape(item['assignment'])}</pre>",
        _document_block(packet_id, "left", "Left (A)", left["text"]),
    ]
    if right is not None:
        chunks.append(_document_block(packet_id, "right", "Right (B)", right["text"]))
        chunks.append(_preference(packet_id))
    chunks.append(
        f'<label>Short explanation <textarea class="explanation" name="{html.escape(packet_id, quote=True)}-explanation"></textarea></label>'
    )
    chunks.append("</section>")
    return "\n".join(chunks)


def _document_block(packet_id: str, side: str, title: str, text: str) -> str:
    checks = [
        ("achieved_required_result", "Achieved required result"),
        ("missed_material_requirement", "Missed a material requirement"),
        ("introduced_material_defect", "Introduced a material defect"),
        ("unnecessary_substantive_changes", "Made unnecessary substantive changes"),
    ]
    labels = []
    for name, caption in checks:
        field = f"{packet_id}-{side}-{name}"
        labels.append(
            f'<label><input type="checkbox" name="{html.escape(field, quote=True)}"> {caption}</label>'
        )
    return "\n".join(
        [
            "<article>",
            f"<h4>{title}</h4>",
            f"<pre>{html.escape(text)}</pre>",
            f"<fieldset><legend>{title}</legend>",
            *labels,
            "</fieldset>",
            "</article>",
        ]
    )


def _preference(packet_id: str) -> str:
    options = (
        ("left", "Left"),
        ("right", "Right"),
        ("tie", "Tie"),
        ("uncertain", "Uncertain"),
    )
    rows = []
    for value, caption in options:
        rows.append(
            f'<label><input type="radio" name="{html.escape(packet_id, quote=True)}-preference" value="{value}"> {caption}</label>'
        )
    return "\n".join(["<fieldset><legend>Preference</legend>", *rows, "</fieldset>"])


def _form_close() -> str:
    return """
<h2>Response JSON</h2>
<p><button type="button" id="fill-json">Copy responses into the textarea</button>
<button type="button" id="download-json">Download JSON</button></p>
<textarea id="response-json" readonly>{"responses":[]}</textarea>
</form>
<script>
function collectResponses() {
  const responses = [];
  document.querySelectorAll("[data-pair]").forEach(function (section) {
    const id = section.getAttribute("data-pair");
    const checks = {};
    section.querySelectorAll("input[type=checkbox]").forEach(function (box) {
      checks[box.name] = box.checked;
    });
    const selected = section.querySelector("input[type=radio]:checked");
    const explanation = section.querySelector("textarea.explanation");
    responses.push({
      id: id,
      checks: checks,
      preference: selected ? selected.value : null,
      explanation: explanation ? explanation.value : ""
    });
  });
  return JSON.stringify({responses: responses}, null, 2);
}
document.getElementById("fill-json").addEventListener("click", function () {
  const payload = collectResponses();
  const box = document.getElementById("response-json");
  box.value = payload;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(payload);
  }
});
document.getElementById("download-json").addEventListener("click", function () {
  const payload = collectResponses();
  document.getElementById("response-json").value = payload;
  const blob = new Blob([payload], {type: "application/json"});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "review-responses.json";
  link.click();
});
</script>
"""
