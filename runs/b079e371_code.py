#!/usr/bin/env python3
"""SSH Config Manager CLI Tool - Manage SSH config entries with ease."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

DEFAULT_SSH_CONFIG = "~/.ssh/config"

def validate_port(port_str: str | int) -> int:
    try:
        port = int(port_str)
        if not 1 <= port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {port}")
        return port
    except ValueError as e:
        raise ValueError(f"Invalid port number: {port_str}") from e

def validate_path(path_str: str) -> Path:
    path = Path(os.path.expanduser(path_str))
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return path

def infer_format(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return "json" if ext == ".json" else "yaml" if ext in (".yaml", ".yml") else "ssh"

def read_ssh_config(filepath: str) -> list[dict]:
    path = Path(os.path.expanduser(filepath))
    if not path.exists():
        return []
    content = path.read_text()
    entries, current = [], {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("Host "):
            if current:
                entries.append(current)
            current = {"host": line.split(None, 1)[1]}
        elif line and current and " " in line:
            key, _, value = line.partition(" ")
            current[key.lower()] = value.strip().split()[0] if key.lower() == "port" else value.strip()
    if current:
        entries.append(current)
    return entries

def write_ssh_config(filepath: str, entries: list[dict]) -> None:
    path = Path(os.path.expanduser(filepath))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for entry in entries:
        if "host" not in entry:
            continue
        lines.append(f"Host {entry['host']}")
        mapping = {"hostname": "HostName", "port": "Port", "user": "User", "identityfile": "IdentityFile"}
        for key, label in mapping.items():
            if key in entry:
                lines.append(f"    {label} {entry[key]}")
        lines.append("")
    path.write_text("\n".join(lines))

def read_json_config(filepath: str) -> list[dict]:
    path = Path(os.path.expanduser(filepath))
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else []

def write_json_config(filepath: str, entries: list[dict]) -> None:
    path = Path(os.path.expanduser(filepath))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))

def read_yaml_config(filepath: str) -> list[dict]:
    if yaml is None:
        raise ImportError("PyYAML is required for YAML config files")
    path = Path(os.path.expanduser(filepath))
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, list) else []

def write_yaml_config(filepath: str, entries: list[dict]) -> None:
    if yaml is None:
        raise ImportError("PyYAML is required for YAML config files")
    path = Path(os.path.expanduser(filepath))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(entries, default_flow_style=False))

def load_config(filepath: str, fmt: str) -> list[dict]:
    loaders = {"ssh": read_ssh_config, "json": read_json_config, "yaml": read_yaml_config}
    return loaders[fmt](filepath)

def save_config(filepath: str, entries: list[dict], fmt: str) -> None:
    savers = {"ssh": write_ssh_config, "json": write_json_config, "yaml": write_yaml_config}
    savers[fmt](filepath, entries)

def find_entry(entries: list[dict], host: str) -> dict | None:
    return next((e for e in entries if e.get("host") == host), None)

def cmd_add(args: argparse.Namespace) -> None:
    fmt = infer_format(args.file)
    entries = load_config(args.file, fmt)
    entry = {"host": args.hostname, "hostname": args.hostname, "port": str(args.port), "user": args.username}
    if args.private_key:
        entry["identityfile"] = args.private_key
    existing = find_entry(entries, args.hostname)
    if existing:
        entries.remove(existing)
    entries.append(entry)
    save_config(args.file, entries, fmt)
    print(f"Added SSH config entry for {args.hostname}")

def cmd_remove(args: argparse.Namespace) -> None:
    fmt = infer_format(args.file)
    entries = load_config(args.file, fmt)
    entry = find_entry(entries, args.hostname)
    if not entry:
        print(f"No SSH config entry found for {args.hostname}")
        sys.exit(1)
    entries.remove(entry)
    save_config(args.file, entries, fmt)
    print(f"Removed SSH config entry for {args.hostname}")

def cmd_connect(args: argparse.Namespace) -> None:
    fmt = infer_format(args.file)
    entries = load_config(args.file, fmt)
    entry = find_entry(entries, args.hostname)
    if not entry:
        print(f"No SSH config entry found for {args.hostname}")
        sys.exit(1)
    cmd = ["ssh"]
    port = args.port if args.port != 22 else validate_port(entry.get("port", 22))
    if port != 22:
        cmd.extend(["-p", str(port)])
    if privkey := args.private_key or entry.get("identityfile"):
        cmd.extend(["-i", str(privkey)])
    target = entry.get("hostname", args.hostname)
    user = args.username or entry.get("user")
    cmd.append(f"{user}@{target}" if user else target)
    print(f"Connecting to {cmd[-1]}...")
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        print("SSH command not found. Please ensure OpenSSH is installed.")
        sys.exit(1)

def cmd_list(args: argparse.Namespace) -> None:
    fmt = infer_format(args.file)
    entries = load_config(args.file, fmt)
    if not entries:
        print("No SSH config entries found.")
        return
    for entry in entries:
        host = entry.get("host", "unknown")
        hostname = entry.get("hostname", entry.get("host", "unknown"))
        port = entry.get("port", "22")
        user = entry.get("user", "current")
        print(f"Host: {host} -> {hostname}:{port} (user: {user})")

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SSH Config Manager CLI Tool")
    subparsers = p.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add SSH config entry")
    add_parser.add_argument("--hostname", "-n", required=True, help="Hostname or IP")
    add_parser.add_argument("-p", "--port", type=int, default=22, help="Port number")
    add_parser.add_argument("-u", "--username", required=True, help="Username")
    add_parser.add_argument("-k", "--private-key", help="Private key file")
    add_parser.add_argument("-f", "--file", default=DEFAULT_SSH_CONFIG, help="Config file path")
    add_parser.set_defaults(func=cmd_add)

    remove_parser = subparsers.add_parser("remove", help="Remove SSH config entry")
    remove_parser.add_argument("--hostname", "-n", required=True, help="Hostname or IP")
    remove_parser.add_argument("-f", "--file", default=DEFAULT_SSH_CONFIG, help="Config file path")
    remove_parser.set_defaults(func=cmd_remove)

    connect_parser = subparsers.add_parser("connect", help="Connect via SSH")
    connect_parser.add_argument("--hostname", "-n", required=True, help="Hostname or IP")
    connect_parser.add_argument("-p", "--port", type=int, default=22, help="Port number")
    connect_parser.add_argument("-u", "--username", help="Username override")
    connect_parser.add_argument("-k", "--private-key", help="Private key file override")
    connect_parser.add_argument("-f", "--file", default=DEFAULT_SSH_CONFIG, help="Config file path")
    connect_parser.set_defaults(func=cmd_connect)

    list_parser = subparsers.add_parser("list", help="List SSH config entries")
    list_parser.add_argument("-f", "--file", default=DEFAULT_SSH_CONFIG, help="Config file path")
    list_parser.set_defaults(func=cmd_list)

    return p

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "add":
        if args.private_key:
            validate_path(args.private_key)
        args.port = validate_port(args.port)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, ImportError) as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()