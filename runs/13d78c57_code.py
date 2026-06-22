#!/usr/bin/env python3
"""CLI tool for batch renaming files using regex patterns."""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from queue import Queue


def parse_args():
    parser = argparse.ArgumentParser(description="Batch rename files using regex patterns")
    parser.add_argument("directory", help="Directory containing files to rename")
    parser.add_argument("pattern", help="Regex pattern to match")
    parser.add_argument("replacement", help="Replacement string")
    parser.add_argument("-r", "--recursive", action="store_true", help="Process subdirectories")
    parser.add_argument("-d", "--dry-run", action="store_true", help="Preview changes without renaming")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print detailed information")
    parser.add_argument("-c", "--case-sensitive", action="store_true", help="Case-sensitive matching")
    parser.add_argument("--version", action="version", version="rename-tool 1.0.0")
    return parser.parse_args()


def collect_files(directory, recursive):
    dir_path = Path(directory)
    if not dir_path.exists():
        raise ValueError(f"Directory does not exist: {directory}")
    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: {directory}")
    
    pattern = dir_path.rglob if recursive else dir_path.glob
    return [f for f in pattern("*") if f.is_file()]


def validate_pattern(pattern, case_sensitive):
    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        re.compile(pattern, flags)
        return True
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")


def resolve_conflict(new_path, dry_run, verbose):
    if not new_path.exists():
        return True
    
    if dry_run or not verbose:
        print(f"Conflict: {new_path.name} already exists")
        return False
    
    response = input(f"File '{new_path}' exists. Overwrite? (y/n): ").strip().lower()
    return response == "y"


def log_rename(original, renamed, log_file):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp}|{original}|{renamed}\n"
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text((log_path.read_text() if log_path.exists() else "") + log_entry, encoding="utf-8")


def rename_files(files, pattern, replacement, recursive, dry_run, verbose, case_sensitive):
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = re.compile(pattern, flags)
    queue = Queue()
    renamed_count = 0
    
    for file_path in files:
        stem = file_path.stem
        suffix = file_path.suffix
        new_stem = compiled.sub(replacement, stem)
        
        if stem == new_stem:
            continue
        
        queue.put((file_path, file_path.parent, stem, new_stem, suffix))
    
    while not queue.empty():
        original, parent, stem, new_stem, suffix = queue.get()
        new_path = parent / f"{new_stem}{suffix}"
        
        if not resolve_conflict(new_path, dry_run, verbose):
            continue
        
        if dry_run or verbose:
            print(f"{original.name} -> {new_path.name}")
        
        if not dry_run:
            try:
                original.rename(new_path)
                renamed_count += 1
                log_rename(original.name, new_path.name, ".rename_log")
            except OSError as e:
                print(f"Error renaming {original}: {e}", file=sys.stderr)
    
    return renamed_count


def main():
    args = parse_args()
    validate_pattern(args.pattern, args.case_sensitive)
    
    try:
        files = collect_files(args.directory, args.recursive)
        count = rename_files(files, args.pattern, args.replacement, args.recursive, 
                           args.dry_run, args.verbose, args.case_sensitive)
        if args.verbose:
            print(f"Renamed {count} files")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()