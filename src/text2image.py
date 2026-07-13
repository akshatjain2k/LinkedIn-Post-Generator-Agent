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
        "**Role:** You are an expert AI Image Prompt Designer specializing in the `flux_2_klein_4b` model.\n\n"
        "**Task:** I will provide a topic, concept, or piece of content. Your job is to generate a highly detailed, "
        "natural-language image prompt optimized for Flux based on my input.\n\n"
        "**Rules for Flux Prompting:**\n"
        "1. **Natural Language:** Write in descriptive, full sentences. Paint a picture with your words. Do NOT use disjointed keyword lists or tag stuffing.\n"
        "2. **Subject First:** Always start the prompt by clearly describing the main subject and their action, pose, or state.\n"
        "3. **Structure Layers:** Build the prompt in this exact order: \n"
        "   [Subject & Action] -> [Environment & Context] -> [Lighting Details] -> [Camera/Technical Specs] -> [Overall Style/Vibe].\n"
        "4. **Lighting & Camera Specs:** Include specific photographic terms to enhance realism. Use focal lengths (e.g., 35mm for wide shots, 85mm for portraits), apertures (e.g., f/2.8 for blurred backgrounds), and lighting styles (e.g., golden hour, three-point studio lighting, cinematic low-key lighting).\n"
        "5. **No Negatives or Weights:** Do not write negative prompts (e.g., \"no blurry faces\") and do not use weight syntax (e.g., \"(masterpiece:1.5)\"). Focus only on what *should* be in the image.\n"
        "6. **Text Rendering:** If the topic requires readable text (like a sign, UI mockup, or logo), explicitly state the text in quotes (e.g., holding a coffee cup that reads \"Morning Fuel\").\n"
        "7. **Length:** Keep the final prompt focused and vivid, ideally between 40 and 100 words.\n\n"
        "**Output:** Provide ONLY the final text prompt ready to be copied and pasted into the Flux image generator. "
        "Do not include any surrounding conversational text or explanations. Do not include markdown blocks."
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