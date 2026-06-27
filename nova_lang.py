import os
import ast
import uuid
import time
import subprocess
import re
import sqlite3

import subprocess

SKILL_PATH = "skills/ui-ux/src/ui-ux-pro-max/scripts/search.py"

WEB_KEYWORDS = [
    "website", "web", "html", "css", "landing page",
    "portfolio website", "frontend website", "webpage", "site",
    "landing page", "web app", "web application"
]

def is_web_task(topic: str) -> bool:
    topic_lower = topic.lower()
    return any(kw in topic_lower for kw in WEB_KEYWORDS)

def query_ui_skill(query: str, domain: str) -> str:
    try:
        result = subprocess.run(
            ["python3", SKILL_PATH, query, "--domain", domain],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Skill query failed: {e}"

def get_web_design_context(topic: str) -> str:
    domains = ["style", "color", "typography", "ux"]
    results = []
    for domain in domains:
        output = query_ui_skill(topic, domain)
        if output and "Found: 0" not in output:
            results.append(f"### {domain.upper()} GUIDANCE\n{output}")
    return "\n\n".join(results)
from datetime import datetime
from nova_graph_memory import ExperienceGraph
graph_memory = ExperienceGraph()
from nova_projects import ProjectDNA
project_dna = ProjectDNA()
from dotenv import load_dotenv
from typing import TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from nova_models import (
    try_chain,
    get_researcher_chain,
    get_cli_coder_chain,
    get_cli_debugger_chain,
    get_cli_reviewer_chain,
    get_web_structure_chain,
    get_web_style_chain,
    get_web_logic_chain,
    get_web_debugger_p1_chain,
    get_web_debugger_p2_chain,
    get_web_debugger_final_chain,
    get_web_reviewer_chain,
    get_web_assembler_conflict_chain,
)

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
    task_type: str
    html_structure: str
    css_code: str
    js_code: str
    final_html: str

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
    complex_keywords = ["database", "auth", "api", "multi", "server", "sqlite", "encryption", "website"]
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
# All LLM instantiation is now handled lazily in nova_models.py via try_chain().
# No global LLM objects here — nothing crashes at startup if a key is missing.

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
# call_coder and call_hf_reviewer replaced by try_chain() from nova_models.py

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
            "- If structural splitting is needed for filesystem safety, handle it internally after matching, not before.\n"
            "- NEVER split filename into .stem or .suffix before matching. Always run regex/pattern logic against the raw .name attribute of the path object.\n\n"
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
    blueprint = try_chain(get_researcher_chain(), messages, "researcher")
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
    code = try_chain(get_cli_coder_chain(), messages, "cli_coder")
    print(f"DEBUG: code length = {len(code)} chars")
    return {**state, "code": code}

def debug_node(state: NovaState) -> NovaState:
    print("\n🔧 [DEBUGGER] Validating and fixing code...")
    print("🔧 Debugger: using cli_debugger chain from nova_models")
    if is_web_task(state['topic']):
        print("✅ Web output - skipping Python syntax check.")
        # Strip markdown fences if coder wrapped output
        clean_code = state['code'].strip()
        # Remove any lines before <!DOCTYPE or <html
        if '<!DOCTYPE' in clean_code:
            clean_code = clean_code[clean_code.find('<!DOCTYPE'):]
        elif '<html' in clean_code:
            clean_code = clean_code[clean_code.find('<html'):]
        if clean_code.startswith("```"):
            clean_code = clean_code.split("\n", 1)[1]
        if clean_code.endswith("```"):
            clean_code = clean_code.rsplit("```", 1)[0]
        clean_code = clean_code.strip()
        with open(f"runs/{state['run_id']}_code.html", "w") as f:
            f.write(clean_code)
        with open("system_monitor.py", "w") as f:
            f.write(state['code'])
        return {**state, "code": state['code']}

    is_valid, result = validate_code(state['code'])
    if is_valid:
        print("✅ Code is syntactically valid.")
        _run_meta["syntax_valid"] = True
        with open(f"runs/{state['run_id']}_code.py", "w") as f:
            f.write(result)
        with open("system_monitor.py", "w") as f:
            f.write(result)
        return {**state, "code": result}

    print(f"⚠ Syntax error found: {result}")
    # debugger chain used inline below
    messages = [
        SystemMessage(content="You are a debugging specialist. Fix the syntax error in this code. Return ONLY the corrected raw Python code, no markdown, no explanation."),
        HumanMessage(content=f"Code:\n{state['code']}\n\nError:\n{result}")
    ]
    try:
        fixed = try_chain(get_cli_debugger_chain(), messages, "cli_debugger")
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
                print(f"⚠ Graph logging skipped: {ge}")
        else:
            print(f"⚠ Fix attempt still broken: {final_code}")
            _run_meta["syntax_valid"] = False
            ext = "html" if is_web_task(state['topic']) else "py"
            with open(f"runs/{state['run_id']}_code.{ext}", "w") as f:
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
    if is_web_task(state['topic']):
        print("✅ Web output - skipping Python smoke test.")
        return {**state, "execution_valid": True}
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
        print(f"⚠ Graph mapping log skipped: {ge}")

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
        "26. Pattern matching integrity: Does regex/pattern tool match against the complete target string? Flag if extensions or paths are stripped before matching. Explicitly verify no .stem or .suffix variable splitting occurs before pattern evaluation.\n"
        "27. Boundary validation: Are all numeric inputs range-checked before processing?"
    )
    audit = try_chain(get_cli_reviewer_chain(), [HumanMessage(content=prompt)], "cli_reviewer")
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

