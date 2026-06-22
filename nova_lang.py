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
    model="gemini-3.5-flash",
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

def get_nvidia_llm(model_id):
    return ChatOpenAI(
        model=model_id,
        api_key=os.environ.get("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1"
    )

CODER_MODELS = [
    "poolside/laguna-m.1:free",
    "moonshotai/kimi-k2-6",
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
        print(f"⚠ Primary failed: {e} -> switching to fallback")
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
            print(f"🪙 Tokens - Input: {input_tokens} | Output: {output_tokens}")
            _run_meta["model_used"] = model_id
            _run_meta["time_taken"] = elapsed
            _run_meta["output_tokens"] = output_tokens
            return response.content
        except Exception as e:
            print(f"⚠ {model_id} failed: {e} -> trying next")
    try:
        print("🖥 Trying NVIDIA fallback: kimi-k2-6")
        response = get_nvidia_llm("moonshotai/kimi-k2-6").invoke(messages)
        _run_meta["model_used"] = "moonshotai/kimi-k2-6-nvidia"
        return response.content
    except Exception as e:
        print(f"⚠ NVIDIA fallback failed: {e} -> falling back to Groq")

    print("⚠ All models failed (OpenRouter + NVIDIA) -> falling back to Groq")
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
        SystemMessage(content=(
            "You are a technical researcher. Output clean structured Markdown blueprints.\n\n"
            "When designing CLI tools, enforce these rules:\n\n"
            "INPUT & ARGUMENTS:\n"
            "- ALWAYS use variable positional arguments (nargs=+) for terms that can be multiple.\n"
            "- ALWAYS favor standard CLI arguments first. JSON/YAML config files are optional only.\n"
            "- ALL time/scheduling utilities must accept variable overrides via CLI (-duration, -minutes).\n"
            "- Accept flexible positional fallbacks for core primitives (e.g. python script.py 30 should infer 30 seconds without requiring explicit -duration flag).\n"
            "- File format tools must infer format from file extensions automatically.\n"
            "- For tools with distinct opposing actions (compress/decompress, encrypt/decrypt), ALWAYS use argparse subcommands not boolean flags mixed with positionals.\n"
            "- If boolean action flags are used, they MUST be in a mutually exclusive group (add_mutually_exclusive_group(required=True)).\n\n"
            "FILE HANDLING:\n"
            "- ALWAYS append to existing JSON array structure. NEVER overwrite with w mode directly.\n\n"
            "LIMIT/FLAG LOGIC:\n"
            "- Any -l or --limit flag must have strict validation. Validate range BEFORE slicing.\n\n"
            "SEARCH & AMBIGUITY:\n"
            "- ALWAYS build two distinct paths - Direct Title Lookup first, fallback to Keyword Search.\n\n"
            "STREAM PROCESSING:\n"
            "- Each line must be evaluated ONCE only. Mark it consumed after first match.\n"
            "- Throttling counters must be isolated per-line.\n\n"
            "FEATURE COMPLETENESS:\n"
            "- Parse the users topic for EVERY explicit analytical feature requested. Each must have console output.\n"
            "- Security tools must display length, charset size, entropy bits, strength score.\n"
            "- Metric/telemetry labels must change semantically based on operation direction. Never reuse compression labels for decompression output.\n\n"
            "SMART DEFAULTS & INFERENCE:\n"
            "- Infer file format from extensions automatically. Never require explicit flags for known extensions.\n"
            "- Never throw validation errors for missing type declarations when standard extensions are provided.\n\n"
            "NETWORK & API TOOLS:\n"
            "- ALWAYS validate required credentials locally BEFORE making any network request. Abort immediately if missing.\n"
            "- ALWAYS support environment variable fallbacks for API keys alongside explicit CLI flags.\n"
            "- ALWAYS include explicit user-friendly error handling for HTTP status codes (401, 404, 500).\n\n"
            "ARGUMENT MAPPING:\n"
            "- For structured config file generation, strictly separate the friendly label/alias from the physical address/IP. Never map the same value to both.\n"
            "- Trace every CLI argument variable destination explicitly. Identity and routing must always be distinct parameters.\n\n"
            "REGEX & PATTERN MATCHING:\n"
            "- ALWAYS use native Python re.sub() for regex substitutions. Never fall back to string slice substitution.\n"
            "- Regex tools must correctly handle capture group backreferences (\\1, \\g<1>) dynamically.\n\n"
            "COMMAND INTERFACE COMPLIANCE:\n"
            "- ALWAYS implement every explicit subcommand requested in the user prompt. Never drop or swap a requested command for a utility variation.\n"
            "- Cross-reference final argparse choices against user requirements before finalizing blueprint.\n\n"
            "PATTERN MATCHING INTEGRITY:\n"
            "- Pattern matching and regex tools must evaluate against the COMPLETE target string (e.g. full filename including extension). Never strip extensions or paths before matching unless explicitly instructed.\n"
            "- If structural splitting is needed for filesystem safety, handle it internally after matching, not before.\n\n"
            "STATEFUL & BACKGROUND TOOLS:\n"
            "- Background operations MUST print real-time diagnostic lines to stdout during execution. Use \\r line-clearing updates or progress bars for long-running processes, never silent execution.\n"
            "- Any tool persisting state to SQLite or JSON MUST provide a --view, --report, or stats subcommand.\n"
            "- Never make periodic tracking flags globally required if they block standalone admin commands.\n"
            "- For background daemons or timers, use proper Linux process detachment: double-fork, TTY decoupling, or write worker PID to a lockfile (~/.config/ or /tmp/) so separate CLI invocations can track and signal the active process. Always expose PID on screen and provide a --kill flag to terminate the daemon safely.\n\n"
            "AUDIO & SIGNALS:\n"
            "- For countdown alarms or event alerts, use native terminal bell (print(chr(7))) as primary signal.\n"
            "- Always wrap external audio library imports in try/except to prevent runtime crashes if library is missing.\n\n"
            "BOUNDARY CONDITIONS:\n"
            "- All numeric inputs must be validated against realistic min/max before use."
        )),
        HumanMessage(content=(
            f"Research the core requirements for: {state['topic']}. "
            f"{graph_guidance}"
            "Produce a comprehensive Markdown technical specification."
        ))
    ]
    blueprint = call_with_fallback(groq_llm, get_openrouter_llm("nvidia/nemotron-3-ultra-550b-a55b:free"), messages)
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
        print(f"🔁 Retry attempt {retry_count} - fixing previous execution error.")
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
    coder_system_prompt = (
        "You are a senior Python engineer. Output rules:\n"
        "- Return ONLY raw Python code. No markdown, no explanation, no preamble.\n"
        "- Write a SINGLE Python file. Everything must be defined in this one file.\n"
        "- Only import standard library or well-known third-party packages.\n"
        f"- {budget_instruction}\n"
        "- No empty functions, unused imports, or redundant abstractions.\n"
        "- Use modern Python idioms: comprehensions, walrus operator, ternary where readable.\n"
        "- Map commands/routes via dict dispatch, not if/else chains.\n"
        "- Comments only where logic is non-obvious.\n"
        "- When working with SQLite, always parse date strings explicitly before Python comparison.\n"
        "- Trace every optional flag mentally before finalizing.\n"
        f"{dna_context}"
    )
    messages = [
        SystemMessage(content=coder_system_prompt),
        HumanMessage(content=human_content)
    ]
    code = call_coder(messages)
    print(f"DEBUG: code length = {len(code)} chars")
    return {**state, "code": code}

def debug_node(state: NovaState) -> NovaState:
    print("\n🔧 [DEBUGGER] Validating and fixing code...")
    print(f"🔧 Debugger model: {gemini_llm.model}")
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
    nex_llm = gemini_llm
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
                print("✅ Smoke test passed - no import/runtime errors.")
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
        print(f"🔁 Execution failed - routing back to coder (attempt {state.get('retry_count', 0)}/{MAX_RETRIES}).")
        return "coder"
    print("⚠ Max retries reached. Sending current code to reviewer despite failure.")
    return "reviewer"

def reviewer_node(state: NovaState) -> NovaState:
    print("\n🔍 [REVIEWER] Auditing code...")
    prompt = (
        f"You are a principal QA architect. Review this Python script:\n\n{state['code']}\n\n"
        "Identify bugs, security issues, logic flaws. Write a structured Markdown audit log.\n\n"
        "Mandatory checks:\n"
        "1. CLI args: Does it handle multiple inputs via nargs='+'? Flag if single positional only.\n"
        "2. CLI simplicity: Does it use standard CLI args first? Flag if config file is mandatory.\n"
        "3. Positional fallbacks: For core primitives like duration, does it accept plain positional input without requiring explicit flags?\n"
        "4. File handling: Does it append to JSON array safely? Flag any direct w mode overwrites.\n"
        "5. Limit logic: Is the --limit flag validated strictly before use? Test edge cases (0, 1, max+1).\n"
        "6. Search ambiguity: Is there a clear separation between Direct Title Lookup and Keyword Search?\n"
        "7. Stream processing: Does each log line get evaluated ONCE only? Flag duplicate pattern checks.\n"
        "8. State isolation: Are throttling counters isolated per-line?\n"
        "9. Feature verification: Cross-check every explicit keyword in topic against code. Flag missing analytical output.\n"
        "10. UX transparency: For security tools, does output show length, charset size, entropy bits, strength score?\n"
        "11. Hardcoding check: For time/scheduling tools, are durations overridable via CLI flags?\n"
        "12. Smart inference: For file format tools, does it infer format from extensions automatically?\n"
        "13. Subcommand enforcement: For tools with distinct opposing actions, are argparse subcommands used? If boolean flags used, are they in a mutually exclusive group?\n"
        "14. Telemetry labels: Do metric labels change based on operation direction? Flag if compression labels reused for decompression.\n"
        "15. Pre-flight validation: For network/API tools, are credentials validated locally BEFORE any HTTP request?\n"
        "16. Environment fallbacks: Does the tool check environment variables for API keys alongside CLI flags?\n"
        "17. HTTP error handling: Are status codes (401, 404, 500) caught and shown as user-friendly messages?\n"
        "18. Argument mapping: For structured config generation, is friendly alias strictly separated from physical address?\n"
        "19. Regex handling: Does the tool use re.sub() correctly with backreference support? Flag any string slice fallback.\n"
        "20. Background feedback: Do background operations print real-time status lines to stdout? Flag silent execution.\n"
        "21. Admin interface: For stateful tools, is there a --view, --report, or stats subcommand?\n"
        "22. Flag gridlock: Do admin/view commands work independently without requiring tracking flags?\n"
        "23. Process persistence: For background daemons/timers, does the tool use proper Linux process detachment or PID lockfile? Flag if background worker dies when main process exits.\n"
        "24. Audio fallbacks: For alarm/alert tools, is terminal bell used as primary signal? Are external audio imports wrapped in try/except?\n"
        "25. Command compliance: Does the generated CLI implement every explicit subcommand from the user prompt? Flag any dropped or swapped commands.\n"
        "26. Pattern matching integrity: Does regex/pattern tool match against the complete target string? Flag if extensions or paths are stripped before matching.\n"
        "27. Boundary validation: Are all numeric inputs range-checked before processing?"
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
        deployment="Local CLI script - no deployment target",
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
    print("\n🚀 [NOVA ENGINE INITIALIZED - LangGraph Mode]")
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
