import os
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from huggingface_hub import InferenceClient
from langgraph.graph import StateGraph, END

import time

load_dotenv()

# ── STATE ────────────────────────────────────────────
class NovaState(TypedDict):
    topic: str
    blueprint: str
    code: str
    audit: str

# ── LLMs ─────────────────────────────────────────────
gemini_llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=os.environ.get("GEMINI_API_KEY")
)
groq_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.environ.get("GROQ_API_KEY")
)
CODER_MODELS = [
    "nex-agi/nex-n2-pro:free",
    "deepseek/deepseek-r1-0528:free",
    "poolside/laguna-m.1:free",
    "nvidia/nemotron-3-super-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
]
hf_client = InferenceClient(token=os.environ.get("HF_TOKEN"))

def get_openrouter_llm(model_id):
    return ChatOpenAI(
        model=model_id,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )

# ── HELPERS ───────────────────────────────────────────
def call_with_fallback(primary, fallback, messages):
    try:
        return primary.invoke(messages).content
    except Exception as e:
        print(f"⚠ Primary failed: {e} → switching to fallback")
        return fallback.invoke(messages).content

def call_hf_reviewer(prompt):
    return groq_llm.invoke([HumanMessage(content=prompt)]).content

def call_coder(messages):
    for model_id in CODER_MODELS:
        try:
            print(f"🤖 Trying coder model: {model_id}")
            start = time.time()
            response = get_openrouter_llm(model_id).invoke(messages)
            elapsed = time.time() - start
            
            # token usage
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
    blueprint = call_with_fallback(groq_llm, get_openrouter_llm("deepseek/deepseek-r1-0528:free"), messages)
    with open("system_blueprint.md", "w") as f:
        f.write(blueprint)
    print("✅ Blueprint written.")
    return {**state, "blueprint": blueprint}

def coder_node(state: NovaState) -> NovaState:
    print("\n💻 [CODER] Writing code...")
    messages = [
        SystemMessage(content="""You are a senior Python engineer. Rules:
- Write ONLY the Python code, no explanations outside comments
- Single file output only
- No redundant abstractions — solve the problem directly
- If a feature needs 50 lines, write 50. If it needs 200, write 200. Never pad."""),
        HumanMessage(content=(
            f"Using this blueprint:\n\n{state['blueprint']}\n\n"
            "Write a fully functional Python script with robust error handling."
        ))
    ]
    code = call_coder(messages)
    with open("system_monitor.py", "w") as f:
        f.write(code)
    print("✅ Code written.")
    return {**state, "code": code}

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
    graph.add_node("reviewer", reviewer_node)
    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "coder")
    graph.add_edge("coder", "reviewer")
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
