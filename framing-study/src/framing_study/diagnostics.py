"""Count tracked changes and comments attributed to Reviewing Counsel.

``edit_diagnostics`` accepts one docx path, a ``(before, after)`` pair of
paths, or an already-computed count dict. Docx counts come from ZIP XML:
``w:ins`` and ``w:del`` in ``word/document.xml``, and ``w:comment`` in
``word/comments.xml``, whose author startswith the prefix. A lower count is
not a better score.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

_COUNT_KEYS = (
    "insertion_count",
    "deletion_count",
    "tracked_change_count",
    "comment_count",
)


def edit_diagnostics(docx_path: str, author_prefix: str = "Reviewing Counsel") -> dict:
    """Count new tracked changes and comments for ``author_prefix``.

    A missing file returns ``{"error": "missing"}``. A path pair returns the
    after-minus-before counts for the same prefix. A dict is normalized and
    is not treated as a filename.
    """

    if isinstance(docx_path, dict):
        return normalize_count_dict(docx_path, author_prefix)
    if isinstance(docx_path, (list, tuple)):
        if len(docx_path) != 2:
            return {"error": "unreadable"}
        return new_edit_counts(docx_path[0], docx_path[1], author_prefix)
    return _count_docx(docx_path, author_prefix)


def new_edit_counts(before, after, author_prefix: str = "Reviewing Counsel") -> dict:
    """Return author-attributed counts in ``after`` minus the same counts in ``before``."""

    before_counts = _as_counts(before, author_prefix)
    after_counts = _as_counts(after, author_prefix)
    if "error" in before_counts or "error" in after_counts:
        return {
            "error": before_counts.get("error") or after_counts.get("error"),
            "before": before_counts,
            "after": after_counts,
        }
    delta = {}
    for key in _COUNT_KEYS:
        left = before_counts.get(key)
        right = after_counts.get(key)
        delta[key] = None if left is None or right is None else right - left
    return {
        "author_prefix": author_prefix,
        "insertion_count": delta["insertion_count"],
        "deletion_count": delta["deletion_count"],
        "tracked_change_count": delta["tracked_change_count"],
        "comment_count": delta["comment_count"],
        "new_insertion_count": delta["insertion_count"],
        "new_deletion_count": delta["deletion_count"],
        "new_tracked_change_count": delta["tracked_change_count"],
        "new_comment_count": delta["comment_count"],
        "before": before_counts,
        "after": after_counts,
        "lower_count_is_not_a_better_score": True,
        "source": "pair",
    }


def normalize_count_dict(counts: dict, author_prefix: str = "Reviewing Counsel") -> dict:
    """Normalize a precomputed count mapping. Absent keys stay unknown."""

    if not isinstance(counts, dict):
        return {"error": "unreadable"}
    if (
        "error" in counts
        and "tracked_change_count" not in counts
        and "insertion_count" not in counts
        and "comment_count" not in counts
    ):
        return dict(counts)

    insertion = _pick(counts, "insertion_count", "insertions", "new_insertion_count")
    deletion = _pick(counts, "deletion_count", "deletions", "new_deletion_count")
    tracked = _pick(counts, "tracked_change_count", "tracked_changes", "new_tracked_change_count")
    comments = _pick(counts, "comment_count", "comments", "new_comment_count")
    if tracked is None and insertion is not None and deletion is not None:
        tracked = insertion + deletion
    return {
        "author_prefix": counts.get("author_prefix", author_prefix),
        "insertion_count": insertion,
        "deletion_count": deletion,
        "tracked_change_count": tracked,
        "comment_count": comments,
        "lower_count_is_not_a_better_score": True,
        "source": counts.get("source", "count_dict"),
    }


def _pick(counts: dict, *keys: str) -> int | None:
    for key in keys:
        if key in counts and counts[key] is not None:
            return int(counts[key])
    return None


def _as_counts(source, author_prefix: str) -> dict:
    if isinstance(source, dict):
        return normalize_count_dict(source, author_prefix)
    if isinstance(source, (list, tuple)):
        return {"error": "unreadable"}
    return _count_docx(source, author_prefix)


def _count_docx(docx_path, author_prefix: str) -> dict:
    path = Path(docx_path)
    if not path.is_file():
        return {"error": "missing"}
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                document_blob = archive.read("word/document.xml")
            except KeyError:
                return {"error": "unreadable"}
            try:
                comments_blob = archive.read("word/comments.xml")
            except KeyError:
                comments_blob = None
    except (OSError, zipfile.BadZipFile):
        return {"error": "unreadable"}
    try:
        document_root = ElementTree.fromstring(document_blob)
    except ElementTree.ParseError:
        return {"error": "unreadable"}
    insertions, deletions = _count_revisions(document_root, author_prefix)
    comment_count = 0
    if comments_blob is not None:
        try:
            comments_root = ElementTree.fromstring(comments_blob)
        except ElementTree.ParseError:
            return {"error": "unreadable"}
        comment_count = _count_comments(comments_root, author_prefix)
    return {
        "author_prefix": author_prefix,
        "insertion_count": insertions,
        "deletion_count": deletions,
        "tracked_change_count": insertions + deletions,
        "comment_count": comment_count,
        "lower_count_is_not_a_better_score": True,
        "source": "docx",
    }


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _author_of(element) -> str:
    for key, value in element.attrib.items():
        if _local(key) == "author":
            return value or ""
    return ""


def _matches(author: str, prefix: str) -> bool:
    return author.startswith(prefix)


def _count_revisions(root, author_prefix: str) -> tuple[int, int]:
    insertions = 0
    deletions = 0
    for element in root.iter():
        local = _local(element.tag)
        if local not in {"ins", "del"}:
            continue
        if not _matches(_author_of(element), author_prefix):
            continue
        if local == "ins":
            insertions += 1
        else:
            deletions += 1
    return insertions, deletions


def _count_comments(root, author_prefix: str) -> int:
    count = 0
    for element in root.iter():
        if _local(element.tag) != "comment":
            continue
        if _matches(_author_of(element), author_prefix):
            count += 1
    return count
