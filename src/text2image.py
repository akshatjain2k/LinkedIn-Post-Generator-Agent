import argparse
import subprocess
from pathlib import Path
import sys
import io
import base64

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import SystemMessage, HumanMessage
from src.agent import _build_llm, _msg_text

def create_image_prompt(post_content: str) -> str:
    """
    Uses the configured LLM to generate a rich text-to-image prompt
    based on the provided LinkedIn post content.
    """
    llm = _build_llm()
    system_prompt = (
        "You are an expert AI image prompt generator. Your task is to read the provided LinkedIn post, "
        "understand the core message or technical concept being explained, and generate a highly descriptive "
        "image prompt for a text-to-image model (like Flux/Midjourney) that visually represents that specific concept. "
        "The image should include technical elements like flowcharts, architectural diagrams, or AI concepts, but they MUST be extremely simple, clear, and easy to understand. "
        "Avoid overly dense architectures, cluttered data pipelines, or overwhelming detail. "
        "Think of a clean, minimalist flowchart or a highly simplified architecture diagram that a beginner could understand at a glance. "
        "Use a modern, professional color palette with bright, friendly colors and plenty of empty space. "
        "Do not include any text, letters, words, or UI elements in the image. "
        "Reply ONLY with the image prompt, nothing else."
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=post_content)
    ]
    
    # Redirect stdout so LangChain callbacks don't corrupt the terminal
    _real_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        response = llm.invoke(messages)
    except Exception as e:
        sys.stdout = _real_stdout
        raise RuntimeError(f"Failed to generate image prompt: {e}")
    finally:
        sys.stdout = _real_stdout

    return _msg_text(response)

def generate_image(post_content: str, image_name: str, output_dir: Path | str | None = None) -> tuple[str, str]:
    """
    Generates an image from the post content.
    Returns a tuple of (absolute_image_path, base64_image_data).
    """
    # 1. Generate the prompt using LLM
    print("Generating optimized image prompt...")
    image_prompt = create_image_prompt(post_content)
    print(f"Generated Prompt: {image_prompt}\n")

    # 2. Setup output directory
    if output_dir is None:
        output_dir = Path(__file__).parent / "image_output"
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure .png extension
    if not image_name.lower().endswith(".png"):
        image_name += ".png"

    output_path = output_dir / image_name

    # IMPORTANT: Delete existing file so draw-things-cli doesn't silently skip generation
    if output_path.exists():
        output_path.unlink()

    # 3. Call draw-things-cli
    command = [
        "draw-things-cli",
        "generate",
        "--model", "flux_2_klein_4b_q6p.ckpt",
        "--prompt", image_prompt,
        "--output", str(output_path),
    ]

    print("Starting image generation...")
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Image generation failed:\n{result.stderr}"
        )

    print(f"Image saved: {output_path}")
    
    # Read the generated image and encode to base64
    with open(output_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        
    return str(output_path), encoded_string

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate an image based on LinkedIn post content using Draw Things CLI"
    )

    parser.add_argument(
        "post_content",
        type=str,
        help="The LinkedIn post content to base the image on",
    )

    parser.add_argument(
        "image_name",
        type=str,
        help="Output image name (with or without .png)",
    )

    args = parser.parse_args()

    try:
        path, b64 = generate_image(
            post_content=args.post_content,
            image_name=args.image_name,
        )
        print(f"Base64 length: {len(b64)}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)