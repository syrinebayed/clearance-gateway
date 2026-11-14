"""Upstream stand-in for the visual demo: forwards exactly one request to the real BioMCP.

The only biology this demo fetches or shows is the benign TP53 gene summary. Any other
cleared call gets a notice instead of being forwarded. If BioMCP cannot be reached in
time, the cached copy of that same summary is returned and labelled as cached.
"""
import asyncio
import time
from pathlib import Path

from clearance.redact import redact

FIXTURE = Path(__file__).parent / "fixtures" / "tp53_gene.txt"
TIMEOUT_S = 8.0
NOTICE = ("[visual demo] Cleared by the gateway. This demo forwards only one upstream request "
          "(get gene TP53), so nothing was fetched for this call.")
_TP53_ARGS = {"entity": "gene", "id": "TP53"}


def _is_tp53(tool: str, arguments: dict) -> bool:
    return (tool == "get" and arguments.get("entity") == "gene"
            and str(arguments.get("id", "")).upper() == "TP53")


class DemoUpstream:
    """Drop-in for Runtime.proxy: same `call` signature as BioMCPProxy."""

    def __init__(self, live, fixture: Path = FIXTURE, timeout: float = TIMEOUT_S) -> None:
        self.live = live                # the real BioMCPProxy, or None to stay offline
        self.cached = fixture.read_text()
        self.timeout = timeout
        self.fast = False               # True during story replays: no network, answer from memory
        self.reached = 0                # requests that got past the gateway
        self.last: dict | None = None   # how the most recent request was answered
        self._memo: str | None = None   # last live answer in this session

    async def call(self, tool: str, arguments: dict) -> tuple[str, bool]:
        """Answer one request the gateway has already cleared. Returns (text, is_error)."""
        self.reached += 1
        started = time.monotonic()
        if _is_tp53(tool, arguments):
            text, source = await self._tp53()
        else:
            text, source = NOTICE, "not_forwarded"
        self.last = {"source": source, "ms": round((time.monotonic() - started) * 1000),
                     "redacted": redact(text).n_redacted}
        return text, False

    async def _tp53(self) -> tuple[str, str]:
        if self.fast:
            return self._memo or self.cached, "replay"
        if self.live is None:
            return self.cached, "cache"
        try:
            async with asyncio.timeout(self.timeout):
                text, is_error = await self.live.call("get", dict(_TP53_ARGS))
        except Exception:  # offline, timed out, or BioMCP missing: fall back to the cached copy
            return self.cached, "cache"
        if is_error or "TP53" not in text:
            return self.cached, "cache"
        self._memo = text
        return text, "live"
