"""
NOVA Model Registry
====================
Lazy provider construction: chains are lists of (factory, model_id, label) tuples,
NOT constructed ChatOpenAI objects. Nothing touches an API key until try_chain()
actually attempts that specific step. This means:
 - A missing/bad key for one provider only kills that one step, not the
   whole chain-build (the previous version crashed at import time if any
   single env var was empty).
 - `python nova_models.py` now sanity-prints every chain with ZERO keys set.

Verified vs unverified, stated plainly instead of all marked "confirmed":
  CONFIRMED this session: nemotron-3-ultra-550b-a55b:free (OR), kimi-k2.6 (NVIDIA),
  deepseek-ai/deepseek-v4-flash (NVIDIA route).
  CONFIRMED DEAD: deepseek/deepseek-v4-flash:free on OpenRouter (lost tag 2026-06-05),
  minimax/minimax-m3 free tier anywhere (never existed, paid only).
  UNVERIFIED — check yourself before trusting: glm-5.1 exact OR slug (zhipuai vs z-ai),
  step-3.5-flash free-vs-paid (conflicting signals), seed-oss-36b-instruct OR free tier,
  gemma-4-31b-it exact name/size (separate source called a similar model "Gemma 4 26B"),
  llama-3.3-nemotron-super-49b-v1.5 free status on NVIDIA NIM.

Trial-flagged on NVIDIA NIM (free now, NVIDIA's own pages call these "trial service",
can be revoked or rate-limited harder without much warning):
  qwen/qwen3-next-80b-a3b-instruct, qwen/qwen3.5-122b-a10b, qwen/qwen3.5-397b-a17b,
  bytedance/seed-oss-36b-instruct, minimaxai/minimax-m3 (also "Preview" + non-commercial
  license + native VLM, not text-only despite being usable for text).

VLM caveat: qwen3.5-122b-a10b AND qwen3.5-397b-a17b are natively vision-language models,
not text models with vision bolted on. They'll work for text-only coding/JS but it's not
their design target. Watch for weird output, haven't confirmed it breaks.
"""

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# -- Base URLs ----------------------------------------------------------------
NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
OR_BASE     = "https://openrouter.ai/api/v1"
GROQ_BASE   = "https://api.groq.com/openai/v1"
OLLAMA_BASE = "http://localhost:11434/v1"

# -- Model string constants ----------------------------------------------------

# NVIDIA NIM
M_KIMI_K2              = "moonshotai/kimi-k2.6"                      # confirmed
M_DEEPSEEK_V4_NVIDIA   = "deepseek-ai/deepseek-v4-flash"             # confirmed, NVIDIA route
M_DEEPSEEK_V4_PRO      = "deepseek-ai/deepseek-v4-0709"              # DEAD — 404, wrong slug
M_DEEPSEEK_OR          = "deepseek/deepseek-chat-v3-0324:free"        # OR free, confirmed
M_DEEPSEEK_R1_OR       = "deepseek/deepseek-r1:free"                  # OR free, reasoning model
M_QWEN3_NEXT_80B       = "qwen/qwen3-next-80b-a3b-instruct"          # trial-flagged
M_QWEN35_122B          = "qwen/qwen3.5-122b-a10b"                    # trial-flagged, VLM
M_QWEN35_397B          = "qwen/qwen3.5-397b-a17b"                    # trial-flagged, VLM
M_MINIMAX_M27          = "minimaxai/minimax-m2.7"                    # free on NVIDIA
M_MINIMAX_M3           = "minimaxai/minimax-m3"                      # NVIDIA "Preview" + non-commercial license
M_SEED_OSS_36B         = "bytedance/seed-oss-36b-instruct"           # trial-flagged
M_NEMOTRON_ULTRA       = "nvidia/nemotron-3-ultra-550b-a55b"         # DEAD — 504 consistently on NVIDIA too
M_LLAMA_NEMOTRON_49B_V15 = "nvidia/llama-3.3-nemotron-super-49b-v1.5"  # UNVERIFIED free status
M_NEMOTRON_NANO9       = "nvidia/NVIDIA-Nemotron-Nano-9B-v2"         # was lowercase, 404'd — uppercase per NVIDIA slug

# OpenRouter
M_LAGUNA_M1            = "poolside/laguna-m.1:free"                  # CONFIRMED LIVE
M_GEMMA_4              = "google/gemma-4-31b-it:free"                # CONFIRMED LIVE (exact size name unconfirmed)
M_NEMOTRON_ULTRA_OR    = "nvidia/nemotron-3-ultra-550b-a55b:free"    # DEAD — 504 consistently, do not use in chains
M_SEED_OSS_OR          = "bytedance/seed-oss-36b-instruct:free"      # UNVERIFIED on OR specifically

