"""One real gateway runtime for the visual demo: its own data dir, a lock, and an upstream stand-in.

Tool calls go through the gateway's own MCP tool registry (gw.mcp.call_tool), so the arguments
are validated and the tool functions run exactly as they would for an MCP client.
"""
import asyncio
import threading
from pathlib import Path

from clearance import gateway as gw
from clearance import policy

from .cast import MODEL
from .snapshot import snapshot
from .upstream import DemoUpstream

TAMPER_COPY = "audit_tampered_copy.jsonl"
OWNED_FILES = ("state.json", "audit.jsonl", TAMPER_COPY)  # the only files reset() deletes
GATED_TOOLS = ("bio_search", "bio_get", "design_stub", "export_design")


def _verdict(text: str, events: list[dict]) -> str:
    """allowed / denied for gated tools (from the audit entry the gateway wrote), else refused / ok."""
    gated = [e for e in events if e["event"] == "tool_call"]
    if gated:
        return "allowed" if gated[-1]["data"]["allowed"] else "denied"
    if text.startswith("DENIED"):
        return "denied"
    return "refused" if text.startswith(("REFUSED", "Unknown role")) else "ok"


class Session:
    def __init__(self, data_dir: Path, biomcp_cmd: str, live: bool = True) -> None:
        self.data_dir = Path(data_dir)
        self.biomcp_cmd = biomcp_cmd
        self.live = live
        self.lock = threading.RLock()
        self.reset()

    def reset(self, path: str = "replicating") -> None:
        """Start again from Phase 0 on the given path."""
        if path not in policy.PATH_ORDER:
            raise ValueError(f"path must be one of {', '.join(policy.PATH_ORDER)}")
        with self.lock:
            for name in OWNED_FILES:
                (self.data_dir / name).unlink(missing_ok=True)
            self.rt = gw.configure(self.data_dir, MODEL, path, self.biomcp_cmd)
            self.upstream = DemoUpstream(self.rt.proxy if self.live else None)
            self.rt.proxy = self.upstream

    def tools(self) -> list[dict]:
        """The gateway's real MCP tool list."""
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in asyncio.run(gw.mcp.list_tools())]

    def state(self) -> dict:
        with self.lock:
            return snapshot(self.rt, self.upstream)

    def _rule(self, tool: str, args: dict) -> str | None:
        """The policy rule text for a gated call by the current identity (policy.decide is pure)."""
        who = self.rt.who
        if tool not in GATED_TOOLS or not who:
            return None
        entity = args.get("entity") if tool.startswith("bio_") else None
        return policy.decide(self.rt.state.phase, who["role"], tool, entity, bool(who.get("bio_id"))).reason

    def call(self, tool: str, args: dict, fast: bool = False) -> dict:
        """Call one gateway tool and report what the gateway did (verdict, rule, signals, audit events)."""
        with self.lock:
            gw.rt = self.rt
            state = self.rt.state
            phase, signals, seen = state.phase, dict(state.signals), len(self.rt.audit.entries())
            rule = self._rule(tool, args)
            self.upstream.fast, self.upstream.last = fast, None
            try:
                result = asyncio.run(gw.mcp.call_tool(tool, args))
            except Exception as exc:  # unknown tool, or arguments that fail the tool's MCP schema
                raise ValueError(str(exc)) from exc
            text = "".join(getattr(part, "text", "") for part in result.content)
            events = self.rt.audit.entries()[seen:]
            return {
                "tool": tool, "args": args, "text": text,
                "verdict": _verdict(text, events), "rule": rule,
                "identity": dict(self.rt.who) or None,
                "phase_before": phase, "phase_after": state.phase,
                "signals_delta": {k: v - signals[k] for k, v in state.signals.items() if v > signals[k]},
                "upstream": self.upstream.last,
                "events": events,
            }
