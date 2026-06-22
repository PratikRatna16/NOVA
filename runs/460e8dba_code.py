#!/usr/bin/env python3
"""SSH Config Manager CLI Tool - Manage SSH configurations with ease."""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CONFIG = Path.home() / ".ssh" / "config.json"


def load_config(path: Path) -> list:
    """Load SSH configuration from JSON file, return empty list if not exists."""
    if not path.exists():
        return []
    with open(path, 'r') as f:
        return json.load(f)


def save_config(path: Path, configs: list) -> None:
    """Save SSH configuration to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(configs, f, indent=2)


def find_config(configs: list, term: str) -> tuple:
    """Find config by exact alias or keyword search. Returns (index, config) or (None, None)."""
    # Direct Title Lookup (exact match on alias)
    for i, cfg in enumerate(configs):
        if cfg.get('alias', '').lower() == term.lower():
            return i, cfg
    # Keyword Search (fallback to any field match)
    for i, cfg in enumerate(configs):
        if any(str(v).lower() == term.lower() for v in cfg.values()):
            return i, cfg
    return None, None


def validate_config(hostname: str, alias: str, port: int) -> str:
    """Validate configuration fields. Returns error message or None."""
    if not hostname:
        return "Missing required field: hostname"
    if not alias:
        return "Missing required field: alias"
    if not isinstance(port, int) or port < 1 or port > 65535:
        return "Invalid port number: must be between 1 and 65535"
    return None


def add_configs(path: Path, hostnames: list, **kwargs) -> bool:
    """Add new SSH configurations."""
    configs = load_config(path)
    success = True
    
    for hostname in hostnames:
        alias = kwargs.get('alias') or hostname.split('.')[0]
        port = kwargs.get('port', 22)
        username = kwargs.get('username', '')
        password = kwargs.get('password', '')
        
        _, existing = find_config(configs, alias)
        if existing:
            print(f"Error: Duplicate SSH configuration for alias '{alias}'")
            success = False
            continue
        
        error = validate_config(hostname, alias, port)
        if error:
            print(f"Error: {error}")
            success = False
            continue
        
        configs.append({
            "hostname": hostname,
            "alias": alias,
            "port": port,
            "username": username,
            "password": password
        })
        print(f"Added SSH configuration: alias='{alias}', hostname='{hostname}'")
    
    if success:
        save_config(path, configs)
    return success


def remove_configs(path: Path, aliases: list) -> bool:
    """Remove SSH configurations by alias."""
    configs = load_config(path)
    success = True
    
    for alias in aliases:
        index, _ = find_config(configs, alias)
        if index is None:
            print(f"Error: No configuration found with alias '{alias}'")
            success = False
            continue
        removed = configs.pop(index)
        print(f"Removed SSH configuration: alias='{removed['alias']}'")
    
    if success:
        save_config(path, configs)
    return success


def list_configs(path: Path, limit: int = None, keyword: str = None) -> bool:
    """List all SSH configurations with optional limit and keyword filter."""
    configs = load_config(path)
    
    if keyword:
        keyword = keyword.lower()
        configs = [c for c in configs if keyword in c.get('alias', '').lower() or keyword in c.get('hostname', '').lower()]
    
    if limit is not None:
        if limit < 0:
            print("Error: Limit must be non-negative")
            return False
        configs = configs[:limit]
    
    if not configs:
        print("No SSH configurations found.")
        return True
    
    for cfg in configs:
        print(f"Alias: {cfg.get('alias')}, Hostname: {cfg.get('hostname')}, Port: {cfg.get('port')}")
    return True


def edit_config(path: Path, alias: str, **kwargs) -> bool:
    """Edit an existing SSH configuration."""
    configs = load_config(path)
    index, cfg = find_config(configs, alias)
    
    if index is None:
        print(f"Error: No configuration found with alias '{alias}'")
        return False
    
    if kwargs.get('new_alias'):
        _, existing = find_config(configs, kwargs['new_alias'])
        if existing:
            print(f"Error: Duplicate SSH configuration for alias '{kwargs['new_alias']}'")
            return False
        cfg['alias'] = kwargs['new_alias']
    
    if kwargs.get('hostname'):
        cfg['hostname'] = kwargs['hostname']
    if kwargs.get('port'):
        cfg['port'] = kwargs['port']
    if kwargs.get('username') is not None:
        cfg['username'] = kwargs['username']
    if kwargs.get('password') is not None:
        cfg['password'] = kwargs['password']
    
    error = validate_config(cfg.get('hostname'), cfg.get('alias'), cfg.get('port'))
    if error:
        print(f"Error: {error}")
        return False
    
    configs[index] = cfg
    save_config(path, configs)
    print(f"Updated SSH configuration: alias='{alias}'")
    return True


def view_config(path: Path, alias: str) -> bool:
    """View details of an SSH configuration."""
    configs = load_config(path)
    _, cfg = find_config(configs, alias)
    
    if not cfg:
        print(f"Error: No configuration found with alias '{alias}'")
        return False
    
    for key, value in cfg.items():
        print(f"{key.capitalize()}: {value}")
    return True


def main():
    parser = argparse.ArgumentParser(description="SSH Config Manager CLI Tool")
    parser.add_argument('-f', '--file', type=Path, default=DEFAULT_CONFIG, help='Configuration file path')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new SSH configuration')
    add_parser.add_argument('hostname', nargs='+', help='Hostname(s) to add')
    add_parser.add_argument('-a', '--alias', help='Alias for SSH configuration')
    add_parser.add_argument('-p', '--port', type=int, default=22, help='SSH port (default: 22)')
    add_parser.add_argument('-u', '--username', help='SSH username')
    add_parser.add_argument('-w', '--password', help='SSH password')
    
    # Remove command
    rm_parser = subparsers.add_parser('remove', help='Remove an SSH configuration')
    rm_parser.add_argument('alias', nargs='+', help='Alias(es) to remove')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List SSH configurations')
    list_parser.add_argument('-l', '--limit', type=int, help='Limit number of results')
    list_parser.add_argument('keyword', nargs='*', help='Keyword to filter results')
    
    # Edit command
    edit_parser = subparsers.add_parser('edit', help='Edit an SSH configuration')
    edit_parser.add_argument('alias', help='Alias to edit')
    edit_parser.add_argument('-a', '--alias', dest='new_alias', help='New alias (use -a, not -h)')
    edit_parser.add_argument('--hostname', help='New hostname')
    edit_parser.add_argument('-p', '--port', type=int, help='New port')
    edit_parser.add_argument('-u', '--username', help='New username')
    edit_parser.add_argument('-w', '--password', help='New password')
    
    # View command
    view_parser = subparsers.add_parser('view', help='View SSH configuration details')
    view_parser.add_argument('alias', help='Alias to view')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    actions = {
        'add': lambda: add_configs(args.file, args.hostname, alias=args.alias, port=args.port, 
                                    username=args.username, password=args.password),
        'remove': lambda: remove_configs(args.file, args.alias),
        'list': lambda: list_configs(args.file, args.limit, ' '.join(args.keyword) if args.keyword else None),
        'edit': lambda: edit_config(args.file, args.alias, new_alias=args.new_alias, hostname=args.hostname,
                                     port=args.port, username=args.username, password=args.password),
        'view': lambda: view_config(args.file, args.alias),
    }
    
    actions[args.command]()


if __name__ == '__main__':
    main()