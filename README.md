# LinkedIn Post Creator Agent

An AI-powered agent that takes a topic, searches Google for real, current information, writes a developer-focused LinkedIn post, evaluates it against strict writing rules, generates a highly simplified vector-art diagram representing the concept, and saves both the post (as a PDF) and the image (as a PNG). Exposed via a fully polished **Next.js Frontend**, a CLI tool, and an MCP tool.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [End-to-End Flow](#end-to-end-flow)
- [Setup](#setup)
- [Usage](#usage)
  - [Web UI (Next.js)](#web-ui-nextjs)
  - [CLI](#cli)
  - [MCP Server](#mcp-server)
- [Configuration](#configuration)

---

## Features

### Web UI (Next.js)
| Feature | Details |
|---|---|
| **Dynamic Theming** | Sun/Moon toggle for Space Black (Dark) or Slate (Light) mode with ethereal ambient glowing backgrounds. |
| **Interactive UX** | Staggered typewriter animations for post text, skeleton loaders, and pulsing "Thinking" button states. |
| **Design Canvas** | Architectural diagrams are rendered on a dotted-grid blueprint canvas with drop shadows. |
| **Lightbox Modal** | Click any generated image to view it in a full-screen, high-res modal overlay. |
| **Content Metrics** | Live calculation of word count, read time, and character limits (with an amber warning if you exceed 3,000 characters). |
| **Hashtag Chips** | Automatically parses raw hashtags and styles them as sleek, purple-tinted pill badges. |
| **One-Click Post** | "Post to LinkedIn" button instantly copies your post and redirects you directly to the LinkedIn feed to paste. |
| **Direct Downloads** | Dedicated buttons to download the post as a PDF and the diagram as a PNG. |

### Backend Agent
| Feature | Details |
|---|---|
| **DeepSeek V4-Flash** | Optimized to use the lightning-fast `deepseek-v4-pro` model via the OpenAI-compatible endpoint. |
| **Real-time research** | Runs up to `MAX_SEARCHES` live Google searches via SerpAPI before writing. |
| **Structured narrative** | Fixed story arc: problem → tool → hard result → question. |
| **Evaluator agent** | Separate LLM call checks the post against all writing rules; forces revisions until approved. |
| **Flux Image Engine** | Uses a highly engineered Flux prompt pipeline executed locally via `draw-things-cli` (`flux_2_klein_4b_q6p.ckpt`). |
| **PDF export** | Auto-saves every post to `Posts/<topic>/<topic>.pdf` using Calibri font (Unicode + emoji). |

---

## Tech Stack

| Component | Technology |
|---|---|
| **Frontend UI** | `Next.js 16` (App Router), `React 19`, `lucide-react`, Vanilla CSS (Glassmorphism & CSS Variables) |
| **LLM Engine** | DeepSeek (`deepseek-v4-pro`) via `langchain_openai` |
| **Agent Framework** | `langgraph` — explicit `StateGraph` with typed state, named nodes, conditional routing |
| **Web Search** | SerpAPI (`google-search-results`) wrapped as a LangChain `@tool` |
| **PDF Generation** | `reportlab` — fast, native PDF generation using standard Helvetica font |
| **Image Generation** | `draw-things-cli` executing the `flux_2_klein_4b_q6p.ckpt` model locally |
| **Backend API** | `mcp[cli]` — FastMCP over Streamable HTTP transport |

---

## Project Structure

```
Post Creator Agent/
│
├── frontend/                # Next.js 16 Web UI
│   ├── src/app/page.tsx     # Main layout, Lightbox, Copy & Redirect, Metrics
│   ├── src/app/globals.css  # CSS Variables, Ambient Backgrounds, Skeleton Loaders
│   └── src/app/api/         # API routes connecting Frontend to Backend MCP
│
├── main.py                  # CLI entry point
├── mcp_server.py            # MCP HTTP server
├── requirements.txt
├── .env                     # API keys and tuning values (not committed)
│
├── src/
│   ├── text2image.py        # Local image generation script (Flux via draw-things-cli)
│   ├── agent.py             # LangGraph graph, evaluator, image trigger, progress stream
│   ├── tools.py             # search_google tool (SerpAPI)
│   ├── prompts.py           # SYSTEM_PROMPT + EVALUATOR_PROMPT
│   └── pdf_utils.py         # PDF generation & folder routing
│
└── Posts/                   # Auto-created structure for assets (PDFs & PNGs)
```

---

## End-to-End Flow

### 1 — Input
The user provides a topic (e.g. `"Redis caching for API performance"`) via the Next.js UI, the CLI, or MCP.

### 2 — Progress Stream
The backend streams structured events indicating exactly what the pipeline is doing, updating the frontend UI seamlessly.

### 3 — LangGraph StateGraph & Evaluation Loop
The agent searches the web, drafts the post, and then enters a strict evaluation loop. The Evaluator LLM checks against the rules and forces revisions until approved or `MAX_REVISIONS` is reached.

### 4 — Image Generation
Once the post text is finalized, the pipeline triggers `text2image.py`.
- An LLM constructs a highly descriptive, minimalist prompt optimized strictly for Flux.
- The prompt is sent to `draw-things-cli`, executing the Flux model locally.
- The resulting `.png` is saved.

### 5 — Output & Export
- The text is exported to a `.pdf` file.
- The `.png` file is encoded to Base64.
- All files are organized into a clean folder: `Posts/<Topic_Name>/`.
- The UI parses the response, renders the hashtags into chips, computes reading metrics, and presents the image in a blueprint canvas.

---

## Setup

### 1. Install Backend Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure `.env`
```bash
cp .env.example .env   # then open .env and fill in your keys
```

**DeepSeek Configuration:**
```env
DEEPSEEK_API_KEY=sk-...
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=deepseek-v4-pro
LLM_BASE_URL=https://api.deepseek.com
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=1
LLM_TOP_P=0.95

SERPAPI_API_KEY=...

MAX_SEARCHES=2
MAX_REVISIONS=1
```

### 3. Local Image Generation Setup (Draw Things)
To enable the image generation step, you must configure your local machine to run Flux via Draw Things:
1. Ensure the **Draw Things** application is installed on your Mac.
2. Install the `draw-things-cli` command-line utility and ensure it is available in your terminal's `$PATH`.
3. Inside Draw Things, ensure you have downloaded the required model: `flux_2_klein_4b_q6p.ckpt`.

### 4. Install Frontend Dependencies
```bash
cd frontend
npm install
```

---

## Usage

### Web UI (Next.js)
**1. Start Backend MCP Server:**
```bash
python mcp_server.py
```
**2. Start Frontend Dev Server:**
```bash
cd frontend
npm run dev
```
Navigate to `http://localhost:3000` to access the full UI!

### CLI
```bash
# Run via CLI
python main.py "FastAPI vs Flask for Python APIs"
```

### MCP Server Connect via Inspector
1. Transport Type → `Streamable HTTP`
2. URL → `http://localhost:8000/mcp`
3. Connect → Tools → `create_linkedin_post` → enter topic → Run Tool
