"""
NOVA Model Smoke Test
======================
One-time live check: does each model string in nova_models.py actually
respond right now? Not the deferred health-check system — no DB logging,
no periodic re-run, just a single pass/fail report before wiring into nodes.

Dedupes by (provider, model_id) so models shared across chains (Kimi K2.6,
GLM-5.1, Gemma 4, etc.) only get hit once, not once per chain.
"""

from langchain_core.messages import HumanMessage
from nova_models import (
    get_researcher_chain, get_cli_coder_chain, get_cli_debugger_chain,
    get_cli_reviewer_chain, get_web_structure_chain, get_web_style_chain,
    get_web_logic_chain, get_web_debugger_p1_chain, get_web_debugger_p2_chain,
    get_web_debugger_final_chain, get_web_reviewer_chain,
    get_web_assembler_conflict_chain,
)

ALL_CHAINS = {
    "researcher": get_researcher_chain(),
    "cli_coder": get_cli_coder_chain(),
    "cli_debugger": get_cli_debugger_chain(),
    "cli_reviewer": get_cli_reviewer_chain(),
    "web_structure": get_web_structure_chain(),
    "web_style": get_web_style_chain(),
    "web_logic": get_web_logic_chain(),
    "web_debugger_p1": get_web_debugger_p1_chain(),
    "web_debugger_p2": get_web_debugger_p2_chain(),
    "web_debugger_final": get_web_debugger_final_chain(),
    "web_reviewer": get_web_reviewer_chain(),
    "web_assembler_conflict": get_web_assembler_conflict_chain(),
}

seen = {}
for node, chain in ALL_CHAINS.items():
    for factory, model_id, label in chain:
        key = (factory.__name__, model_id)
        if key not in seen:
            seen[key] = [factory, label, [node]]
        else:
            seen[key][2].append(node)

total_calls = sum(len(c) for c in ALL_CHAINS.values())
print(f"Testing {len(seen)} unique endpoints (deduped from {total_calls} chain entries)...\n")

passed, failed = [], []

for (provider, model_id), (factory, label, used_in) in seen.items():
    try:
        llm = factory(model_id)
        llm.invoke([HumanMessage(content="Reply with exactly: OK")])
        print(f"PASS  [{provider:11s}] {label}")
        passed.append(label)
    except Exception as e:
        err = str(e)[:150]
        print(f"FAIL  [{provider:11s}] {label}  ->  {err}")
        failed.append((label, model_id, str(e), used_in))

print(f"\n{'='*60}\nPASS: {len(passed)}   FAIL: {len(failed)}")
if failed:
    print("\nFailures and which chains they affect:")
    for label, model_id, err, used_in in failed:
        print(f"\n  {label}  ({model_id})")
        print(f"    used in: {', '.join(used_in)}")
        print(f"    error: {err[:200]}")
