"""
LinkedIn Post Creator — LangGraph Agent
========================================

High-level flow
---------------
1. Researcher node   → plans Google searches and calls them via ToolNode
2. Tools node        → executes search_google(), feeds results back to researcher
3. Force-write node  → injected when MAX_SEARCHES cap is hit; tells LLM to write now
4. Evaluator         → separate LLM call that checks the post against writing rules
5. Revision loop     → up to MAX_REVISIONS rewrites if evaluator requests changes

All tuneable values (LLM provider, search caps, revision caps) live in .env.
No code changes are needed when switching providers or adjusting limits.

Public surface
--------------
  generate_linkedin_post_stream(topic) → Generator[dict, None, None]
      Yields progress events {"type":"progress"/"result"/"error", "pct":int, ...}
      Consume from a CLI loop, MCP handler, or future UI/WebSocket.

  generate_linkedin_post(topic) → str
      Blocking wrapper — iterates the stream, prints progress, returns the post.
"""

import io
import json
import os
import re
import sys
import unicodedata
from typing import Annotated, Generator
from typing_extensions import TypedDict

from pydantic import SecretStr
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .tools import search_google
from .prompts import SYSTEM_PROMPT, EVALUATOR_PROMPT


 # Configuration — all values come from .env (see .env for swap examples)
 
MAX_SEARCHES  = int(os.getenv("MAX_SEARCHES",  "3"))  # Google searches per run
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "2"))  # evaluator-driven rewrites


 # Progress percentage milestones
#
# The 0-100 range is split into four phases:
#   0  – 55 %  →  search phase     (evenly divided by MAX_SEARCHES)
#   55 – 63 %  →  writing phase
#   63 – 80 %  →  first evaluation
#   80 – 95 %  →  revision phase   (evenly divided by MAX_REVISIONS)
#   100 %      →  done
#
# Changing MAX_SEARCHES or MAX_REVISIONS in .env recalibrates all % values
# automatically — a UI progress bar needs no code changes.
 
_SEARCH_END_PCT   = 55
_WRITE_PCT        = 63
_FIRST_EVAL_PCT   = 73
_REVISE_START_PCT = 80
_REVISE_END_PCT   = 95


def _search_pct(n: int) -> int:
    """Return % after completing search number n (0-indexed total is MAX_SEARCHES)."""
    return int(_SEARCH_END_PCT * n / max(MAX_SEARCHES, 1))


def _revision_pct(n: int, re_eval: bool = False) -> int:
    """
    Return % for revision cycle n.
    Pass re_eval=True to get the slightly higher % used during re-evaluation.
    """
    span = (_REVISE_END_PCT - _REVISE_START_PCT) / max(MAX_REVISIONS, 1)
    base = _REVISE_START_PCT + int(span * n)
    return min(base + (3 if re_eval else 0), _REVISE_END_PCT)


 # Utility helpers
 
def _progress(msg: str) -> None:
    """Write to the *real* stdout even when sys.stdout is redirected to StringIO."""
    print(msg, file=sys.__stdout__, flush=True)


def _ev(step: str, pct: int, msg: str, **extra) -> dict:
    """Build a progress event dict. pct is clamped to 0–99 (100 is reserved for result)."""
    return {"type": "progress", "step": step, "pct": max(0, min(99, pct)), "msg": msg, **extra}


