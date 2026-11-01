"""Student facts: proposed -> confirmed -> versioned snapshot.

Only facts the student has confirmed (or corrected) enter a snapshot, and only a
snapshot reaches the interviewer or the grader. Source text from documents is
untrusted data: it is sanitised before it is ever placed in a prompt.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .tracks import TrackSpec

CONFIRMED_STATES = ("confirmed", "corrected")
MAX_TEXT_LEN = 400

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str, max_len: int = MAX_TEXT_LEN) -> str:
    """Make untrusted text safe to embed inside a delimited data block.

    Angle brackets are replaced so text cannot close or open the tags that delimit
    data in the prompt. This does not make instructions inside the text harmless on
    its own; the prompt also tells the model the block is data. Both are needed.
    """
    s = unicodedata.normalize("NFKC", str(value))
    s = _CONTROL.sub(" ", s)
    s = s.replace("<", "‹").replace(">", "›")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {sanitize_text(str(k), 64): sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(v) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_text(str(value))


@dataclass(frozen=True)
class Fact:
    ref: str  # stable id, used as a document reference in feedback
    field: str  # e.g. "funding.funds"
    value: Any
    source_label: str  # e.g. "Synthetic I-20, page 1"
    source_snippet: str
    status: str  # proposed | confirmed | corrected | rejected


def build_snapshot(facts: list[Fact], version: int) -> dict[str, Any]:
    confirmed = [f for f in facts if f.status in CONFIRMED_STATES]
    return {
        "version": version,
        "facts": [
            {
                "ref": f.ref,
                "field": f.field,
                "value": sanitize_value(f.value),
                "source": sanitize_text(f.source_label, 120),
            }
            for f in confirmed
        ],
    }


def snapshot_refs(snapshot: dict[str, Any]) -> set[str]:
    return {f["ref"] for f in snapshot.get("facts", [])}


def facts_by_field(snapshot: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for f in snapshot.get("facts", []):
        out.setdefault(f["field"], []).append(f)
    return out


def missing_required(track: TrackSpec, snapshot: dict[str, Any]) -> list[str]:
    present = set(facts_by_field(snapshot))
    return [name for name in track.required_facts if name not in present]


def first_value(snapshot: dict[str, Any], field_name: str, default: Any = None) -> Any:
    items = facts_by_field(snapshot).get(field_name)
    return items[0]["value"] if items else default
