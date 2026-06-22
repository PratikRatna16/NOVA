#!/usr/bin/env python3
"""Inventory Management CLI Tool - Single file implementation."""
import json
import argparse
import sys
from pathlib import Path
from typing import Optional

DEFAULT_INVENTORY_PATH = Path.home() / ".inventory.json"

def load_inventory(path: Path) -> list[dict]:
    """Load inventory from JSON file, return empty list if file doesn't exist."""
    if not path.exists():
        return []
    with open(path, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_inventory(path: Path, inventory: list[dict]) -> None:
    """Save inventory to JSON file."""
    with open(path, 'w') as f:
        json.dump(inventory, f, indent=2)

def find_item(inventory: list[dict], item_id: Optional[str] = None, name: Optional[str] = None) -> Optional[dict]:
    """Find item by id or name."""
    for item in inventory:
        if item_id and item.get('id') == item_id:
            return item
        if name and item.get('name', '').lower() == name.lower():
            return item
    return None

def find_items_by_name(inventory: list[dict], name: str) -> list[dict]:
    """Find items containing name (case-insensitive partial match)."""
    return [item for item in inventory if name.lower() in item.get('name', '').lower()]

def cmd_add(args, inventory: list[dict], path: Path) -> int:
    """Add a new item to inventory."""
    if find_item(inventory, item_id=args.id):
        print(f"Error: Item with id '{args.id}' already exists.", file=sys.stderr)
        return 1
    
    try:
        quantity = int(args.quantity)
        threshold = int(args.low_stock_threshold)
        if quantity < 0 or threshold < 0:
            raise ValueError("Quantity and threshold must be non-negative")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    item = {
        'id': args.id,
        'name': args.name,
        'description': args.description or '',
        'quantity': quantity,
        'low_stock_threshold': threshold
    }
    inventory.append(item)
    save_inventory(path, inventory)
    print(f"Added item: {args.id}")
    return 0

def cmd_remove(args, inventory: list[dict], path: Path) -> int:
    """Remove an item from inventory by id."""
    item = find_item(inventory, item_id=args.id)
    if not item:
        print(f"Error: Item with id '{args.id}' not found.", file=sys.stderr)
        return 1
    
    inventory.remove(item)
    save_inventory(path, inventory)
    print(f"Removed item: {args.id}")
    return 0

def cmd_update(args, inventory: list[dict], path: Path) -> int:
    """Update an existing item in inventory."""
    item = find_item(inventory, item_id=args.id)
    if not item:
        print(f"Error: Item with id '{args.id}' not found.", file=sys.stderr)
        return 1
    
    updates = {k: v for k, v in {
        'name': args.name,
        'description': args.description,
        'quantity': int(args.quantity) if args.quantity is not None else None,
        'low_stock_threshold': int(args.low_stock_threshold) if args.low_stock_threshold is not None else None
    }.items() if v is not None}
    
    if updates.get('quantity', item['quantity']) < 0:
        print("Error: Quantity must be non-negative", file=sys.stderr)
        return 1
    if updates.get('low_stock_threshold', item['low_stock_threshold']) < 0:
        print("Error: Low stock threshold must be non-negative", file=sys.stderr)
        return 1
    
    item.update(updates)
    save_inventory(path, inventory)
    print(f"Updated item: {args.id}")
    return 0

def cmd_search(args, inventory: list[dict], path: Path) -> int:
    """Search for items by id or name."""
    results = []
    if args.id:
        item = find_item(inventory, item_id=args.id)
        if item:
            results = [item]
    elif args.name:
        results = find_items_by_name(inventory, args.name)
    
    if not results:
        print("No items found.")
        return 0
    
    for item in results:
        alert = ""
        if item['quantity'] <= item['low_stock_threshold']:
            alert = " [LOW STOCK ALERT]"
        print(f"ID: {item['id']}, Name: {item['name']}, Qty: {item['quantity']}, Threshold: {item['low_stock_threshold']}{alert}")
    return 0

def cmd_list(args, inventory: list[dict], path: Path) -> int:
    """List all items in inventory."""
    if not inventory:
        print("Inventory is empty.")
        return 0
    
    low_stock_items = [item for item in inventory if item['quantity'] <= item['low_stock_threshold']]
    if low_stock_items and not args.no_alerts:
        print("Low stock alerts:")
        for item in low_stock_items:
            print(f"  - {item['id']}: {item['name']} (qty: {item['quantity']}, threshold: {item['low_stock_threshold']})")
        print()
    
    for item in inventory:
        alert = "*" if item['quantity'] <= item['low_stock_threshold'] else ""
        print(f"{alert}[{item['id']}] {item['name']} - Qty: {item['quantity']}/{item['low_stock_threshold']}")
    return 0

def cmd_check_alerts(args, inventory: list[dict], path: Path) -> int:
    """Check and display all low stock items."""
    low_stock_items = [item for item in inventory if item['quantity'] <= item['low_stock_threshold']]
    if not low_stock_items:
        print("No low stock alerts.")
        return 0
    
    print("Low stock alert items:")
    for item in low_stock_items:
        print(f"  - {item['id']}: {item['name']} (qty: {item['quantity']}, threshold: {item['low_stock_threshold']})")
    return 0

def main():
    parser = argparse.ArgumentParser(description='Inventory Management CLI Tool', 
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--inventory', '-i', type=Path, default=DEFAULT_INVENTORY_PATH,
                        help=f'Path to inventory JSON file (default: {DEFAULT_INVENTORY_PATH})')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Add command
    add_parser = subparsers.add_parser('add', help='Add a new item to inventory')
    add_parser.add_argument('id', help='Unique identifier for the item')
    add_parser.add_argument('name', help='Name of the item')
    add_parser.add_argument('--description', '-d', default='', help='Description of the item')
    add_parser.add_argument('--quantity', '-q', required=True, help='Initial quantity')
    add_parser.add_argument('--low-stock-threshold', '-t', required=True, help='Low stock threshold')
    
    # Remove command
    remove_parser = subparsers.add_parser('remove', help='Remove an item from inventory')
    remove_parser.add_argument('id', help='ID of the item to remove')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update an existing item')
    update_parser.add_argument('id', help='ID of the item to update')
    update_parser.add_argument('--name', help='New name for the item')
    update_parser.add_argument('--description', '-d', help='New description for the item')
    update_parser.add_argument('--quantity', '-q', type=int, help='New quantity')
    update_parser.add_argument('--low-stock-threshold', '-t', type=int, help='New low stock threshold')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search for items')
    search_group = search_parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument('--id', help='Search by item ID')
    search_group.add_argument('--name', help='Search by item name (partial match)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all items in inventory')
    list_parser.add_argument('--no-alerts', action='store_true', help='Suppress low stock alerts')
    
    # Check alerts command
    subparsers.add_parser('alerts', help='Check for low stock items')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    inventory = load_inventory(args.inventory)
    
    commands = {
        'add': cmd_add,
        'remove': cmd_remove,
        'update': cmd_update,
        'search': cmd_search,
        'list': cmd_list,
        'alerts': cmd_check_alerts
    }
    
    return commands[args.command](args, inventory, args.inventory)

if __name__ == '__main__':
    sys.exit(main())