def _classify_llm_error(exc: Exception) -> RuntimeError:
    """
    Translate a raw LLM API exception into a human-readable RuntimeError.
    Covers the most common failure codes so the user sees a clear message.
    """
    s = str(exc)
    # Quota exhausted — check before generic RESOURCE_EXHAUSTED so Gemini quota
    # errors ("limit: 0", "exceeded your current quota") get a specific message.
    if "quota" in s.lower() or "exceeded your current quota" in s.lower():
        return RuntimeError(
            "LLM quota exhausted. Check your plan/billing at your provider's dashboard."
        )
    if "DEGRADED" in s or "end of life" in s.lower():
        return RuntimeError(
            "Model unavailable (degraded or end-of-life). "
            "Update LLM_MODEL in .env to an active model and retry."
        )
    if "503" in s or "RESOURCE_EXHAUSTED" in s or "Worker" in s:
        return RuntimeError("LLM server is overloaded. Wait a few seconds and retry.")
    if "429" in s:
        return RuntimeError("LLM rate limit hit. Wait a moment and retry.")
    if "401" in s or "403" in s:
        return RuntimeError("LLM API key invalid or unauthorised. Check LLM_API_KEY in .env.")
    return RuntimeError(f"LLM call failed: {exc}")


def _msg_text(msg: AIMessage) -> str:
    """
    Extract plain text from an AIMessage.
    Some providers (e.g. NVIDIA with thinking mode) return content as a list of
    typed blocks; this flattens them to a single string.
    """
    content = msg.content
    if isinstance(content, list):
        parts = [
            b["text"] if isinstance(b, dict) else str(b)
            for b in content
            if not isinstance(b, dict) or b.get("type") == "text"
        ]
        return " ".join(parts).strip()
    return (content or "").strip()


def _extract_post(state: dict) -> str:
    """
    Walk the final graph state messages in reverse and return the first
    AIMessage that contains actual post text (i.e. not a tool-call message).
    Returns "" if nothing usable is found.
    """
    for msg in reversed(state.get("messages", [])):
        if not isinstance(msg, AIMessage):
            continue
        if getattr(msg, "tool_calls", None):
            # This message only contains tool call requests, not post text
            continue
        text = _msg_text(msg)
        if text:
            return _strip_preamble(text)
    return ""


