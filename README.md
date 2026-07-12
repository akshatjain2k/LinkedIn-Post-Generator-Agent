# LinkedIn Post Creator Agent

An AI-powered agent that takes a topic, searches Google for real, current information, writes a developer-focused LinkedIn post, evaluates it against strict writing rules, generates a highly simplified vector-art diagram representing the concept, and saves both the post (as a PDF) and the image (as a PNG). Exposed as both a CLI tool and an MCP tool callable from Claude Code, Claude Desktop, or MCP Inspector.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [End-to-End Flow](#end-to-end-flow)
- [Setup](#setup)
- [Usage](#usage)
  - [CLI](#cli)
  - [MCP Server](#mcp-server)
- [Configuration](#configuration)

---

## Features

| Feature | Details |
|---|---|
| Real-time research | Runs up to `MAX_SEARCHES` live Google searches via SerpAPI before writing |
| Generic LLM | Works with NVIDIA NIM (native SDK) or any OpenAI-compatible endpoint — swap with a few `.env` lines |
| Structured narrative | Fixed story arc: problem → tool → hard result → question |
| Developer voice | No marketing language, no exclamation marks, dry and factual |
| Hard numbers | Requires a real metric from search (latency, time saved, cost) — no invented stats |
| Evaluator agent | Separate LLM call checks the post against all writing rules; returns `[STATUS: GO AHEAD]` or `[STATUS: REVISION NEEDED]` with bullet feedback |
| Local Image Generation | Uses a local Flux model via `draw-things-cli` to generate a simplified, clear flowchart or conceptual diagram for the post. |
| PDF export | Auto-saves every post to `Posts/<topic>/<topic>.pdf` using Calibri font (Unicode + emoji) |
| Unified Outputs | Saves all assets (PDF and PNG) into dynamically named topic subdirectories. |
| Base64 API Support | Seamlessly returns raw Base64 image data alongside the text to support direct frontend UI rendering. |
| MCP tool | FastMCP over Streamable HTTP — callable from Claude Code, Claude Desktop, or MCP Inspector |

---

## Tech Stack

| Component | Technology |
|---|---|
| **LLM (NVIDIA path)** | `ChatNVIDIA` from `langchain_nvidia_ai_endpoints` — native NVIDIA NIM SDK |
| **LLM (OpenAI path)** | `ChatOpenAI` from `langchain_openai` — any OpenAI-compatible endpoint |
| **Agent Framework** | `langgraph` — explicit `StateGraph` with typed state, named nodes, conditional routing |
| **Web Search** | SerpAPI (`google-search-results`) wrapped as a LangChain `@tool` |
| **PDF Generation** | `reportlab` — fast, native PDF generation using standard Helvetica font |
| **Image Generation** | `draw-things-cli` executing the `flux_2_klein_4b_q6p.ckpt` model locally |
| **MCP Server** | `mcp[cli]` — FastMCP over Streamable HTTP transport |
| **Config** | `python-dotenv` — all credentials and behaviour values from `.env` |

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
│   ├── text2image.py        # Local image generation script (Flux via draw-things-cli)
│   ├── agent.py             # LangGraph graph, evaluator, image trigger, progress stream
│   ├── tools.py             # search_google tool (SerpAPI)
│   ├── prompts.py           # SYSTEM_PROMPT + EVALUATOR_PROMPT
│   └── pdf_utils.py         # PDF generation & folder routing
│
└── Posts/                   # Auto-created structure for assets
    └── <Topic_Name>/
        ├── <Topic_Name>.pdf
        └── <Topic_Name>.png
```

---

## End-to-End Flow

### 1 — Input

The user provides a topic (e.g. `"Redis caching for API performance"`).
- Via CLI: `python main.py "your topic"`
- Via MCP: Claude calls `create_linkedin_post(topic="your topic")`

### 2 — Progress Stream

Both surfaces call `generate_linkedin_post_stream(topic)` — a generator that yields structured events indicating exactly what the pipeline is doing at any moment.

### 3 — LangGraph StateGraph & Evaluation Loop

The agent searches the web, drafts the post, and then enters a strict evaluation loop. The Evaluator LLM checks against the rules and forces revisions until approved or `MAX_REVISIONS` is reached.

### 4 — Image Generation

Once the post text is finalized, the pipeline triggers `text2image.py`.
- An LLM constructs a highly descriptive, minimalist prompt based on the post.
- The prompt is sent to `draw-things-cli`, which executes the Flux model locally on your machine.
- The resulting `.png` is saved.

### 5 — Output & Export

- The text is exported to a `.pdf` file.
- The `.png` file is encoded to Base64.
- All files are organized into a clean folder: `Posts/<Topic_Name>/`.
- The CLI/MCP returns the post text, the relative file paths, and the Base64 image payload.

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

**OpenAI (Gemini/GPT Example):**
```env
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gemini-2.5-flash
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=1
LLM_TOP_P=0.95
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

SERPAPI_API_KEY=...

MAX_SEARCHES=2
MAX_REVISIONS=1
```

### 3. Local Image Generation Setup (Draw Things)

To enable the image generation step, you must configure your local machine to run Flux via Draw Things:
1. Ensure the **Draw Things** application is installed on your Mac.
2. Install the `draw-things-cli` command-line utility and ensure it is available in your terminal's `$PATH`.
3. Inside Draw Things, ensure you have downloaded the required model: `flux_2_klein_4b_q6p.ckpt`.
4. The pipeline will automatically invoke the CLI during the final generation phase.

---

## Usage

### CLI

```bash
# Run via CLI
python main.py "FastAPI vs Flask for Python APIs"
```

### MCP Server

**Start:**
```bash
python mcp_server.py
```

**Connect via MCP Inspector:**
1. Transport Type → `Streamable HTTP`
2. URL → `http://localhost:8000/mcp`
3. Connect → Tools → `create_linkedin_post` → enter topic → Run Tool
