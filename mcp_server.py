"""
MCP server that exposes LinkedIn post generation as a tool.

Run as an HTTP server (for MCP Inspector testing):
    python mcp_server.py
    python mcp_server.py --port 9000   # optional custom port

Then in MCP Inspector:
    Transport Type : Streamable HTTP
    URL            : http://localhost:8000/mcp   (or whatever port is printed)
    → Connect
"""

import argparse
from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from src.agent import generate_linkedin_post
from src.pdf_utils import save_post_as_pdf

# Parse port/host early so FastMCP binds to the right address from the start.
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--port", type=int, default=8000)
_parser.add_argument("--host", type=str, default="localhost")
_args, _ = _parser.parse_known_args()

mcp = FastMCP(
    "linkedin-post-creator",
    host=_args.host,
    port=_args.port,
    instructions=(
        "Creates professional LinkedIn posts grounded in real-time Google Search results. "
        "Each post follows a strict 5-part structure: emoji hook, pain, tech details, "
        "measurable result, and a closing question."
    ),
)

import os

@mcp.tool()
def create_linkedin_post(topic: str) -> str:
    """
    Generate a LinkedIn post about *topic* using live Google Search data.

    The agent runs 2-3 real searches via SerpAPI, extracts current statistics
    and insights, then writes a structured 5-part post:
      1. Hook — one emoji + bold opening statement (stands alone)
      2. Pain — how the task was done before / why the old way failed
      3. Tech — exact tools, frameworks, or scripts used with technical details
      4. Result — measurable outcome with real numbers
      5. Question — one direct question to drive comments

    The finished post is also saved as a PDF under the Posts/ folder.

    Args:
        topic: Subject for the LinkedIn post, e.g. "LangGraph for building AI agents"

    Returns:
        The generated post text followed by the relative paths and base64 image data.
    """
    post, image_path, base64_image = generate_linkedin_post(topic)

    try:
        pdf_path = save_post_as_pdf(post, topic)
        
        rel_pdf_path = os.path.relpath(pdf_path)
        result = f"{post}\n\n[PDF saved → {rel_pdf_path}]"
        
        if image_path:
            rel_image_path = os.path.relpath(image_path)
            result += f"\n[Image saved → {rel_image_path}]"
            
        if base64_image:
            result += f"\n\n--- Image Base64 Data ---\n{base64_image}\n-------------------------"
            
        return result
    except Exception as exc:
        return f"{post}\n\n[Save failed: {exc}]"


if __name__ == "__main__":
    print(f"\n LinkedIn Post Creator MCP Server")
    print(f" ─────────────────────────────────────────────────")
    print(f" Listening on : http://{_args.host}:{_args.port}/sse")
    print(f"")
    print(f" In MCP Inspector set:")
    print(f"   Transport Type → SSE")
    print(f"   URL            → http://{_args.host}:{_args.port}/sse")
    print(f" ─────────────────────────────────────────────────\n")

    mcp.run(transport="sse")