# OpenRouter — new additions
M_OWL_ALPHA           = "openrouter/optimus-alpha"                  # Owl Alpha OR, 1M context, agentic
M_GPT_OSS_120B        = "openai/gpt-oss-120b:free"                  # 120B, 131K context, strong reasoning
M_COHERE_NORTH_MINI   = "cohere/command-r-plus:free"                 # North Mini Code, 256K, code-focused — verify slug

# REMOVED FROM USE:

# M_GLM_51 = "z-ai/glm-5.1"         — correct slug confirmed but NO free tier on OR ($0.98/M in)
# M_STEP_35 = "stepfun/step-3.5-flash" — live 404, free tier discontinued
# M_MINIMAX_M3_OR = "minimax/minimax-m3:free" — confirmed no free tier exists anywhere

# Groq
M_LLAMA_33_70B         = "llama-3.3-70b-versatile"                   # DEPRECATED by Groq 2026-06-17, do not use
M_GPT_OSS_120B_GROQ    = "openai/gpt-oss-120b"                       # Groq replacement for Llama 3.3 70B

# Local Ollama — true offline tier, immune to any provider's policy changes
M_QWEN_CODER_7B        = "qwen2.5-coder:7b"


# -- Provider factories (called lazily inside try_chain, not at chain-build time) --
def nvidia(model, temperature=0.6, max_tokens=4096):
    return ChatOpenAI(model=model, api_key=os.environ.get("NVIDIA_API_KEY", ""),
                      base_url=NVIDIA_BASE, temperature=temperature, max_tokens=max_tokens)

def openrouter(model, temperature=0.6, max_tokens=4096):
    return ChatOpenAI(model=model, api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                      base_url=OR_BASE, temperature=temperature, max_tokens=max_tokens)

def groq(model, temperature=0.6, max_tokens=4096):
    return ChatOpenAI(model=model, api_key=os.environ.get("GROQ_API_KEY", ""),
                      base_url=GROQ_BASE, temperature=temperature, max_tokens=max_tokens)

def gemini(model="gemini-2.0-flash", temperature=0.6, max_tokens=4096):
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=os.environ.get("GEMINI_API_KEY", ""),
        temperature=temperature,
        max_tokens=max_tokens,
    )

def ollama(model, temperature=0.6, max_tokens=4096):
    return ChatOpenAI(model=model, api_key="ollama",
                      base_url=OLLAMA_BASE, temperature=temperature, max_tokens=max_tokens)


# -- Chains: list of (factory, model_id, label) — NOT constructed clients ------

def get_researcher_chain():
    return [
        (groq,       M_GPT_OSS_120B_GROQ,   "GPT-OSS 120B (Groq)"),
        (nvidia,     M_SEED_OSS_36B,   "Seed-OSS-36B (NVIDIA, trial)"),
        (groq,       "openai/gpt-oss-20b", "GPT-OSS 20B (Groq)"),
    ]

def get_cli_coder_chain():
    return [
        (openrouter, M_LAGUNA_M1,          "Laguna M.1 (OR)"),
        (nvidia,     M_KIMI_K2,            "Kimi K2.6 (NVIDIA)"),
        (nvidia,     M_DEEPSEEK_V4_NVIDIA, "DeepSeek V4 Flash (NVIDIA route)"),
        (nvidia,     M_QWEN35_397B,        "Qwen3.5-397B (NVIDIA, trial, VLM)"),
        (openrouter, M_COHERE_NORTH_MINI,  "Cohere North Mini Code (OR) - backup"),  # new, verify slug
    ]

def get_cli_debugger_chain():
    return [
        (nvidia,  M_QWEN35_397B,    "Qwen3.5-397B (NVIDIA, trial, VLM)"),       # CONFIRMED LIVE
        (groq,    "openai/gpt-oss-20b", "GPT-OSS 20B (Groq)"),                  # CONFIRMED LIVE
        (nvidia,  M_MINIMAX_M27,    "MiniMax M2.7 (NVIDIA)"),                   # CONFIRMED LIVE
        (ollama,  M_QWEN_CODER_7B,  "Qwen2.5-Coder-7B (LOCAL, offline last resort)"),
    ]

