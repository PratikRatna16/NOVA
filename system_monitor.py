#!/usr/bin/env python3
"""QR Code Generator CLI Tool"""

import argparse
import sys
from pathlib import Path

import qrcode
from PIL import Image


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate QR codes from text input and save as PNG files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python qr_code_generator.py -t 'https://example.com' -o output.png"
    )
    parser.add_argument(
        "-t", "--text",
        required=True,
        help="Text or data to encode in the QR code"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output file path for the PNG image (e.g., output.png)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="QR Code Generator v1.0.0"
    )
    return parser.parse_args()


def validate_output_path(output_path):
    path = Path(output_path)
    if path.exists() and not path.is_file():
        raise ValueError(f"Output path '{output_path}' exists but is not a file")
    if path.suffix.lower() != ".png":
        raise ValueError("Output file must have .png extension")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise PermissionError(f"Cannot create directory: {path.parent}")
    return path


def generate_qr_code(text, error_correction=qrcode.constants.ERROR_CORRECT_M):
    qr = qrcode.QRCode(
        version=1,
        error_correction=error_correction,
        box_size=10,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")


def save_png_image(image, output_path):
    try:
        image.save(output_path, format="PNG")
    except PermissionError:
        raise PermissionError(f"Permission denied writing to '{output_path}'")
    except Exception as e:
        raise IOError(f"Failed to save image: {e}")


def main():
    args = parse_args()
    
    if not args.text.strip():
        print("Error: Input text cannot be empty", file=sys.stderr)
        sys.exit(1)
    
    try:
        output_path = validate_output_path(args.output)
        image = generate_qr_code(args.text)
        save_png_image(image, output_path)
        print(f"Successfully generated QR code: {output_path.resolve()}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()