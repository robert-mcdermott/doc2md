import argparse
import os
import sys
import base64
import requests

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "bmp", "webp")
DEFAULT_ENDPOINT = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5vl:latest"


def encode_image_to_data_url(data: bytes, image_ext: str) -> str:
    ext = image_ext.lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:image/{ext};base64,{b64}"


def extract_markdown_from_image(endpoint: str, model: str, image_bytes: bytes, image_ext: str, api_key: str | None = None) -> str:
    data_url = encode_image_to_data_url(image_bytes, image_ext)
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Please extract all text from this image and convert it to Markdown format "
                            "attempting to preserve the original document formating. "
                            "The output should be a Markdown representation of the orginal image/document text. "
                            "If there are tables in the images, recreate them as Markdown tables in the output. "
                            "Formatted Markdown output only, no HTML."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(endpoint, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def process_pdf(path: str, endpoint: str, model: str, api_key: str | None = None) -> str:
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        print(
            "Error: PDF support requires the 'pymupdf' package. Install it with: \n"
            "  uv add pymupdf\n"
            f"Details: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        doc = fitz.open(path)
    except Exception as e:
        print(f"Error opening PDF: {e}", file=sys.stderr)
        sys.exit(1)

    page_count = len(doc)
    results = []
    # Render at 2x scale (~144 DPI) for readability while keeping size reasonable
    matrix = fitz.Matrix(2.0, 2.0)

    for i, page in enumerate(doc, start=1):
        try:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            text = extract_markdown_from_image(endpoint, model, png_bytes, "png", api_key=api_key)
            results.append(text)
            print(f"Processed page {i}/{page_count}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"Error processing page {i}: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Rendering error on page {i}: {e}", file=sys.stderr)
            sys.exit(1)

    return "\n\n".join(results)


def load_config(config_path: str | None) -> dict:
    if not config_path:
        return {}
    if not os.path.isfile(config_path):
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    if tomllib is None:
        print(
            "Error: tomllib is unavailable. Ensure you're running Python 3.11+.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        # Support flat keys or nested under [llm]
        if "llm" in data and isinstance(data["llm"], dict):
            base = data.get("llm", {})
        else:
            base = data
        cfg = {}
        if isinstance(base.get("endpoint"), str):
            cfg["endpoint"] = base["endpoint"]
        if isinstance(base.get("model"), str):
            cfg["model"] = base["model"]
        if isinstance(base.get("api_key"), str):
            cfg["api_key"] = base["api_key"]
        return cfg
    except Exception as e:
        print(f"Error reading config file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Extract text from an image or PDF using a local or configured OpenAI-compatible API."
    )
    parser.add_argument("input_path", type=str, help="Path to the image or PDF file")
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help=f"Model name to use for text extraction (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--endpoint",
        "-e",
        type=str,
        default=None,
        help=f"OpenAI-compatible endpoint URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to a TOML config file with 'endpoint' and 'model' keys (optionally under [llm]).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path to write extracted text (optional, prints to stdout by default)",
    )
    args = parser.parse_args()

    # Load config and compute effective settings (CLI > config > defaults)
    config = load_config(args.config)
    endpoint = args.endpoint or config.get("endpoint") or DEFAULT_ENDPOINT
    model = args.model or config.get("model") or DEFAULT_MODEL
    # API key precedence: config > environment (keep CLI free of secrets)
    api_key = config.get("api_key") or os.environ.get("PDF2MARKDOWN_API_KEY") or os.environ.get("OPENAI_API_KEY")

    input_path = args.input_path

    # Validate input path
    if not os.path.isfile(input_path):
        print(f"Error: The file {input_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    ext = os.path.splitext(input_path)[1].lower().lstrip(".")

    try:
        if ext in IMAGE_EXTS:
            with open(input_path, "rb") as f:
                data = f.read()
            text = extract_markdown_from_image(endpoint, model, data, ext, api_key=api_key)
        elif ext == "pdf":
            text = process_pdf(input_path, endpoint, model, api_key=api_key)
        else:
            print(
                "Error: Unsupported file format. Please use jpg, jpeg, png, gif, bmp, webp, or pdf.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Output the extracted text
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as output_file:
                    output_file.write(text)
                print(f"Text extracted and saved to: {args.output}", file=sys.stderr)
            except IOError as e:
                print(f"Error writing to output file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(text)
    except requests.RequestException as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
