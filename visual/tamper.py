"""Tamper demo: forge one entry in a COPY of the audit log, then re-verify with the real AuditLog.

Modes:
  edit     change the entry and leave its hash alone (breaks at that entry)
  rehash   also recompute that entry's hash (the next entry no longer links to it)
  rewrite  recompute every hash from there on (verifies, but the head hash has changed)
"""
import json
import shutil
from pathlib import Path

from clearance.audit import AuditLog, _digest

MODES = ("edit", "rehash", "rewrite")
_BODY = ("ts", "event", "data", "prev_hash")


def _forge(entry: dict) -> str:
    """Change one meaningful field in place and say what was changed."""
    event, data = entry["event"], entry["data"]
    if event == "vote":
        old, data["decision"] = data["decision"], "back" if data["decision"] == "forward" else "forward"
        return f"Vote by {data['name']} changed from {old} to {data['decision']}"
    if event == "tool_call":
        data["allowed"] = not data["allowed"]
        return f"{data['tool']} call relabelled as {'allowed' if data['allowed'] else 'denied'}"
    if event == "look":
        old, data["observed"], data["fired"] = data["observed"], 0, False
        return f"Look {data['look']} changed from {old} signals to 0"
    if event == "preregister":
        old, data["alpha"] = data["alpha"], 0.5
        return f"False-alarm budget changed from {old} to 0.5 after the fact"
    data["edited_later"] = True
    return f"{event} entry altered"


def _default_index(entries: list[dict]) -> int:
    """Prefer a hold vote (the classic forgery), then any vote, then the first entry."""
    votes = [i for i, e in enumerate(entries) if e["event"] == "vote"]
    holds = [i for i in votes if entries[i]["data"]["decision"] == "hold"]
    return (holds or votes or [0])[0]


def _rehash(entries: list[dict], start: int, stop: int) -> None:
    for i in range(start, stop):
        if i > start:
            entries[i]["prev_hash"] = entries[i - 1]["hash"]
        entries[i]["hash"] = _digest({k: entries[i][k] for k in _BODY})


def _status(i: int, index: int, ok: bool, broken_at: int | None) -> str:
    if i < index:
        return "ok"
    if not ok and i == broken_at:
        return "broken"
    if not ok and i > broken_at:
        return "untrusted"
    return "forged"


def tamper_copy(source: Path, copy: Path, index: int | None = None, mode: str = "edit") -> dict:
    """Forge one entry in a copy of `source`. The original file is never written to."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    shutil.copyfile(source, copy)
    entries = AuditLog(copy).entries()
    if not entries:
        raise ValueError("the audit log is empty: nothing to tamper with yet")
    index = _default_index(entries) if index is None else int(index)
    if not 0 <= index < len(entries):
        raise ValueError(f"entry index must be between 0 and {len(entries) - 1}")
    before = json.loads(json.dumps(entries[index]))
    description = _forge(entries[index])
    if mode != "edit":
        _rehash(entries, index, index + 1 if mode == "rehash" else len(entries))
    copy.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in entries))

    ok, broken_at = AuditLog(copy).verify()
    original = AuditLog(source)
    original_ok, _ = original.verify()
    original_head = original.entries()[-1]["hash"]
    return {
        "mode": mode, "index": index, "description": description,
        "before": before, "after": entries[index],
        "copy": {"ok": ok, "broken_at": broken_at, "count": len(entries), "head": entries[-1]["hash"]},
        "original": {"ok": original_ok, "head": original_head},
        "head_matches": entries[-1]["hash"] == original_head,
        "recomputed": None if ok else _digest({k: entries[broken_at][k] for k in _BODY}),
        "entries": [{**e, "status": _status(i, index, ok, broken_at)} for i, e in enumerate(entries)],
    }