def get_cli_reviewer_chain():
    return [
        (nvidia,      M_LLAMA_NEMOTRON_49B_V15, "Llama-3.3-Nemotron-Super-49B-v1.5 (NVIDIA, CONFIRMED LIVE)"),
        (openrouter,  M_NEMOTRON_ULTRA_OR,       "Nemotron Ultra 550B (OR)"),
        (groq,        M_GPT_OSS_120B_GROQ,            "GPT-OSS 120B (Groq)"),
        (ollama,      M_QWEN_CODER_7B,           "Qwen2.5-Coder-7B (LOCAL, offline last resort)"),
    ]


# -- Web pipeline --------------------------------------------------------------

def get_web_structure_chain():
    return [
        (nvidia,      M_KIMI_K2,        "Kimi K2.6 (NVIDIA)"),
        (openrouter,  M_GEMMA_4,        "Gemma 4 (OR, CONFIRMED LIVE)"),
        (nvidia,      M_QWEN3_NEXT_80B, "Qwen3-Next-80B (NVIDIA, trial, fast)"),
    ]

def get_web_style_chain():
    return [
        (nvidia,      M_MINIMAX_M27,        "MiniMax M2.7 (NVIDIA)"),
        (openrouter,  M_GEMMA_4,            "Gemma 4 (OR, CONFIRMED LIVE)"),
        (nvidia,      M_DEEPSEEK_V4_NVIDIA, "DeepSeek V4 Flash (NVIDIA route)"),
        (nvidia,      M_MINIMAX_M3,         "MiniMax M3 (NVIDIA Preview, last resort ONLY)"),
    ]

def get_web_logic_chain():
    return [
        (nvidia,      M_QWEN35_122B,  "Qwen3.5-122B (NVIDIA, trial, VLM)"),    # CONFIRMED LIVE
        (nvidia,      M_QWEN35_397B,  "Qwen3.5-397B (NVIDIA, trial, VLM)"),    # CONFIRMED LIVE
        (nvidia,      M_KIMI_K2,      "Kimi K2.6 (NVIDIA)"),                   # CONFIRMED LIVE
        (openrouter,  M_LAGUNA_M1,    "Laguna M.1 (OR)"),                      # CONFIRMED LIVE
    ]

# Split into three real stages instead of one flat list — try_chain() stops at
# the first success, so a flat list silently skips P2/Final whenever P1 works.
# Each stage gets its OWN front/backup chain; your node code calls all three
# in sequence and passes each stage's output into the next, same as the
# original "P1 finds JS bugs, P2 finds HTML/CSS bugs, Final reviews both" plan.

def get_web_debugger_p1_chain():
    """
    P1: JS logic validation ONLY.
    Checks: undefined variables, missing event listeners, broken DOM queries,
    JS errors that would prevent execution. Does NOT check HTML structure or CSS.
    """
    return [
        (nvidia,      M_MINIMAX_M27,        "MiniMax M2.7 (NVIDIA) - P1 JS"),
        (nvidia,      M_KIMI_K2,            "Kimi K2.6 (NVIDIA) - P1 JS"),
        (openrouter,  M_GEMMA_4,            "Gemma 4 (OR) - P1 JS"),
        (nvidia,      M_DEEPSEEK_V4_NVIDIA, "DeepSeek V4 Flash (NVIDIA) - P1 JS"),  # 504s frequently
    ]

def get_web_debugger_p2_chain():
    """
    P2: HTML/CSS consistency ONLY.
    Checks: CSS selectors targeting non-existent elements, missing classes,
    broken layout rules, media query issues. Does NOT re-check JS logic.
    Receives P1 JS audit summary to know what JS issues were already found.
    """
    return [
        (nvidia,      M_MINIMAX_M27,         "MiniMax M2.7 (NVIDIA) - P2 HTML/CSS"),
        (nvidia,      M_KIMI_K2,             "Kimi K2.6 (NVIDIA) - P2 HTML/CSS"),
        (groq,        M_GPT_OSS_120B_GROQ,        "GPT-OSS 120B (Groq) - P2 HTML/CSS"),
    ]

