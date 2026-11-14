"""Scripted demo: drives the real Clearance Gateway MCP server over stdio, exactly as Claude would.

Run: .venv/bin/python demo.py          (fresh state each run, in ./demo_run)
Also the fallback if a live Claude session misbehaves in the demo room.
"""
import asyncio
import shutil
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).parent
RUN = HERE / "demo_run"
PAUSE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0


async def step(session: ClientSession, title: str, tool: str, **args) -> None:
    result = await session.call_tool(tool, args)
    text = "".join(getattr(p, "text", "") for p in result.content)
    print(f"\n>>> {title}\n    {tool}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
    print("    " + text[:600].replace("\n", "\n    "))
    await asyncio.sleep(PAUSE)


async def votes(session: ClientSession, role: str, decisions: list[str]) -> None:
    for i, d in enumerate(decisions):
        await step(session, f"Named sign-off {i + 1}/5", "cast_gate_vote",
                   evaluator_name=f"{role} evaluator {i + 1}", evaluator_role=role,
                   decision=d, rationale="pre-registered criteria reviewed")


async def main() -> None:
    shutil.rmtree(RUN, ignore_errors=True)
    params = StdioServerParameters(command=sys.executable, cwd=str(HERE),
                                   args=["-m", "clearance.gateway", "--model", "demo-model",
                                         "--path", "replicating", "--data-dir", str(RUN)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await step(s, "1. Phase 0: regulator opens certification", "whoami", name="Dr. Regulator", role="regulator")
            await step(s, "Votes before criteria are refused", "cast_gate_vote", evaluator_name="Early bird",
                       evaluator_role="regulator", decision="forward", rationale="eager")
            await step(s, "Pre-register Phase 0 criteria", "preregister_phase",
                       criteria="SRB results hold up on re-run; path confirmed as replicating",
                       baseline_per_user_week=0.002, rate_ratio=3.0)
            await votes(s, "regulator", ["forward", "forward", "forward", "forward", "hold"])

            await step(s, "2. Phase 1 (BSL-4): staff sign in", "whoami", name="BSL-4 Tech", role="bsl4_staff")
            await step(s, "Air-gapped: live BioMCP refused", "bio_search", entity="article", query="p53 tumor suppressor")
            await step(s, "Probing: same call again (counted as a signal)", "bio_search", entity="article", query="p53")
            await step(s, "Design capability is a logged stub", "design_stub", purpose="demo")

            await step(s, "3. Regulator registers Phase 1 criteria", "whoami", name="Dr. Regulator", role="regulator")
            await step(s, "Pre-register Phase 1", "preregister_phase",
                       criteria="Nothing produced would be unsafe at BSL-3; internet adds no untested capability",
                       baseline_per_user_week=0.002, rate_ratio=3.0)
            await votes(s, "bsl4_staff", ["forward", "forward", "forward", "hold", "back"])

            await step(s, "4. Phase 2 (BSL-3): internet tools unlock", "whoami", name="BSL-3 Scientist", role="bsl3_staff")
            await step(s, "Real BioMCP record through the gateway", "bio_get", entity="gene", id="TP53")
            await step(s, "Designs stay in the container", "export_design", design_id="D-0001")

            await step(s, "5. DSMB look with the pre-registered stopping rule", "whoami", name="Dr. Regulator", role="regulator")
            await step(s, "Pre-register Phase 2 stopping rule", "preregister_phase",
                       criteria="Logging and stop signal verified; no output needed BSL-3 handling",
                       baseline_per_user_week=0.002, rate_ratio=3.0)
            await step(s, "Look 1: normal traffic", "ingest_synthetic_traffic", user_weeks=1000, signals=1)
            await step(s, "Look 2: proxy signals spike", "ingest_synthetic_traffic", user_weeks=200, signals=8)

            await step(s, "6. Back in Phase 1: internet tools gone again", "whoami", name="BSL-3 Scientist", role="bsl3_staff")
            await step(s, "BSL-3 staff no longer cleared", "bio_get", entity="gene", id="TP53")
            await step(s, "7. Status and tamper-evident record", "clearance_status")
            await step(s, "Audit chain", "verify_audit")


if __name__ == "__main__":
    asyncio.run(main())
