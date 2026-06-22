#!/usr/bin/env python3
"""CLI SSH Connection Manager"""

import argparse
import json
import os
import sys
from typing import Optional, Dict, List, Any
import paramiko
import socket

CONFIG_FILE = "connections.json"
SSH_TIMEOUT = 10
RETRY_COUNT = 3

def load_connections() -> List[Dict[str, Any]]:
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []

def save_connections(connections: List[Dict[str, Any]]) -> bool:
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(connections, f, indent=2)
        return True
    except IOError as e:
        print(f"Error saving configuration: {e}", file=sys.stderr)
        return False

def validate_params(port: int, private_key: Optional[str]) -> bool:
    if not (1 <= port <= 65535):
        print(f"Error: Invalid port number {port}", file=sys.stderr)
        return False
    if private_key and not os.path.exists(private_key):
        print(f"Error: Private key file not found: {private_key}", file=sys.stderr)
        return False
    return True

def connect_ssh(hostname: str, port: int, username: Optional[str], private_key: Optional[str]) -> bool:
    if not hostname:
        print("Error: Hostname is required", file=sys.stderr)
        return False
    if not validate_params(port, private_key):
        return False
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    for attempt in range(RETRY_COUNT):
        try:
            client.connect(
                hostname, port=port, username=username,
                key_filename=private_key if private_key else None,
                timeout=SSH_TIMEOUT, allow_agent=False
            )
            print(f"Successfully connected to {hostname}")
            client.close()
            return True
        except paramiko.AuthenticationException:
            print(f"Error: Authentication failed for {hostname}", file=sys.stderr)
            return False
        except (paramiko.SSHException, socket.timeout, socket.error, OSError) as e:
            print(f"Connection error (attempt {attempt + 1}/{RETRY_COUNT}): {e}", file=sys.stderr)
    print(f"Error: Failed to connect to {hostname} after {RETRY_COUNT} attempts", file=sys.stderr)
    return False

def add_connection(hostname: str, port: int, username: Optional[str], private_key: Optional[str]) -> bool:
    if not hostname:
        print("Error: Hostname is required", file=sys.stderr)
        return False
    if not validate_params(port, private_key):
        return False
    
    connections = load_connections()
    if any(c['hostname'] == hostname for c in connections):
        print(f"Error: Connection to {hostname} already exists", file=sys.stderr)
        return False
    
    connection = {
        'hostname': hostname, 'port': port,
        'username': username or '', 'private_key': private_key or ''
    }
    connections.append(connection)
    if save_connections(connections):
        print(f"Added connection to {hostname}")
        return True
    return False

def remove_connection(hostname: str) -> bool:
    if not hostname:
        print("Error: Hostname is required", file=sys.stderr)
        return False
    
    connections = load_connections()
    initial_count = len(connections)
    connections = [c for c in connections if c['hostname'] != hostname]
    
    if len(connections) == initial_count:
        print(f"Error: No connection found for {hostname}", file=sys.stderr)
        return False
    if save_connections(connections):
        print(f"Removed connection to {hostname}")
        return True
    return False

def list_connections() -> bool:
    connections = load_connections()
    if not connections:
        print("No saved connections")
        return True
    
    print("Saved SSH connections:")
    for conn in connections:
        parts = []
        if conn.get('username'):
            parts.append(f"{conn['username']}@{conn['hostname']}")
        else:
            parts.append(conn['hostname'])
        if conn.get('port', 22) != 22:
            parts[-1] = f"{parts[-1]}:{conn['port']}"
        if conn.get('private_key'):
            parts.append(f"(key: {conn['private_key']})")
        print(f"  {' '.join(parts)}")
    return True

def main():
    parser = argparse.ArgumentParser(description='CLI SSH Connection Manager', prog='ssh-manager')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    for cmd in ['connect', 'add']:
        p = subparsers.add_parser(cmd, help=f'{cmd.capitalize()} SSH connection')
        p.add_argument('hostname', help='Hostname or IP address')
        p.add_argument('-p', '--port', type=int, default=22, help='SSH port (default: 22)')
        p.add_argument('-u', '--username', help='Username for SSH connection')
        p.add_argument('-k', '--private-key', help='Path to private key file')
    
    remove_parser = subparsers.add_parser('remove', help='Remove SSH connection')
    remove_parser.add_argument('hostname', help='Hostname or IP address')
    subparsers.add_parser('list', help='List all SSH connections')
    
    args = parser.parse_args()
    commands = {
        'connect': lambda: connect_ssh(args.hostname, args.port, args.username, args.private_key),
        'add': lambda: add_connection(args.hostname, args.port, args.username, args.private_key),
        'remove': lambda: remove_connection(args.hostname),
        'list': list_connections
    }
    success = commands.get(args.command, lambda: False)()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()