#!/usr/bin/env python3
"""CLI tool for converting between JSON, CSV, YAML, and TOML formats."""

import argparse
import csv
import json
import sys
from io import StringIO
from typing import Any

try:
    import tomllib
except ImportError:
    import toml as tomllib_mod
    tomllib = tomllib_mod

try:
    import tomli_w
    _to_toml = lambda data: tomli_w.dumps(data)
except ImportError:
    try:
        import toml as toml_write
        _to_toml = lambda data: toml_write.dumps(data)
    except ImportError:
        _to_toml = None

import yaml


def parse_json(data: str) -> Any:
    """Parse JSON string to Python object."""
    return json.loads(data)


def parse_csv(data: str) -> list[dict]:
    """Parse CSV string to list of dictionaries."""
    reader = csv.DictReader(StringIO(data))
    return [row for row in reader]


def parse_yaml(data: str) -> Any:
    """Parse YAML string to Python object."""
    return yaml.safe_load(data)


def parse_toml(data: str) -> Any:
    """Parse TOML string to Python object."""
    if hasattr(tomllib, 'loads'):
        return tomllib.loads(data)
    return tomllib.parse(data)


def to_json(data: Any, indent: int = 2) -> str:
    """Convert Python object to JSON string."""
    return json.dumps(data, indent=indent, ensure_ascii=False)


def to_csv(data: Any) -> str:
    """Convert Python object to CSV string."""
    if not isinstance(data, list) or not data:
        raise ValueError("CSV output requires a non-empty list of records")
    if not all(isinstance(row, dict) for row in data):
        raise ValueError("CSV output requires a list of dictionaries as records")
    
    fieldnames = list(data[0].keys())
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def to_yaml(data: Any) -> str:
    """Convert Python object to YAML string."""
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def to_toml(data: Any) -> str:
    """Convert Python object to TOML string."""
    if _to_toml is None:
        raise ImportError("TOML output requires 'toml' or 'tomli-w' package")
    return _to_toml(data)


PARSERS = {
    'json': parse_json,
    'csv': parse_csv,
    'yaml': parse_yaml,
    'toml': parse_toml,
}

WRITERS = {
    'json': to_json,
    'csv': to_csv,
    'yaml': to_yaml,
    'toml': to_toml,
}


def read_input(source: str | None) -> str:
    """Read input from file or STDIN."""
    if source is None:
        return sys.stdin.read()
    with open(source, 'r', encoding='utf-8') as f:
        return f.read()


def write_output(data: str, destination: str | None) -> None:
    """Write output to file or STDOUT."""
    if destination is None:
        print(data)
    else:
        with open(destination, 'w', encoding='utf-8') as f:
            f.write(data)


def validate_format(fmt: str) -> str:
    """Validate and normalize format string."""
    fmt_lower = fmt.lower()
    if fmt_lower not in PARSERS:
        raise ValueError(f"Unsupported format: {fmt}. Supported: {list(PARSERS.keys())}")
    return fmt_lower


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert between JSON, CSV, YAML, and TOML formats',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n  %(prog)s -i json -o yaml data.json\n  cat data.csv | %(prog)s -i csv -o json\n  %(prog)s -i toml -o csv input.toml output.csv'
    )
    
    parser.add_argument('-i', '--input-format', required=True, 
                        help='Input format (json, csv, yaml, toml)')
    parser.add_argument('-o', '--output-format', required=True,
                        help='Output format (json, csv, yaml, toml)')
    parser.add_argument('input_file', nargs='?',
                        help='Input file path (reads from STDIN if omitted)')
    parser.add_argument('output_file', nargs='?',
                        help='Output file path (writes to STDOUT if omitted)')
    parser.add_argument('--indent', type=int, default=2,
                        help='Indentation for JSON output (default: 2)')
    
    args = parser.parse_args()
    
    input_format = validate_format(args.input_format)
    output_format = validate_format(args.output_format)
    
    try:
        data = read_input(args.input_file)
        parsed = PARSERS[input_format](data)
        
        if output_format == 'json':
            result = to_json(parsed, indent=args.indent)
        else:
            result = WRITERS[output_format](parsed)
        
        write_output(result, args.output_file)
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except PermissionError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())