"""Append-only, hash-chained audit log (JSON lines). Any edit to history breaks the chain."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event: str, **data: object) -> dict:
        """Write {ts, event, data, prev_hash, hash} and return the entry."""
        existing = self.entries()
        body = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "data": data,
            "prev_hash": existing[-1]["hash"] if existing else GENESIS,
        }
        entry = {**body, "hash": _digest(body)}
        with self.path.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def entries(self) -> list[dict]:
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) if intact, else (False, index of first broken entry)."""
        prev = GENESIS
        for i, entry in enumerate(self.entries()):
            body = {k: entry[k] for k in ("ts", "event", "data", "prev_hash")}
            if entry["prev_hash"] != prev or entry["hash"] != _digest(body):
                return False, i
            prev = entry["hash"]
        return True, None
