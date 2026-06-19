import os
import ast
import uuid
import time
import subprocess
import re
import sqlite3
from datetime import datetime
from nova_graph_memory import ExperienceGraph
graph_memory = ExperienceGraph()
from nova_projects import ProjectDNA
project_dna = ProjectDNA()
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

load_dotenv()

MAX_RETRIES = 2

# ── STATE ────────────────────────────────────────────
class NovaState(TypedDict):
    topic: str
    blueprint: str
    code: str
    audit: str
    retry_count: int
    last_error: str
    execution_valid: bool
    run_id: str

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

_run_meta = {"model_used": None, "time_taken": None, "output_tokens": None, "syntax_valid": None}

# ── LOGGING ──────────────────────────────────────────
def init_log_db():
    conn = sqlite3.connect("nova_runs.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            topic TEXT,
            model_used TEXT,
            time_taken REAL,
            output_tokens INTEGER,
            syntax_valid INTEGER,
            execution_valid INTEGER,
            retry_count INTEGER,
            run_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_run(topic, model_used, time_taken, output_tokens, syntax_valid, execution_valid, retry_count,run_id):
    conn = sqlite3.connect("nova_runs.db")
    conn.execute(
        "INSERT INTO runs (timestamp, topic, model_used, time_taken, output_tokens, syntax_valid, execution_valid, retry_count, run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), topic, model_used, time_taken, output_tokens, int(bool(syntax_valid)), int(bool(execution_valid)), retry_count, run_id)
    )
    conn.commit()
    conn.close()

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
            _run_meta["model_used"] = model_id
            _run_meta["time_taken"] = elapsed
            _run_meta["output_tokens"] = output_tokens
            return response.content
        except Exception as e:
            print(f"⚠ {model_id} failed: {e} → trying next")
    print("⚠ All OpenRouter models failed → falling back to Groq")
    _run_meta["model_used"] = "groq-fallback"
    return groq_llm.invoke(messages).content

def call_hf_reviewer(prompt):
    return groq_llm.invoke([HumanMessage(content=prompt)]).content

# ── NODES ─────────────────────────────────────────────
def researcher_node(state: NovaState) -> NovaState:
    print("\n🔬 [RESEARCHER] Building blueprint...")

    historical_context = graph_memory.recall_experience(state['topic'])
    
    # Add a custom guidance instruction if past context exists
    graph_guidance = ""
    if historical_context:
        graph_guidance = (
            f"\nTake note of this historical development experience from a similar project to optimize this design:\n"
            f"{historical_context}\n"
            f"Incorporate layout adjustments or fallbacks into your blueprint to prevent these errors.\n"
        )
    messages = [
        SystemMessage(content="You are a technical researcher. Output clean structured Markdown blueprints only."),
        HumanMessage(content=(
            f"Research the core requirements for: {state['topic']}. "
            f"{graph_guidance}"
            "Produce a comprehensive Markdown technical specification."
        ))
    ]
    blueprint = call_with_fallback(groq_llm, get_openrouter_llm("google/gemma-4-31b-it:free"), messages)
    os.makedirs("runs", exist_ok=True)
    with open(f"runs/{state['run_id']}_blueprint.md", "w") as f:
        f.write(blueprint)
    print("✅ Blueprint written.")
    return {**state, "blueprint": blueprint}

def coder_node(state: NovaState) -> NovaState:
    print("\n💻 [CODER] Writing code...")
    complexity = estimate_complexity(state['topic'])
    budget_instruction = COMPLEXITY_BUDGET[complexity]

    retry_count = state.get("retry_count", 0)
    last_error = state.get("last_error", "")

    historical_context = graph_memory.recall_experience(state['topic'])

    if retry_count > 0 and last_error:
        print(f"🔁 Retry attempt {retry_count} — fixing previous execution error.")
        human_content = (
            f"Using this blueprint:\n\n{state['blueprint']}\n\n"
            f"Here is the previous code attempt that FAILED to run:\n\n{state['code']}\n\n"
            f"It failed with this execution error:\n{last_error}\n\n"
            f"{historical_context}"
            "Fix the root cause and write a corrected, fully functional Python script with robust error handling."
        )
    else:
        human_content = (
            f"Using this blueprint:\n\n{state['blueprint']}\n\n"
            f"{historical_context}"
            "Write a fully functional Python script with robust error handling."
        )

    dna_context = project_dna.recall(state['topic'])
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
- Comments only where logic is non-obvious.
- Trace every optional flag mentally before finalizing: no flag combination should produce a silent no-op when the user expects output (e.g. depth=0 disabling all crawling, --dry-run deleting nothing silently.{dna_context}"""),
        HumanMessage(content=human_content)
    ]
    code = call_coder(messages)
    print(f"DEBUG: code length = {len(code)} chars")
    return {**state, "code": code}

def debug_node(state: NovaState) -> NovaState:
    print("\n🔧 [DEBUGGER] Validating and fixing code...")
    is_valid, result = validate_code(state['code'])

    if is_valid:
        print("✅ Code is syntactically valid.")
        _run_meta["syntax_valid"] = True
        with open(f"runs/{state['run_id']}_code.py",  "w") as f:
            f.write(result)
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
            _run_meta["syntax_valid"] = True

            try:
                graph_memory.remember_experience(
                    run_id=state['run_id'],
                    task_prompt=state['topic'],
                    error_text=str(result),
                    fix_text="Syntax Fix Applied: Code successfully validated after adjustments."
                )
            except Exception as ge:
                print(f"⚠️ Graph logging skipped: {ge}")
        else:
            print(f"⚠ Fix attempt still broken: {final_code}")
            _run_meta["syntax_valid"] = False
        with open(f"runs/{state['run_id']}_code.py", "w") as f:
            f.write(final_code)
        with open("system_monitor.py", "w") as f:
            f.write(final_code)
        return {**state, "code": final_code}
    except Exception as e:
        print(f"⚠ Debug fix failed: {e}")
        _run_meta["syntax_valid"] = False
        return state

def test_node(state: NovaState) -> NovaState:
    print("\n🧪 [TESTER] Running smoke test...")
    execution_valid = False
    error_text = ""
    for attempt in range(2):
        try:
            result = subprocess.run(
                [f"python", f"runs/{state['run_id']}_code.py",  "--help"],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0:
                print("✅ Smoke test passed — no import/runtime errors.")
                execution_valid = True
                error_text = ""
                break
            match = re.search(r"No module named '(\w+)'", result.stderr + result.stdout)
            if not match:
                match = re.search(r"pip install (\w+)", result.stderr + result.stdout)
            if match and attempt == 0:
                missing = match.group(1)
                print(f"📦 Missing dependency detected: {missing}. Installing...")
                install = subprocess.run(
                    ["pip", "install", "--break-system-packages", missing],
                    capture_output=True, text=True
                )
                if install.returncode == 0:
                    print(f"✅ Installed {missing}. Retrying smoke test...")
                    continue
                else:
                    print(f"⚠ Failed to install {missing}: {install.stderr[-300:]}")
                    error_text = install.stderr[-500:]
                    break
            else:
                print(f"⚠ Smoke test failed:\n{result.stderr[-500:]}")
                error_text = result.stderr[-500:]
                break
        except subprocess.TimeoutExpired:
            print("⚠ Smoke test timed out (script may not support --help).")
            error_text = "Smoke test timed out."
            break
        except Exception as e:
            print(f"⚠ Smoke test error: {e}")
            error_text = str(e)
            break
    try:
        if execution_valid:
            graph_memory.remember_experience(
                run_id=state['run_id'],
                task_prompt=state['topic'],
                error_text="",
                fix_text=f"Task completed successfully. Lines: {len(state.get('code','').splitlines())}. No runtime errors."
            )
        elif error_text:
            graph_memory.remember_experience(
                run_id=state['run_id'],
                task_prompt=state['topic'],
                error_text=error_text,
                fix_text=""
            )
    except Exception as ge:
        print(f"⚠️ Graph mapping log skipped: {ge}")

    retry_count = state.get("retry_count", 0)
    if not execution_valid:
        retry_count += 1

    log_run(
        topic=state['topic'],
        model_used=_run_meta["model_used"],
        time_taken=_run_meta["time_taken"],
        output_tokens=_run_meta["output_tokens"],
        syntax_valid=_run_meta["syntax_valid"],
        execution_valid=execution_valid,
        retry_count=retry_count,
        run_id=state['run_id']
    )
    return {**state, "execution_valid": execution_valid, "last_error": error_text, "retry_count": retry_count}

def route_after_test(state: NovaState) -> str:
    if state.get("execution_valid"):
        return "reviewer"
    if state.get("retry_count", 0) <= MAX_RETRIES:
        print(f"🔁 Execution failed — routing back to coder (attempt {state.get('retry_count', 0)}/{MAX_RETRIES}).")
        return "coder"
    print("⚠ Max retries reached. Sending current code to reviewer despite failure.")
    return "reviewer"

def reviewer_node(state: NovaState) -> NovaState:
    print("\n🔍 [REVIEWER] Auditing code...")
    prompt = (
        f"You are a principal QA architect. Review this Python script:\n\n{state['code']}\n\n"
        "Identify bugs, security issues, logic flaws. Write a structured Markdown audit log."
    )
    audit = call_hf_reviewer(prompt)
    with open(f"runs/{state['run_id']}_audit.md", "w") as f:
        f.write(audit)
    print("✅ Audit written.")
    files_created = f"runs/{state['run_id']}_blueprint.md, runs/{state['run_id']}_code.py, runs/{state['run_id']}_audit.md, system_monitor.py"
    outcome = f"{'PASS' if state.get('execution_valid') else 'FAIL'} after {state.get('retry_count', 0)} retries"

    graph_memory.remember_experience(
        run_id=state['run_id'],
        task_prompt=state['topic'],
        goal=state['topic'],
        files_created=files_created,
        deployment="Local CLI script — no deployment target",
        outcome=outcome
    )

    try:
        project_dna.store(
            project_id=state['run_id'],
            code=state['code'],
            audit=audit,
            topic=state['topic'],
            execution_valid=state.get('execution_valid', False),
            retry_count=state.get('retry_count', 0),
            time_taken=_run_meta.get('time_taken'),
            output_tokens=_run_meta.get('output_tokens')
        )
    except Exception as e:
        print(f"⚠ Project DNA storage skipped: {e}")
    return {**state, "audit": audit}

# ── GRAPH ─────────────────────────────────────────────
def build_graph():
    graph = StateGraph(NovaState)
    graph.add_node("researcher", researcher_node)
    graph.add_node("coder", coder_node)
    graph.add_node("debugger", debug_node)
    graph.add_node("tester", test_node)
    graph.add_node("reviewer", reviewer_node)
    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "coder")
    graph.add_edge("coder", "debugger")
    graph.add_edge("debugger", "tester")
    graph.add_conditional_edges(
        "tester",
        route_after_test,
        {"coder": "coder", "reviewer": "reviewer"}
    )
    graph.add_edge("reviewer", END)
    return graph.compile()

# ── MAIN ──────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀 [NOVA ENGINE INITIALIZED — LangGraph Mode]")
    init_log_db()
    topic = input("📋 Enter your task: ").strip()
    if not topic:
        print("No task provided.")
    else:
        print(f"Starting pipeline for: {topic}")
        pipeline = build_graph()
        run_id = str(uuid.uuid4())[:8]
        os.makedirs("runs", exist_ok=True)
        result = pipeline.invoke({
            "topic": topic, "blueprint": "", "code": "", "audit": "",
            "retry_count": 0, "last_error": "", "execution_valid": False,
            "run_id": run_id
        })
        print("\n" + "="*60)
        print("✅ Pipeline completed.")
        print(f"📂 Run ID: {run_id} | Files saved in runs/{run_id}_*.py/md")
        print("="*60)