def _strip_preamble(text: str) -> str:
    """
    Remove model commentary before the actual post.
    The post always starts with an emoji, so we scan for the first emoji line.
    Also handles a "---" divider that some models add before the post body.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Emoji categories: So = other symbol, Sm = math, Sk = modifier, No = other number
        if stripped and unicodedata.category(stripped[0]) in ("So", "Sm", "Sk", "No"):
            return "\n".join(lines[i:]).strip()
        if re.match(r"^-{3,}$", stripped) and i + 1 < len(lines):
            remainder = "\n".join(lines[i + 1:]).strip()
            if remainder:
                return remainder
    return text.strip()


 # LLM factory
 
def _build_llm():
    """
    Build the LLM client from environment variables.

    LLM_PROVIDER=nvidia  → ChatNVIDIA (langchain_nvidia_ai_endpoints)
                           Use this for NVIDIA NIM models accessed via the native
                           NVIDIA SDK (e.g. z-ai/glm-5.1, meta/llama-3.3-70b-instruct).

    LLM_PROVIDER=openai  → ChatOpenAI (default)
                           Works with any OpenAI-compatible endpoint:
                           NVIDIA NIM, Gemini, Together AI, OpenAI, Groq, etc.

    Raises EnvironmentError if required keys are missing.
    """
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise EnvironmentError("LLM_API_KEY is not set. Add it to your .env file.")

    model = os.getenv("LLM_MODEL")
    if not model:
        raise EnvironmentError("LLM_MODEL is not set. Add it to your .env file.")

    temperature = float(os.getenv("LLM_TEMPERATURE", "1"))
    top_p       = float(os.getenv("LLM_TOP_P",       "1"))
    max_tokens  = int(os.getenv("LLM_MAX_TOKENS",    "4096"))
    provider    = os.getenv("LLM_PROVIDER", "openai").lower()

    # ── ChatNVIDIA path ───────────────────────────────────────────────────────
    if provider == "nvidia":
        return ChatNVIDIA(
            model=model,
            api_key=api_key,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

    # ── ChatOpenAI path (default) ─────────────────────────────────────────────
    base_url         = os.getenv("LLM_BASE_URL") or None
    enable_thinking  = os.getenv("LLM_ENABLE_THINKING", "false").lower() == "true"
    reasoning_budget = int(os.getenv("LLM_REASONING_BUDGET", "16384"))

    llm_kwargs: dict = dict(
        model=model,
        api_key=SecretStr(api_key),
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,  # type: ignore[call-arg]
    )

    if base_url:
        llm_kwargs["base_url"] = base_url

    # LLM_EXTRA_BODY_JSON: provider-specific JSON added to every request body.
    # Example — disable Gemini 2.5 thinking (required for tool calls to work):
    #   LLM_EXTRA_BODY_JSON={"thinking": {"thinking_budget": 0}}
    extra_body_json = os.getenv("LLM_EXTRA_BODY_JSON")
    if extra_body_json:
        try:
            llm_kwargs["extra_body"] = json.loads(extra_body_json)
        except json.JSONDecodeError as exc:
            raise EnvironmentError(f"LLM_EXTRA_BODY_JSON is not valid JSON: {exc}") from exc
    elif enable_thinking:
        # NVIDIA NIM nemotron thinking mode — only when LLM_PROVIDER=openai
        llm_kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": True},
            "reasoning_budget": reasoning_budget,
        }

    return ChatOpenAI(**llm_kwargs)  # type: ignore[call-arg]


 # AgentState — the typed dict that flows through every graph node
 
class AgentState(TypedDict):
    messages:     Annotated[list, add_messages]  # append-only; never overwritten
    topic:        str                             # original topic; constant throughout
    search_count: int                             # cumulative searches planned by LLM


 # LangGraph nodes
# All nodes are silent — no print statements. Progress is emitted by the
# generator in generate_linkedin_post_stream(), not from inside the graph.
 
def _make_researcher_node(llm_with_tools):
    """
    Researcher node: calls the LLM with the current message history.
    The LLM either requests more searches (tool_calls) or writes the final post.
    """
    def researcher(state: AgentState) -> dict:
        try:
            response = llm_with_tools.invoke(state["messages"])
        except Exception as exc:
            raise _classify_llm_error(exc) from exc

        # Count how many new tool calls the LLM requested
        new_searches = len(response.tool_calls) if getattr(response, "tool_calls", None) else 0
        return {
            "messages":     [response],
            "search_count": state.get("search_count", 0) + new_searches,
        }
    return researcher


def _make_tools_node(tools):
    """Tools node: executes the search tool requested by the researcher."""
    tool_node = ToolNode(tools)

    def run_tools(state: AgentState) -> dict:
        try:
            return tool_node.invoke(state)
        except Exception as exc:
            err = str(exc).lower()
            if "serpapi" in err or "api_key" in err:
                raise RuntimeError("SerpAPI search failed. Check SERPAPI_API_KEY in .env.") from exc
            raise RuntimeError(f"Search tool failed: {exc}") from exc

    return run_tools


def _force_write_node(state: AgentState) -> dict:  # noqa: ARG001
    """
    Force-write node: injected when the search cap is hit.
    Adds a HumanMessage telling the LLM to write the post immediately
    instead of trying to search again.
    """
    return {"messages": [HumanMessage(content=(
        "You've done enough research. "
        "Stop searching and write the LinkedIn post now using the information "
        "you've already gathered. Follow the system prompt format exactly."
    ))]}


 # Routing
 
def _route(state: AgentState) -> str:
    """
    Decides what happens after each researcher node run:
      - LLM made tool calls AND under the search cap  →  run the tools
      - LLM made tool calls AND hit the search cap    →  force_write
      - LLM made no tool calls (wrote the post)       →  END
    """
    last_message   = state["messages"][-1]
    has_tool_calls = bool(getattr(last_message, "tool_calls", None))

    if has_tool_calls:
        return "tools" if state.get("search_count", 0) < MAX_SEARCHES else "force_write"
    return END


 # Graph assembly
 
def build_graph(llm):
    """
    Compile the LangGraph StateGraph.

    Topology
    ────────
        START
          ↓
      researcher ──(tool calls, under cap)──► tools ──┐
          ↑                                            │
          └────────────────────────────────────────────┘
          │
          ├──(tool calls, cap hit)──► force_write ──► researcher
          │
          └──(no tool calls = post written)──► END
    """
    tools          = [search_google]
    llm_with_tools = llm.bind_tools(tools)

    workflow = StateGraph(AgentState)
    workflow.add_node("researcher",  _make_researcher_node(llm_with_tools))
    workflow.add_node("tools",       _make_tools_node(tools))
    workflow.add_node("force_write", _force_write_node)

    workflow.add_edge(START, "researcher")
    workflow.add_conditional_edges(
        "researcher", _route,
        {"tools": "tools", "force_write": "force_write", END: END},
    )
    workflow.add_edge("tools",       "researcher")
    workflow.add_edge("force_write", "researcher")

    return workflow.compile()


# Build once at import time. If keys are missing, _graph stays None and
# every call to generate_linkedin_post_stream() emits an error event.
try:
    _llm   = _build_llm()
    _graph = build_graph(_llm)
except EnvironmentError as e:
    _llm         = None  # type: ignore[assignment]
    _graph       = None  # type: ignore[assignment]
    _graph_error = str(e)
else:
    _graph_error = ""


# Evaluator helpers
 
def _evaluate_post(post: str, llm) -> tuple[bool, str]:
    """
    Ask the evaluation LLM to review the post against the writing rules.

    Returns:
        (True, "")          → evaluator approved  [STATUS: GO AHEAD]
        (False, feedback)   → evaluator wants changes  [STATUS: REVISION NEEDED]

    If the evaluation API call itself fails we silently approve so a transient
    error never permanently blocks post delivery.
    """
    messages = [
        SystemMessage(content=EVALUATOR_PROMPT),
        HumanMessage(content=(
            f"## Writing Rules\n\n{SYSTEM_PROMPT}\n\n"
            f"## Post to Evaluate\n\n{post}"
        )),
    ]

    # Redirect stdout so LangChain callbacks don't corrupt the terminal
    _real_stdout, sys.stdout = sys.stdout, io.StringIO()
    try:
        response = llm.invoke(messages)
    except Exception:
        return True, ""   # fail-open: approve on evaluator error
    finally:
        sys.stdout = _real_stdout

    text     = _msg_text(response)
    approved = "[STATUS: GO AHEAD]" in text
    return approved, ("" if approved else text)


def _run_revision(post: str, feedback: str, topic: str, llm) -> str:
    """
    Ask the LLM to rewrite the post based on evaluator feedback.
    Does NOT re-search — all research data is already inside the post text.
    Returns the original post unchanged if the rewrite call fails.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"You previously wrote this LinkedIn post about '{topic}':\n\n{post}\n\n"
            f"The content evaluator found these issues:\n{feedback}\n\n"
            "Rewrite the post fixing every listed issue. "
            "Keep all research data and numbers intact. "
            "Output only the final post — no preamble, no commentary."
        )),
    ]

    _real_stdout, sys.stdout = sys.stdout, io.StringIO()
    try:
        response = llm.invoke(messages)
    except Exception:
        return post   # keep previous version on failure
    finally:
        sys.stdout = _real_stdout

    text = _msg_text(response)
    # Require a sensible minimum length before accepting the revision.
    # Some providers return short artefacts (e.g. "<<<END_TOOL_CALL>>>") on errors;
    # those should be discarded in favour of the previous version.
    if text and len(text) > 100:
        return _strip_preamble(text)
    return post


 # Public API
 