# ── WEB NODES ─────────────────────────────────────────────────────

def web_structure_node(state: NovaState) -> NovaState:
    print("\n🏗 [WEB STRUCTURE] Building HTML skeleton...")
    design_context = get_web_design_context(state['topic'])
    messages = [
        SystemMessage(content=(
            "You are a senior HTML architect. Output ONLY raw HTML with NO CSS and NO JavaScript.\n"
            "- Return only the HTML skeleton with proper semantic structure.\n"
            "- Use meaningful IDs and classes that CSS and JS will target.\n"
            "- Include placeholder comments like <!-- STYLE_INJECT --> in <head> and <!-- SCRIPT_INJECT --> before </body>.\n"
            "- No inline styles. No script tags. Pure structural HTML only.\n"
            "- Use semantic tags: header, nav, main, section, article, footer.\n"
            "- Every interactive element must have a unique ID.\n"
            "- CONTENT RULES: Use ONLY content explicitly stated in the blueprint below. "
            "Do NOT invent names, projects, skills, experience, testimonials, stats, or any other content. "
            "Use placeholder text like [NAME], [PROJECT_TITLE], [SKILL] where real content isn't specified. "
            "Never fabricate realistic-looking fake data.\n"
            f"\nDESIGN CONTEXT:\n{design_context}"
        )),
        HumanMessage(content=f"Build the complete HTML structure for: {state['blueprint']}")
    ]
    html = try_chain(get_web_structure_chain(), messages, "web_structure")
    lines = html.split('\n')
    if lines[0].strip().startswith('`'):
        lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    html = '\n'.join(lines)
    if '<!DOCTYPE' in html:
        html = html[html.find('<!DOCTYPE'):]
    elif '<html' in html:
        html = html[html.find('<html'):]
    print(f"DEBUG: HTML structure length = {len(html)} chars")
    with open(f"runs/{state['run_id']}_structure.html", "w") as f:
        f.write(html)
    return {**state, "html_structure": html.strip(), "task_type": "web"}


def web_style_node(state: NovaState) -> NovaState:
    print("\n🎨 [WEB STYLE] Generating CSS...")
    messages = [
        SystemMessage(content=(
            "You are a senior CSS architect. Output ONLY raw CSS code, no HTML, no JS.\n"
            "- Write comprehensive CSS for the provided HTML structure.\n"
            "- Use CSS custom properties (variables) for theming.\n"
            "- Include smooth animations, transitions, hover effects.\n"
            "- Mobile-first responsive design with media queries.\n"
            "- Glassmorphism, gradients, and modern visual effects where appropriate.\n"
            "- Target ONLY the IDs and classes present in the HTML structure provided.\n"
            "- Include keyframe animations for entrance effects and scroll reveals.\n"
            "- No external imports. Pure CSS only.\n"
            "- Do NOT generate any content, copy, or text. CSS only — no comments containing fake names or data."
        )),
        HumanMessage(content=f"Write complete CSS for this HTML structure:\n\n{state['html_structure']}")
    ]
    css = try_chain(get_web_style_chain(), messages, "web_style")
    if '\n' in css and css.split('\n')[0].strip().startswith('```'):
        css = '\n'.join(css.split('\n')[1:])
    if css.strip().endswith('```'):
        css = css.strip()[:-3].strip()
    print(f"DEBUG: CSS length = {len(css)} chars")
    with open(f"runs/{state['run_id']}_style.css", "w") as f:
        f.write(css)
    return {**state, "css_code": css.strip()}