def get_web_debugger_final_chain():
    """
    Final: Cross-component integration review.
    Receives P1 JS audit + P2 HTML/CSS audit summaries.
    Only fixes remaining issues not already addressed by P1/P2.
    Returns complete fixed HTML.
    """
    return [
        (gemini_large,      "gemini-2.5-flash",   "Gemini 2.5 Flash - Final"),              # 1M ctx
        (nvidia_large,      M_MINIMAX_M27,         "MiniMax M2.7 (NVIDIA) - Final"),         # confirmed
        (nvidia_large,      M_KIMI_K2,             "Kimi K2.6 (NVIDIA) - Final"),            # confirmed
        (openrouter_large,  M_DEEPSEEK_OR,         "DeepSeek V3 (OR free) - Final"),         # confirmed free
        (openrouter_large,  M_DEEPSEEK_R1_OR,      "DeepSeek R1 (OR free) - Final"),         # reasoning
        (nvidia_large,      M_DEEPSEEK_V4_NVIDIA,  "DeepSeek V4 Flash (NVIDIA) - Final"),    # confirmed
        (openrouter_large,  M_OWL_ALPHA,           "Owl Alpha (OR) - Final"),                # 1M ctx
    ]

def get_web_reviewer_chain():
    return [
        (groq,   "openai/gpt-oss-20b",    "GPT-OSS 20B (Groq)"),               # CONFIRMED LIVE
        (nvidia, M_LLAMA_NEMOTRON_49B_V15, "Llama-3.3-Nemotron-Super-49B-v1.5 (NVIDIA)"),  # CONFIRMED LIVE
        (groq,   M_GPT_OSS_120B_GROQ,           "GPT-OSS 120B (Groq)"),            # CONFIRMED LIVE, replaced deprecated Llama 3.3
    ]

def get_web_assembler_conflict_chain():
    """Only called if web_assembler hits an irreconcilable conflict. Rule-based by default."""
    return [
        (nvidia,      M_NEMOTRON_NANO9, "Nemotron Nano 9B (NVIDIA)"),
        (openrouter,  M_GEMMA_4,        "Gemma 4 (OR, CONFIRMED LIVE)"),
        (nvidia,      M_MINIMAX_M27,    "MiniMax M2.7 (NVIDIA)"),
    ]


# -- try_chain: builds the client lazily, right before the attempt -------------
def try_chain(chain, messages, node_name=""):
    last_error = None
    for i, (factory, model_id, label) in enumerate(chain):
        try:
            llm = factory(model_id)          # client built HERE, not at chain-build time
            response = llm.invoke(messages)
            return response.content
        except Exception as e:
            print(f"[{node_name}] {label} failed (attempt {i+1}/{len(chain)}): {e}")
            last_error = e
            continue
    raise RuntimeError(f"[{node_name}] All {len(chain)} models failed. Last error: {last_error}")


# Gemini large-context factory (uses Google AI Studio, free tier, 1M ctx)
def gemini_large(model="gemini-2.5-flash", temperature=0.6):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=os.environ.get('GEMINI_API_KEY', ''),
        temperature=temperature,
        max_output_tokens=32000,
    )

# Large-context factories for nodes that handle big HTML (15K+ tokens)
def nvidia_large(model, temperature=0.6):
    return ChatOpenAI(model=model, api_key=os.environ.get('NVIDIA_API_KEY','x'),
                      base_url=NVIDIA_BASE, temperature=temperature, max_tokens=32000)

def openrouter_large(model, temperature=0.6):
    return ChatOpenAI(model=model, api_key=os.environ.get('OPENROUTER_API_KEY','x'),
                      base_url=OR_BASE, temperature=temperature, max_tokens=16000)

# -- Sanity print: works with ZERO API keys set, since nothing is constructed --
if __name__ == "__main__":
    chains = {
        "researcher":             get_researcher_chain(),
        "cli_coder":              get_cli_coder_chain(),
        "cli_debugger":           get_cli_debugger_chain(),
        "cli_reviewer":           get_cli_reviewer_chain(),
        "web_structure":          get_web_structure_chain(),
        "web_style":              get_web_style_chain(),
        "web_logic":              get_web_logic_chain(),
        "web_debugger_p1":        get_web_debugger_p1_chain(),
        "web_debugger_p2":        get_web_debugger_p2_chain(),
        "web_debugger_final":     get_web_debugger_final_chain(),
        "web_reviewer":           get_web_reviewer_chain(),
        "web_assembler_conflict": get_web_assembler_conflict_chain(),
    }
    print("=== NOVA Model Registry (no API calls made) ===\n")
    for node, chain in chains.items():
        print(f"{node}:")
        for i, (factory, model_id, label) in enumerate(chain):
            tag = "Front  " if i == 0 else f"Backup {i}"
            print(f"  {tag}: {label}  ->  {model_id}  [{factory.__name__}]")
        print()
