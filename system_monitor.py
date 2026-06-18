#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

MORSE_CODE_DICT = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---',
    '3': '...--', '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.', ' ': '/', '.': '.-.-.-', ',': '--..--',
    '?': '..--..', "'": '.----.', '!': '-.-.--', '/': '-..-.', '(': '-.--.',
    ')': '-.--.-', '&': '.-...', ':': '---...', ';': '-.-.-.', '=': '-...-',
    '+': '.-.-.', '-': '-....-', '_': '..--.-', '"': '.-..-.', '$': '...-..-',
    '@': '.--.'
}

TEXT_FROM_MORSE = {v: k for k, v in MORSE_CODE_DICT.items() if k != ' '}
TEXT_FROM_MORSE['/'] = ' '

def text_to_morse(text: str) -> str:
    """Convert text to Morse code with validation."""
    if not text:
        return ""
    invalid = [c for c in text.upper() if c not in MORSE_CODE_DICT]
    if invalid:
        raise ValueError(f"Invalid characters: {set(invalid)}")
    return ' '.join(MORSE_CODE_DICT[c.upper()] for c in text)

def morse_to_text(morse: str) -> str:
    """Convert Morse code to text with validation."""
    if not morse:
        return ""
    tokens = morse.strip().split()
    invalid = [t for t in tokens if t not in TEXT_FROM_MORSE]
    if invalid:
        raise ValueError(f"Invalid Morse sequences: {set(invalid)}")
    return ''.join(TEXT_FROM_MORSE[t] for t in tokens)

def detect_input_type(text: str) -> str:
    """Determine if input is Morse code or plain text."""
    morse_chars = set('.-_/\t\n ')
    return 'morse' if all(c in morse_chars for c in text) else 'text'

def process_input(input_path: str | None, input_data: str | None) -> str:
    """Handle input from file or string with validation."""
    if input_path:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        data = path.read_text().strip()
        if not data:
            raise ValueError("Input file is empty")
        return data
    if input_data is None:
        raise ValueError("No input provided (use --input-data or --input-file)")
    return input_data

def handle_output(output_path: str | None, output_data: str) -> None:
    """Handle output to file or stdout."""
    if output_path:
        Path(output_path).write_text(output_data + '\n')
    else:
        print(output_data)

def main():
    parser = argparse.ArgumentParser(
        description="Morse Code Converter CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert text/Morse code')
    convert_parser.add_argument('--input-data', '-i', help='Input string')
    convert_parser.add_argument('--input-file', '-f', help='Input file path')
    convert_parser.add_argument('--output-file', '-o', help='Output file path')
    convert_parser.add_argument('--mode', '-m', choices=['text', 'morse', 'auto'],
                                default='auto', help='Conversion mode (default: auto-detect)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == 'convert':
        try:
            input_text = process_input(args.input_file, args.input_data)
            
            mode = detect_input_type(input_text) if args.mode == 'auto' else args.mode
            
            conversion_map = {
                'text': lambda x: text_to_morse(x),
                'morse': lambda x: morse_to_text(x)
            }
            
            result = conversion_map[mode](input_text)
            handle_output(args.output_file, result)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()