def web_logic_node(state: NovaState) -> NovaState:
    print("\n⚡ [WEB LOGIC] Generating JavaScript...")
    messages = [
        SystemMessage(content=(
            "You are a senior JavaScript engineer. Output ONLY raw JavaScript, no HTML, no CSS.\n"
            "- Write complete vanilla JS for all interactivity and animations.\n"
            "- Target ONLY element IDs and classes that exist in the HTML structure provided.\n"
            "- Implement: smooth scroll, scroll reveal animations, typing effects, canvas animations if needed.\n"
            "- All DOM queries must use IDs/classes from the HTML structure — never assume element names.\n"
            "- Always wrap DOM queries in DOMContentLoaded event listener.\n"
            "- Implement real-time data updates with setInterval where needed.\n"
            "- Handle all interactive elements: buttons, forms, navigation, modals.\n"
            "- No external libraries. Pure vanilla JS only.\n"
            "- Add error handling for all DOM queries — check element exists before using it.\n"
            "- CONTENT RULES: Do NOT hardcode any names, project titles, skills, stats, or realistic-looking fake data in JS strings or arrays. "
            "If dynamic content is needed, read it from the DOM (from HTML placeholders) — never generate it in JS."
        )),
        HumanMessage(content=(
            f"Write complete JavaScript for this HTML structure:\n\n{state['html_structure']}\n\n"
            f"The CSS classes and animations defined are:\n\n{state['css_code'][:2000]}..."
        ))
    ]
    js = try_chain(get_web_logic_chain(), messages, "web_logic")
    if not js.strip():
        print("⚠ JS empty on first attempt — retrying web_logic...")
        js = try_chain(get_web_logic_chain(), messages, "web_logic_retry")
    if '\n' in js and js.split('\n')[0].strip().startswith('```'):
        js = '\n'.join(js.split('\n')[1:])
    if js.strip().endswith('```'):
        js = js.strip()[:-3].strip()
    print(f"DEBUG: JS length = {len(js)} chars")
    with open(f"runs/{state['run_id']}_logic.js", "w") as f:
        f.write(js)
    return {**state, "js_code": js.strip()}


def web_assembler_node(state: NovaState) -> NovaState:
    print("\n🔧 [WEB ASSEMBLER] Combining HTML + CSS + JS...")
    html = state['html_structure']
    print(f"DEBUG ASSEMBLER: html_structure length = {len(html)} chars")
    css = state['css_code']
    js = state['js_code']

    # Inject CSS
    style_tag = f"<style>\n{css}\n</style>"
    if '<!-- STYLE_INJECT -->' in html:
        html = html.replace('<!-- STYLE_INJECT -->', style_tag)
    else:
        html = html.replace('</head>', f"{style_tag}\n</head>", 1)

    # Inject JS
    script_tag = f"<script>\n{js}\n</script>"
    if '<!-- SCRIPT_INJECT -->' in html:
        html = html.replace('<!-- SCRIPT_INJECT -->', script_tag)
    else:
        html = html.replace('</body>', f"{script_tag}\n</body>", 1)

    print(f"DEBUG: Final HTML length = {len(html)} chars")
    with open(f"runs/{state['run_id']}_code.html", "w") as f:
        f.write(html)
    with open("system_monitor.py", "w") as f:
        f.write(html)
    return {**state, "final_html": html, "code": html}


def web_debugger_node(state: NovaState) -> NovaState:
    print("\n🔍 [WEB DEBUGGER] Validating HTML/CSS/JS consistency...")
    messages = [
        SystemMessage(content=(
            "You are a browser debugging expert. Analyze the provided HTML, CSS, and JS for consistency issues.\n"
            "Check for:\n"
            "1. JS references to IDs/classes that don't exist in HTML\n"
            "2. CSS selectors targeting non-existent elements\n"
            "3. Undefined variables in JS\n"
            "4. Missing event listeners for interactive elements\n"
            "5. Canvas/animation code that won't execute\n"
            "If issues found, return the COMPLETE FIXED HTML file with CSS and JS embedded.\n"
            "If no issues, return the HTML unchanged.\n"
            "Return ONLY raw HTML, no explanation."
        )),
        HumanMessage(content=(
            f"HTML Structure:\n{state['html_structure'][:3000]}\n\n"
            f"CSS (first 2000 chars):\n{state['css_code'][:2000]}\n\n"
            f"JavaScript (first 3000 chars):\n{state['js_code'][:3000]}\n\n"
            f"Full assembled HTML:\n{state['final_html'][:5000]}"
        ))
    ]
    try:
        # 3-stage debugger: P1=JS logic, P2=HTML/CSS consistency, Final=combined review
        p1_result = try_chain(get_web_debugger_p1_chain(), messages, "web_debugger_p1")
        p2_messages = messages + [HumanMessage(content=f"P1 JS audit result:\n{p1_result}\nNow check HTML/CSS consistency.")]
        p2_result = try_chain(get_web_debugger_p2_chain(), p2_messages, "web_debugger_p2")
        final_messages = messages + [HumanMessage(content=f"P1 JS audit:\n{p1_result}\n\nP2 HTML/CSS audit:\n{p2_result}\n\nNow return the complete fixed HTML.")]
        fixed = try_chain(get_web_debugger_final_chain(), final_messages, "web_debugger_final")
    except Exception as e:
        print(f"⚠ Web debugger failed: {e} — skipping, using assembled HTML")
        return state
    if '<!DOCTYPE' in fixed:
        fixed = fixed[fixed.find('<!DOCTYPE'):]
    if fixed.startswith('```'):
        fixed = fixed.split('\n', 1)[1]
    if fixed.endswith('```'):
        fixed = fixed.rsplit('```', 1)[0]
    if len(fixed) > 1000:
        with open(f"runs/{state['run_id']}_code.html", "w") as f:
            f.write(fixed)
        print("✅ Web debugger applied fixes.")
        return {**state, "final_html": fixed, "code": fixed}
    print("✅ Web debugger: no critical issues found.")
    return state


