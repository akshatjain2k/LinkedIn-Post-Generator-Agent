# LinkedIn Post Creator Agent

An AI-powered agent that takes a topic, searches Google for real, current information, writes a developer-focused LinkedIn post, evaluates it against strict writing rules, and saves it as a PDF. Exposed as both a CLI tool and an MCP tool callable from Claude Code, Claude Desktop, or MCP Inspector.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [End-to-End Flow](#end-to-end-flow)
- [Agent Graph](#agent-graph)
- [Setup](#setup)
- [Usage](#usage)
  - [CLI](#cli)
  - [MCP Server](#mcp-server)
- [Configuration](#configuration)
- [Post Format](#post-format)

---

## Features

| Feature | Details |
|---|---|
| Real-time research | Runs up to `MAX_SEARCHES` live Google searches via SerpAPI before writing |
| Generic LLM | Works with NVIDIA NIM (native SDK) or any OpenAI-compatible endpoint — swap with a few `.env` lines |
| Structured narrative | Fixed story arc: problem → tool → hard result → question |
| Developer voice | No marketing language, no exclamation marks, dry and factual |
| Hard numbers | Requires a real metric from search (latency, time saved, cost) — no invented stats |
| Search cap guard | Hard limit of `MAX_SEARCHES`; if hit, a `force_write` node redirects the LLM to write with what it has |
| Evaluator agent | Separate LLM call checks the post against all writing rules; returns `[STATUS: GO AHEAD]` or `[STATUS: REVISION NEEDED]` with bullet feedback |
| Revision loop | Up to `MAX_REVISIONS` rewrites driven by evaluator feedback; fails-open on evaluator error |
| Streaming progress | `generate_linkedin_post_stream()` yields `{"type", "pct", "msg"}` events — ready for CLI, MCP, or a future UI progress bar |
| PDF export | Auto-saves every post to `Posts/<topic>.pdf` using Calibri font (Unicode + emoji) |
| MCP tool | FastMCP over Streamable HTTP — callable from Claude Code, Claude Desktop, or MCP Inspector |
| Error handling | Human-readable errors for overload, rate limits, quota exhaustion, degraded/EOL models, bad keys |

---

## Tech Stack

| Component | Technology |
|---|---|
| **LLM (NVIDIA path)** | `ChatNVIDIA` from `langchain_nvidia_ai_endpoints` — native NVIDIA NIM SDK |
| **LLM (OpenAI path)** | `ChatOpenAI` from `langchain_openai` — any OpenAI-compatible endpoint |
| **Agent Framework** | `langgraph` — explicit `StateGraph` with typed state, named nodes, conditional routing |
| **Web Search** | SerpAPI (`google-search-results`) wrapped as a LangChain `@tool` |
| **PDF Generation** | `fpdf2` with system Calibri font for full Unicode + emoji support |
| **MCP Server** | `mcp[cli]` — FastMCP over Streamable HTTP transport |
| **Config** | `python-dotenv` — all credentials and behaviour values from `.env` |
| **Language** | Python 3.12 |

---

## Project Structure

```
Post Creator Agent/
│
├── main.py                  # CLI entry point
├── mcp_server.py            # MCP HTTP server
├── requirements.txt
├── .env                     # API keys and tuning values (not committed)
├── .gitignore
│
├── src/
│   ├── agent.py             # LangGraph graph, evaluator, progress stream generator
│   ├── tools.py             # search_google tool (SerpAPI)
│   ├── prompts.py           # SYSTEM_PROMPT + EVALUATOR_PROMPT
│   └── pdf_utils.py         # PDF generation
│
└── Posts/                   # Auto-created; one PDF per generated post
```

---

## End-to-End Flow

### 1 — Input

The user provides a topic (e.g. `"Redis caching for API performance"`).

- Via CLI: `python main.py "your topic"` or interactive prompt
- Via MCP: Claude calls `create_linkedin_post(topic="your topic")`

---

### 2 — Progress Stream

Both surfaces call `generate_linkedin_post_stream(topic)` — a generator that yields structured events:

```python
{"type": "progress", "step": "searching", "pct": 27, "msg": 'Searching: "Redis latency 2024"'}
{"type": "progress", "step": "evaluating", "pct": 73, "msg": "Evaluating post (attempt 1/1)..."}
{"type": "result",   "post": "<full post text>", "pct": 100}
{"type": "error",    "msg": "Model unavailable. Update LLM_MODEL in .env.", "pct": 0}
```

`main.py` iterates this stream and prints each step. `mcp_server.py` uses the blocking wrapper `generate_linkedin_post()`. A future UI can consume the same events over WebSocket or SSE without any code changes.

---

### 3 — LangGraph StateGraph (`src/agent.py`)

Three nodes, typed state:

```python
class AgentState(TypedDict):
    messages:     Annotated[list, add_messages]  # appended, never overwritten
    topic:        str
    search_count: int                            # searches planned by LLM so far
```

| Node | What it does |
|---|---|
| `researcher` | Calls the LLM with full message history; counts new tool calls |
| `tools` | Executes `search_google` via LangGraph's `ToolNode` |
| `force_write` | Injected when `search_count >= MAX_SEARCHES` — tells the LLM to write immediately |

**Routing after `researcher`:**
```
tool calls + under cap   →  tools
tool calls + cap hit     →  force_write → researcher
no tool calls (wrote)    →  END
```

---

### 4 — Evaluate → Revise Loop

After the graph produces a post, the generator runs:

```
for attempt in range(MAX_REVISIONS):
    approved, feedback = _evaluate_post(post, llm)
    if approved:
        yield result          # done
        return
    post = _run_revision(post, feedback, topic, llm)

yield result   # max revisions reached — return last version
```

`_evaluate_post()` sends the post + all writing rules to the LLM with `EVALUATOR_PROMPT`. Returns `[STATUS: GO AHEAD]` or `[STATUS: REVISION NEEDED]` + bullet feedback. Fails-open on error (approves silently).

`_run_revision()` rewrites the post using only the feedback — no re-searching. If the revised text is under 100 characters (garbled model output), it keeps the previous version.

---

### 5 — Progress Percentages

Recalibrate automatically when `MAX_SEARCHES` / `MAX_REVISIONS` change in `.env`:

```
  0 %        planning
  0 – 55 %   search phase      (divided evenly by MAX_SEARCHES)
 55 – 63 %   writing
 63 – 80 %   first evaluation
 80 – 95 %   revision phase    (divided evenly by MAX_REVISIONS)
100 %        result
```

---

### 6 — PDF Export (`src/pdf_utils.py`)

Saves to `Posts/<topic>.pdf` using Windows Calibri font (Unicode + emoji). Falls back to Helvetica on non-Windows.

---

## Agent Graph

```
       START
         │
         ▼
   ┌─────────────┐
   │  researcher │◄──────────────────────────┐
   └──────┬──────┘                            │
          │  _route()                         │
          ├── tool calls + under cap  ──► ┌──────┐
          │                               │tools │
          │◄──────────────────────────────┴──────┘
          │
          ├── tool calls + cap hit ──► ┌─────────────┐
          │                           │ force_write  │
          │◄──────────────────────────┴─────────────-┘
          │
          └── no tool calls ──► END
                                  │
                    ┌─────────────▼──────────────┐
                    │  evaluate → revise loop     │
                    │  (up to MAX_REVISIONS)      │
                    └─────────────┬──────────────┘
                                  ▼
                             yield result + PDF
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

```bash
cp .env.example .env   # then open .env and fill in your keys
```

**NVIDIA NIM (default):**
```env
LLM_PROVIDER=nvidia
LLM_API_KEY=nvapi-...
LLM_MODEL=qwen/qwen3-next-80b-a3b-instruct
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.6
LLM_TOP_P=0.7

SERPAPI_API_KEY=...

MAX_SEARCHES=2
MAX_REVISIONS=1
```

**OpenAI (swap example):**
```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=1
LLM_TOP_P=0.95
LLM_BASE_URL=        # leave blank for OpenAI; set URL for Gemini/Groq/Together

SERPAPI_API_KEY=...

MAX_SEARCHES=2
MAX_REVISIONS=1
```

**Why `MAX_SEARCHES` and `MAX_REVISIONS` are in `.env`:**

> **Cost control** — each search and revision is an LLM call. Tuning them per environment (dev vs prod) without touching code keeps the cost knob in one place.
>
> **Progress bar accuracy** — percentage milestones are calculated from these two values at startup. Change them in `.env` and the progress bar recalibrates automatically; no code change, no redeployment.

Get keys from:
- NVIDIA NIM: https://build.nvidia.com
- SerpAPI: https://serpapi.com

---

## Usage

### CLI

```bash
# Interactive
python main.py

# Argument
python main.py "FastAPI vs Flask for Python APIs"
python main.py "PostgreSQL indexing strategies"
python main.py "GitHub Actions CI/CD pipelines"
```

**Example terminal output:**
```
  [  0%]  Reasoning and planning searches...
  [ 58%]  Search cap (2) reached — writing with gathered data...
  [ 63%]  Writing the post...
  [ 73%]  Evaluating post (attempt 1/1)...
  [ 99%]  Evaluator approved — post is ready.

============================================================
YOUR LINKEDIN POST
============================================================
📉 Our Go services used to ship 650–900 MB Docker images...
============================================================
Character count: 560
Generated in:    51.6s

Post saved to: Posts/Docker_multi-stage_builds.pdf
```

---

### MCP Server

**Start:**
```bash
python mcp_server.py              # default port 8000
python mcp_server.py --port 9000
```

**Connect via MCP Inspector:**
1. Transport Type → `Streamable HTTP`
2. URL → `http://localhost:8000/mcp`
3. Connect → Tools → `create_linkedin_post` → enter topic → Run Tool

**Register with Claude Code:**
```bash
claude mcp add linkedin-post-creator \
  --env LLM_API_KEY="nvapi-..." \
  --env SERPAPI_API_KEY="..." \
  -- python "path/to/mcp_server.py"
```

**Register with Claude Desktop:**
```bash
mcp install mcp_server.py --name "linkedin-post-creator" --env-file .env
```

---

## Configuration

All values live in `.env`. No code changes needed when switching providers.

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `nvidia` → `ChatNVIDIA`; `openai` → `ChatOpenAI` |
| `LLM_API_KEY` | *(required)* | API key for your LLM provider |
| `LLM_MODEL` | *(required)* | Model ID, e.g. `qwen/qwen3-next-80b-a3b-instruct` or `gpt-4o` |
| `LLM_MAX_TOKENS` | `4096` | Max output tokens per LLM call |
| `LLM_TEMPERATURE` | `1` | Sampling temperature |
| `LLM_TOP_P` | `1` | Top-p sampling |
| `LLM_BASE_URL` | *(empty = OpenAI)* | Base URL for OpenAI-compatible endpoints (Gemini, Groq, etc.) |
| `LLM_ENABLE_THINKING` | `false` | NVIDIA nemotron thinking mode (openai provider only) |
| `LLM_REASONING_BUDGET` | `16384` | Nemotron thinking token budget |
| `LLM_EXTRA_BODY_JSON` | *(unset)* | Raw JSON merged into every request body (e.g. disable Gemini 2.5 thinking) |
| `MAX_SEARCHES` | `3` | Max Google searches per run; also scales the progress bar |
| `MAX_REVISIONS` | `2` | Max evaluator-driven rewrites; also scales the progress bar |
| `SERPAPI_API_KEY` | *(required)* | SerpAPI key for Google Search |
| `--port` | `8000` | MCP server port (CLI flag) |
| `--host` | `localhost` | MCP server host (CLI flag) |

---

## Post Format

```
[emoji] [hook — the problem, raw and specific]

[what tool/technique was used and how]

[the hard result — real metric from search]

[one specific developer question]

#hashtag1 #hashtag2 #hashtag3
```

**Example:**
```
📉 Our Go services used to ship 650–900MB Docker images because we built and ran in the same stage.
We switched to multi-stage builds: compile with golang:alpine, copy only the binary to scratch.
The largest service went from 847MB to 28MB — confirmed in a 2022 Docker case study.
Push time dropped from 42s to 14s on our CI runner.
What's your multi-stage build copying into the final stage that you could leave out?
#Docker #GoLang #DevOps #Containerization #BuildOptimization
```