ProgressEvent = dict  # alias for readability in type hints


def generate_linkedin_post_stream(topic: str) -> Generator[ProgressEvent, None, None]:
    """
    Generator — yields structured progress events, then the final post.

    Every yielded value is a plain dict with a "type" key:

        progress  →  {"type": "progress", "step": str, "pct": int, "msg": str, ...}
        result    →  {"type": "result",   "post": str, "pct": 100}
        error     →  {"type": "error",    "msg": str,  "pct": int}

    Steps and their "pct" values (all scale with MAX_SEARCHES / MAX_REVISIONS):
        planning      0 %       LLM reasoning before first search
        searching    per-search  about to fire search n  (+query, n, total)
        search_done  per-search  search n complete       (+n, total)
        force_write  ~60 %      search cap hit, forcing write
        writing      63 %       LLM composing the final post
        evaluating   73–93 %    evaluation running       (+attempt, total)
        approved     99 %       evaluator passed
        revising     per-rev    rewriting                (+n, total, feedback)
        max_revisions 95 %      cap hit, returning last version

    Usage:
        for event in generate_linkedin_post_stream("Redis caching"):
            if event["type"] == "progress":
                update_ui(event["pct"], event["msg"])
            elif event["type"] == "result":
                show_post(event["post"])
            elif event["type"] == "error":
                show_error(event["msg"])
    """
    # ── Guard: check setup ───────────────────────────────────────────────────
    print("Starting now....ß")
    if _graph is None or _llm is None:
        yield {"type": "error", "msg": _graph_error, "pct": 0}
        return

    if not topic or not topic.strip():
        yield {"type": "error", "msg": "Topic cannot be empty.", "pct": 0}
        return

    # ── Phase 1: LangGraph generation ───────────────────────────────────────
    initial_state: AgentState = {
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Create a LinkedIn post about: {topic}"),
        ],
        "topic":        topic,
        "search_count": 0,
    }

    yield _ev("planning", 0, "Reasoning and planning searches...")

    searches_done  = 0                              # tracks actual completed searches
    prev_msg_count = len(initial_state["messages"]) # used to detect new messages in stream
    final_state: dict = {}

    # We stream in "values" mode so each chunk IS the full state after a node runs.
    # The last chunk we receive becomes final_state — no separate invoke() needed.
    #
    # Why redirect stdout?
    # LangGraph / LangChain write callback logs to sys.stdout. We silence them by
    # pointing sys.stdout at a StringIO buffer. We restore it around every yield
    # so our caller's print() calls still work normally.
    _real_stdout = sys.stdout
    sys.stdout   = io.StringIO()
    try:
        for state in _graph.stream(initial_state, stream_mode="values"):
            sys.stdout = _real_stdout  # restore so yield is visible to caller

            msgs = state.get("messages", [])
            print(f"Graph state: {len(msgs)} messages, {state.get('search_count', 0)} searches planned")
            # LangGraph may yield the initial state unchanged as the very first chunk.
            # Skip it — we only care about states where a new message was added.
            if len(msgs) <= prev_msg_count:
                prev_msg_count = len(msgs)
                sys.stdout = io.StringIO()
                continue

            new_msg        = msgs[-1]
            prev_msg_count = len(msgs)
            final_state    = state  # keep updating; last value = final graph state

            # ── Interpret which node just ran based on message type ──────────
            if isinstance(new_msg, AIMessage) and getattr(new_msg, "tool_calls", None):
                # Researcher ran and wants to search.
                #
                # Guard: only emit "searching" events when the searches will actually
                # run. state["search_count"] already includes the new calls. If it
                # equals or exceeds MAX_SEARCHES, _route() will send to force_write
                # instead of tools — no real search will happen.
                if state.get("search_count", 0) < MAX_SEARCHES:
                    for tc in new_msg.tool_calls:
                        query = tc.get("args", {}).get("query", "")
                        yield _ev("searching", _search_pct(searches_done),
                                  f'Searching: "{query}"',
                                  query=query, n=searches_done + 1, total=MAX_SEARCHES)

            elif isinstance(new_msg, AIMessage):
                # Researcher ran and produced no tool calls → wrote the final post
                yield _ev("writing", _WRITE_PCT, "Writing the post...")

            elif isinstance(new_msg, ToolMessage):
                # Tools node ran → one search completed
                searches_done += 1
                yield _ev("search_done", _search_pct(searches_done),
                          f"Search {searches_done}/{MAX_SEARCHES} complete",
                          n=searches_done, total=MAX_SEARCHES)

            elif isinstance(new_msg, HumanMessage):
                # force_write node injected a HumanMessage ("stop searching, write now")
                yield _ev("force_write", _WRITE_PCT - 5,
                          f"Search cap ({MAX_SEARCHES}) reached — writing with gathered data...")

            sys.stdout = io.StringIO()  
            # re-redirect before next node runs

    except RuntimeError as exc:
        sys.stdout = _real_stdout
        yield {"type": "error", "msg": str(exc), "pct": _search_pct(searches_done)}
        return
    except Exception as exc:
        sys.stdout = _real_stdout
        yield {"type": "error", "msg": f"Agent graph failed: {exc}", "pct": _search_pct(searches_done)}
        return
    finally:
        sys.stdout = _real_stdout  # always restore, even on exception

    # ── Extract the finished post from the final graph state ─────────────────
    post = _extract_post(final_state)
    print(f"Final post length: {len(post)} characters")
    if not post:
        yield {"type": "error",
               "msg": "Agent returned no content. The model may have been cut off.",
               "pct": _WRITE_PCT}
        return

    # ── Phase 2: evaluate → revise loop ─────────────────────────────────────
    for attempt in range(MAX_REVISIONS):

        # Determine the % to show for this evaluation step
        eval_pct = _FIRST_EVAL_PCT if attempt == 0 else _revision_pct(attempt, re_eval=True)
        yield _ev("evaluating", eval_pct,
                  f"Evaluating post (attempt {attempt + 1}/{MAX_REVISIONS})...",
                  attempt=attempt + 1, total=MAX_REVISIONS)

        approved, feedback = _evaluate_post(post, _llm)

        if approved:
            yield _ev("approved", 99, "Evaluator approved — post is ready.")
            yield {"type": "result", "post": post, "pct": 100}
            return

        # Evaluator found issues — rewrite the post
        feedback_lines = [ln.strip() for ln in feedback.splitlines() if ln.strip()]
        yield _ev("revising", _revision_pct(attempt + 1),
                  f"Revision {attempt + 1}/{MAX_REVISIONS} — fixing evaluator feedback...",
                  n=attempt + 1, total=MAX_REVISIONS,
                  feedback="\n".join(feedback_lines[:8]))  # cap feedback to 8 lines

        post = _run_revision(post, feedback, topic, _llm)

    # All revision attempts used — return whatever we have
    yield _ev("max_revisions", _REVISE_END_PCT,
              f"Max revisions ({MAX_REVISIONS}) reached — returning last version.")
    yield {"type": "result", "post": post, "pct": 100}


def generate_linkedin_post(topic: str) -> str:
    """
    Blocking convenience wrapper around generate_linkedin_post_stream().

    Iterates the stream, prints each step to the terminal as [pct%] msg,
    and returns the finished post string.

    Raises:
        RuntimeError — for any generation or evaluation failure.
        ValueError   — if topic is empty (emitted as error event and re-raised).
    """
    print(f"\nGenerating LinkedIn post about: {topic}\n")
    for event in generate_linkedin_post_stream(topic):
        if event["type"] == "progress":
            _progress(f"  [{event['pct']:3d}%]  {event['msg']}")
        elif event["type"] == "result":
            return event["post"]
        elif event["type"] == "error":
            raise RuntimeError(event["msg"])
    raise RuntimeError("Stream ended without a result.")