def web_reviewer_node(state: NovaState) -> NovaState:
    print("\n🔍 [WEB REVIEWER] Auditing final output...")
    prompt = (
        f"You are a senior web QA engineer. Review this complete HTML/CSS/JS file:\n\n"
        f"{state['final_html'][:6000]}\n\n"
        f"ORIGINAL USER REQUEST: {state['topic']}\n\n"
        "Check:\n"
        "1. All sections render with visible content\n"
        "2. Navigation links point to existing section IDs\n"
        "3. All interactive elements have JS handlers\n"
        "4. Animations and transitions are defined\n"
        "5. Mobile responsiveness\n"
        "6. No broken references between HTML, CSS, JS\n"
        "7. SEMANTIC ALIGNMENT: Does the output match what the user actually asked for? "
        "List every feature/section explicitly requested in the original user request and confirm "
        "whether it is present in the output. Flag anything requested but missing or misimplemented.\n"
        "8. PLACEHOLDER CHECK: Flag any [NAME], [PROJECT_TITLE], [SKILL] or similar placeholders "
        "still present in the output that the user needs to fill in.\n"
        "Write a structured Markdown audit report."
    )
    try:
        audit = try_chain(get_web_reviewer_chain(), [HumanMessage(content=prompt)], "web_reviewer")
    except Exception as e:
        print(f"⚠ Web reviewer failed: {e} — skipping audit")
        audit = f"Web reviewer unavailable: {e}"
        with open(f"runs/{state['run_id']}_web_audit.md", "w") as f:
            f.write(audit)
        return {**state, "audit": audit}
    with open(f"runs/{state['run_id']}_web_audit.md", "w") as f:
        f.write(audit)
    print("✅ Web audit written.")
    return {**state, "audit": audit}


def route_after_researcher(state: NovaState) -> str:
    if is_web_task(state['topic']):
        return "web_structure"
    return "coder"

def build_graph():
    graph = StateGraph(NovaState)
    # CLI nodes
    graph.add_node("researcher", researcher_node)
    graph.add_node("coder", coder_node)
    graph.add_node("debugger", debug_node)
    graph.add_node("tester", test_node)
    graph.add_node("reviewer", reviewer_node)
    # Web nodes
    graph.add_node("web_structure", web_structure_node)
    graph.add_node("web_style", web_style_node)
    graph.add_node("web_logic", web_logic_node)
    graph.add_node("web_assembler", web_assembler_node)
    graph.add_node("web_debugger", web_debugger_node)
    graph.add_node("web_reviewer", web_reviewer_node)
    graph.set_entry_point("researcher")
    # CLI edges
    graph.add_conditional_edges("researcher", route_after_researcher, {"coder": "coder", "web_structure": "web_structure"})
    graph.add_edge("coder", "debugger")
    graph.add_edge("debugger", "tester")
    # Web edges
    graph.add_edge("web_structure", "web_style")
    graph.add_edge("web_style", "web_logic")
    graph.add_edge("web_logic", "web_assembler")
    graph.add_edge("web_assembler", "web_debugger")
    graph.add_edge("web_debugger", "web_reviewer")
    graph.add_edge("web_reviewer", END)
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
            "run_id": run_id, "task_type": "",
            "html_structure": "", "css_code": "", "js_code": "", "final_html": ""
        })
        print("\n" + "="*60)
        print("✅ Pipeline completed.")
        print(f"📂 Run ID: {run_id} | Files saved in runs/{run_id}_*.py/md")
        print("="*60)
