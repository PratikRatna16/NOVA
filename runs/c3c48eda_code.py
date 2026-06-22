#!/usr/bin/env python3
import argparse
import os
import re
import sys
import paramiko
from pathlib import Path

SSH_CONFIG_PATH = Path.home() / ".ssh" / "config"

def parse_config(content):
    """Parse SSH config file into list of entries (host -> config dict)."""
    entries = {}
    current_host = None
    current_config = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.lower().startswith("host "):
            if current_host:
                entries[current_host] = current_config
            host_tokens = stripped.split()[1:]
            for token in host_tokens:
                entries[token] = {}
            current_host = host_tokens[-1] if host_tokens else None
            current_config = {}
        elif current_host and "=" in stripped:
            key, value = stripped.split("=", 1)
            current_config[key.strip().lower()] = value.strip()
    if current_host:
        entries[current_host] = current_config
    return entries

def format_entry(host, config):
    """Format config entry as SSH config string."""
    lines = [f"Host {host}", f"\tHostName {config.get('hostname', host)}",
             f"\tUser {config['user']}", f"\tPort {config.get('port', 22)}"]
    if identity := config.get('identityfile'):
        lines.append(f"\tIdentityFile {identity}")
    return "\n".join(lines) + "\n"

def validate_host(host):
    if not host or not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$', host):
        raise ValueError("Invalid host name")
    return host

def validate_username(username):
    if not username or not re.match(r'^[a-zA-Z0-9_-]+$', username):
        raise ValueError("Invalid username")
    return username

def validate_port(port):
    port = int(port)
    if not (1 <= port <= 65535):
        raise ValueError("Port must be between 1 and 65535")
    return port

def validate_private_key(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise ValueError(f"Private key file not found: {path}")
    return path

def add_entry(args):
    SSH_CONFIG_PATH.parent.mkdir(mode=0o700, exist_ok=True)
    content = SSH_CONFIG_PATH.read_text() if SSH_CONFIG_PATH.exists() else ""
    entries = parse_config(content)
    
    host = validate_host(args.host)
    username = validate_username(args.username)
    port = validate_port(args.port) if args.port else 22
    private_key = validate_private_key(args.private_key) if args.private_key else None
    
    if host in entries:
        print(f"Warning: Host '{host}' already exists. Overwriting.")
    
    new_entry = {"user": username, "port": port}
    if private_key:
        new_entry["identityfile"] = private_key
    
    entries[host] = new_entry
    updated_content = "".join(format_entry(h, c) for h, c in entries.items())
    SSH_CONFIG_PATH.write_text(updated_content)
    print(f"Added SSH config entry for host: {host}")

def remove_entry(args):
    if not SSH_CONFIG_PATH.exists():
        raise FileNotFoundError("SSH config file not found")
    
    host = validate_host(args.host)
    content = SSH_CONFIG_PATH.read_text()
    entries = parse_config(content)
    
    if host not in entries:
        raise ValueError(f"Host '{host}' not found in config file")
    
    del entries[host]
    
    # Rebuild config preserving non-entry lines
    lines = content.splitlines()
    in_target_entry = False
    write_lines = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith(f"host {host}") or stripped.startswith(f"host * {host}"):
            in_target_entry = True
            continue
        if in_target_entry and (stripped.startswith("\t") or not stripped):
            continue
        if in_target_entry and stripped:
            in_target_entry = False
        if not in_target_entry:
            write_lines.append(line)
    
    SSH_CONFIG_PATH.write_text("\n".join(write_lines) + "\n")
    print(f"Removed SSH config entry for host: {host}")

def connect_ssh(args):
    host = validate_host(args.host)
    
    if not SSH_CONFIG_PATH.exists():
        raise FileNotFoundError("SSH config file not found")
    
    content = SSH_CONFIG_PATH.read_text()
    entries = parse_config(content)
    
    if host not in entries:
        raise ValueError(f"Host '{host}' not found in config file")
    
    config = entries[host]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        pkey = None
        if identity_file := config.get('identityfile'):
            key_path = os.path.expanduser(identity_file)
            if key_path.endswith('.pub'):
                raise ValueError("Cannot use public key for authentication")
            pkey = paramiko.RSAKey.from_private_key_file(key_path)
        
        client.connect(
            hostname=config.get('hostname', host),
            username=config['user'],
            port=int(config.get('port', 22)),
            pkey=pkey,
            look_for_keys=False,
            allow_agent=False
        )
        print(f"Connected to {host}. Interactive session not supported in this mode.")
        client.close()
    except paramiko.ssh_exception.AuthenticationException:
        raise ValueError("Authentication failed. Check credentials and key permissions.")
    except paramiko.ssh_exception.NoValidConnectionsError:
        raise ConnectionError(f"Cannot connect to {host}. Connection refused.")

def main():
    parser = argparse.ArgumentParser(description="SSH Config Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Add SSH config entry")
    add_parser.add_argument("--host", required=True, help="Hostname or IP address")
    add_parser.add_argument("--username", required=True, help="Username")
    add_parser.add_argument("--port", type=int, help="Port number (default: 22)")
    add_parser.add_argument("--private-key", help="Path to private key file")
    
    # Remove command
    remove_parser = subparsers.add_parser("remove", help="Remove SSH config entry")
    remove_parser.add_argument("--host", required=True, help="Host to remove")
    
    # Connect command
    connect_parser = subparsers.add_parser("connect", help="Connect via SSH config entry")
    connect_parser.add_argument("--host", required=True, help="Host to connect to")
    
    args = parser.parse_args()
    
    commands = {"add": add_entry, "remove": remove_entry, "connect": connect_ssh}
    
    try:
        commands[args.command](args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()