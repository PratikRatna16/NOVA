
import os
import ast
import time
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

# ── STATE ────────────────────────────────────────────
class NovaState(TypedDict):
    topic: str
    blueprint: str
    code: str
    audit: str

# ── VALIDATION ───────────────────────────────────────
def validate_code(code: str) -> tuple[bool, str]:
    code = code.strip()
    if code.startswith("```"):
        code = code.split("\n", 1)[1]
    if code.endswith("```"):
        code = code.rsplit("\n", 1)[0]
    try:
        ast.parse(code)
        return True, code
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

# ── COMPLEXITY ───────────────────────────────────────
def estimate_complexity(topic: str) -> str:
    word_count = len(topic.split())
    complex_keywords = ["database", "auth", "api", "multi", "server", "sqlite", "encryption"]
    if word_count > 15 or any(k in topic.lower() for k in complex_keywords):
        return "complex"
    elif word_count > 8:
        return "medium"
    return "simple"

COMPLEXITY_BUDGET = {
    "simple": "Keep this under 100 lines. This is a small utility script.",
    "medium": "Keep this under 250 lines. Moderate complexity is expected.",
    "complex": "Use as many lines as genuinely needed for correctness, but avoid padding."
}

# ── LLMs ─────────────────────────────────────────────
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.environ.get("GEMINI_API_KEY")
)
groq_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY")
)

def get_openrouter_llm(model_id):
    return ChatOpenAI(
        model=model_id,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

CODER_MODELS = [
    "poolside/laguna-m.1:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

# ── HELPERS ───────────────────────────────────────────
def call_with_fallback(primary, fallback, messages):
    try:
        return primary.invoke(messages).content
    except Exception as e:
        print(f"⚠ Primary failed: {e} → switching to fallback")
        return fallback.invoke(messages).content

def call_coder(messages):
    for model_id in CODER_MODELS:
        try:
            print(f"🤖 Trying coder model: {model_id}")
            start = time.time()
            response = get_openrouter_llm(model_id).invoke(messages)
            elapsed = time.time() - start
            usage = response.response_metadata.get("token_usage", {})
            input_tokens = usage.get("prompt_tokens", "?")
            output_tokens = usage.get("completion_tokens", "?")
            print(f"✅ Model: {model_id}")
            print(f"⏱ Time: {elapsed:.2f}s")
            print(f"🪙 Tokens — Input: {input_tokens} | Output: {output_tokens}")
            return response.content
        except Exception as e:
            print(f"⚠ {model_id} failed: {e} → trying next")
    print("⚠ All OpenRouter models failed → falling back to Groq")
    return groq_llm.invoke(messages).content

def call_hf_reviewer(prompt):
    return groq_llm.invoke([HumanMessage(content=prompt)]).content

# ── NODES ─────────────────────────────────────────────
def researcher_node(state: NovaState) -> NovaState:
    print("\n🔬 [RESEARCHER] Building blueprint...")
    messages = [
        SystemMessage(content="You are a technical researcher. Output clean structured Markdown blueprints only."),
        HumanMessage(content=(
            f"Research the core requirements for: {state['topic']}. "
            "Produce a comprehensive Markdown technical specification."
        ))
    ]
    blueprint = call_with_fallback(groq_llm, get_openrouter_llm("google/gemma-4-31b-it:free"), messages)
    with open("system_blueprint.md", "w") as f:
        f.write(blueprint)
    print("✅ Blueprint written.")
    return {**state, "blueprint": blueprint}

def coder_node(state: NovaState) -> NovaState:
    print("\n💻 [CODER] Writing code...")
    complexity = estimate_complexity(state['topic'])
    budget_instruction = COMPLEXITY_BUDGET[complexity]

    messages = [
       SystemMessage(content=f"""You are a senior Python engineer. Output rules:
           - Return ONLY raw Python code. No markdown, no explanation, no preamble.
           - Write a SINGLE Python file. Do NOT import from local modules (no "from api_client import X", no "from utils import Y"). Everything must be defined in this one file.
           - Only import standard library modules or well-known third-party packages (requests, argparse, etc).
           - {budget_instruction}
           - No empty functions, unused imports, or redundant abstractions.
           - Use modern Python idioms: comprehensions, walrus operator, ternary where readable.
           - Inline validation at point of use.
           - Map commands/routes via dict dispatch, not if/else chains.
           - Comments only where logic is non-obvious."""),
        HumanMessage(content=(
            f"Using this blueprint:\n\n{state['blueprint']}\n\n"
            "Write a fully functional Python script with robust error handling."
        ))
    ]
    code = call_coder(messages)
    print(f"DEBUG: code length = {len(code)} chars")
    return {**state, "code": code}

def debug_node(state: NovaState) -> NovaState:
    print("\n🔧 [DEBUGGER] Validating and fixing code...")
    is_valid, result = validate_code(state['code'])

    if is_valid:
        print("✅ Code is syntactically valid.")
        with open("system_monitor.py", "w") as f:
            f.write(result)
        return {**state, "code": result}

    print(f"⚠ Syntax error found: {result}")
    nex_llm = get_openrouter_llm("nex-agi/nex-n2-pro:free")
    messages = [
        SystemMessage(content="You are a debugging specialist. Fix the syntax error in this code. Return ONLY the corrected raw Python code, no markdown, no explanation."),
        HumanMessage(content=f"Code:\n{state['code']}\n\nError:\n{result}")
    ]
    try:
        fixed = nex_llm.invoke(messages).content
        still_valid, final_code = validate_code(fixed)
        if still_valid:
            print("✅ Fix successful, code is now valid.")
        else:
            print(f"⚠ Fix attempt still broken: {final_code}")
        with open("system_monitor.py", "w") as f:
            f.write(final_code)
        return {**state, "code": final_code}
    except Exception as e:
        print(f"⚠ Debug fix failed: {e}")
        return state

def reviewer_node(state: NovaState) -> NovaState:
    print("\n🔍 [REVIEWER] Auditing code...")
    prompt = (
        f"You are a principal QA architect. Review this Python script:\n\n{state['code']}\n\n"
        "Identify bugs, security issues, logic flaws. Write a structured Markdown audit log."
    )
    audit = call_hf_reviewer(prompt)
    with open("audit_log.md", "w") as f:
        f.write(audit)
    print("✅ Audit written.")
    return {**state, "audit": audit}

# ── GRAPH ─────────────────────────────────────────────
def build_graph():
    graph = StateGraph(NovaState)
    graph.add_node("researcher", researcher_node)
    graph.add_node("coder", coder_node)
    graph.add_node("debugger", debug_node)
    graph.add_node("reviewer", reviewer_node)
    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "coder")
    graph.add_edge("coder", "debugger")
    graph.add_edge("debugger", "reviewer")
    graph.add_edge("reviewer", END)
    return graph.compile()

# ── MAIN ──────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀 [NOVA ENGINE INITIALIZED — LangGraph Mode]")
    topic = input("📋 Enter your task: ").strip()
    if not topic:
        print("No task provided.")
    else:
        print(f"Starting pipeline for: {topic}")
        pipeline = build_graph()
        result = pipeline.invoke({"topic": topic, "blueprint": "", "code": "", "audit": ""})
        print("\n" + "="*60)
        print("✅ Pipeline completed.")
        print("📂 Created: system_blueprint.md, system_monitor.py, audit_log.md")
        print("="*60)
