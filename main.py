import sys
import time
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows so emoji/special chars don't crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

from src.agent import generate_linkedin_post_stream
from src.pdf_utils import save_post_as_pdf


def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        print("LinkedIn Post Creator Agent")
        print("-" * 40)
        topic = input("Enter a topic for your LinkedIn post: ").strip()
        if not topic:
            print("Error: Topic cannot be empty.")
            sys.exit(1)

    print(f"\nGenerating LinkedIn post about: {topic}\n")

    start = time.time()
    post  = None
    image_path = None
    image_base64 = None

    try:
        for event in generate_linkedin_post_stream(topic):
            etype = event["type"]

            if etype == "progress":
                pct = event["pct"]
                msg = event["msg"]
                if event.get("step") == "revising" and event.get("feedback"):
                    print(f"  [{pct:3d}%]  {msg}")
                    for line in event["feedback"].splitlines()[:5]:
                        print(f"           → {line}")
                else:
                    print(f"  [{pct:3d}%]  {msg}")

            elif etype == "result":
                post = event["post"]
                image_path = event.get("image_path")
                image_base64 = event.get("image_base64")

            elif etype == "error":
                print(f"\nFailed: {event['msg']}")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)

    elapsed = time.time() - start

    if post is None:
        print("\nFailed: no post was returned.")
        sys.exit(1)

    separator = "=" * 60
    print(f"\n{separator}")
    print("YOUR LINKEDIN POST")
    print(separator)
    print(post)
    print(separator)
    print(f"Character count: {len(post)}")
    print(f"Generated in:    {elapsed:.1f}s")

    try:
        pdf_path = save_post_as_pdf(post, topic)
        print(f"\nPDF saved to:   {pdf_path}")
        if image_path:
            print(f"Image saved to: {image_path}")
        if image_base64:
            print(f"Image Base64:   {len(image_base64)} bytes generated.")
    except Exception as e:
        print(f"\nWarning: Could not save PDF/Image outputs — {e}")


if __name__ == "__main__":
    main()
