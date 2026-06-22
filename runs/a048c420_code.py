#!/usr/bin/env python3
"""CLI Regex Batch File Renamer - A tool for batch renaming files using regex patterns."""

import argparse
import os
import re
import sys
from pathlib import Path


def validate_regex(pattern: str) -> bool:
    """Validate that the provided string is a valid regex pattern."""
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def get_files(directory: Path, recursive: bool) -> list[Path]:
    """Get list of files from directory, recursively if specified."""
    if recursive:
        return [f for f in directory.rglob("*") if f.is_file()]
    return [f for f in directory.iterdir() if f.is_file()]


def rename_file(file_path: Path, pattern: str, replacement: str, dry_run: bool, verbose: bool) -> bool:
    """Rename a single file based on regex pattern. Returns True if renamed."""
    stem = file_path.stem
    suffix = file_path.suffix
    
    new_stem = re.sub(pattern, replacement, stem)
    
    if new_stem == stem:
        return False
    
    new_path = file_path.with_name(f"{new_stem}{suffix}")
    
    if dry_run or verbose:
        print(f"{'[DRY RUN] ' if dry_run else ''}{file_path.name} -> {new_stem}{suffix}")
    
    if not dry_run:
        try:
            file_path.rename(new_path)
        except OSError as e:
            print(f"Error renaming {file_path}: {e}", file=sys.stderr)
            return False
    
    return True


def main():
    parser = argparse.ArgumentParser(description="CLI Regex Batch File Renamer")
    parser.add_argument("pattern", help="Regex pattern to match against filenames")
    parser.add_argument("replacement", nargs="?", default="", help="Replacement string (default: empty string)")
    parser.add_argument("directory", nargs="?", default=".", help="Directory path (default: current directory)")
    parser.add_argument("-r", "--recursive", action="store_true", help="Enable recursive renaming")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Simulate renaming without changes")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    if not validate_regex(args.pattern):
        print(f"Error: Invalid regex pattern '{args.pattern}'", file=sys.stderr)
        sys.exit(1)
    
    directory = Path(args.directory).resolve()
    
    if not directory.exists():
        print(f"Error: Directory '{args.directory}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    if not directory.is_dir():
        print(f"Error: '{args.directory}' is not a directory", file=sys.stderr)
        sys.exit(1)
    
    if args.verbose and not args.dry_run:
        print(f"Processing files in: {directory}")
    
    files = get_files(directory, args.recursive)
    
    if not files:
        print("No files found to process.", file=sys.stderr)
        return
    
    renamed_count = sum(
        1 for f in files 
        if rename_file(f, args.pattern, args.replacement, args.dry_run, args.verbose)
    )
    
    if args.verbose:
        print(f"\nProcessed {len(files)} files, {renamed_count} {'would be ' if args.dry_run else ''}renamed.")


if __name__ == "__main__":
    main()