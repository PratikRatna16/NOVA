#!/usr/bin/env python3
import argparse
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = 'portfolio.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stocks
                 (symbol TEXT PRIMARY KEY, quantity INTEGER, total_buy_cost REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, type TEXT, 
                  quantity INTEGER, price REAL, date TEXT)''')
    conn.commit()
    conn.close()

def validate_date(date_str: str) -> str:
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return date_str
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format")

def validate_positive(value: str, field: str) -> float:
    try:
        val = float(value)
        if val <= 0:
            raise ValueError(f"{field} must be positive")
        return val
    except ValueError as e:
        if "must be positive" not in str(e):
            raise ValueError(f"Invalid {field}")
        raise

def validate_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if not all(c.isalnum() for c in symbol) or len(symbol) < 1 or len(symbol) > 10:
        raise ValueError("Stock symbol must be alphanumeric, 1-10 characters")
    return symbol

def add_stock(symbol: str, quantity: str, price: str, date: str):
    symbol = validate_symbol(symbol)
    quantity = int(quantity)
    price = validate_positive(price, "price")
    validate_date(date)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT quantity, total_buy_cost FROM stocks WHERE symbol = ?', (symbol,))
    row = c.fetchone()
    
    if row:
        new_qty = row[0] + quantity
        new_cost = row[1] + quantity * price
        c.execute('UPDATE stocks SET quantity = ?, total_buy_cost = ? WHERE symbol = ?',
                  (new_qty, new_cost, symbol))
    else:
        c.execute('INSERT INTO stocks (symbol, quantity, total_buy_cost) VALUES (?, ?, ?)',
                  (symbol, quantity, quantity * price))
    
    c.execute('INSERT INTO transactions (symbol, type, quantity, price, date) VALUES (?, ?, ?, ?, ?)',
              (symbol, 'BUY', quantity, price, date))
    conn.commit()
    conn.close()
    logger.info(f"Added {quantity} shares of {symbol}")

def sell_stock(symbol: str, quantity: str, price: str, date: str):
    symbol = validate_symbol(symbol)
    quantity = int(quantity)
    price = validate_positive(price, "price")
    validate_date(date)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT quantity, total_buy_cost FROM stocks WHERE symbol = ?', (symbol,))
    row = c.fetchone()
    
    if not row or row[0] < quantity:
        conn.close()
        raise ValueError(f"Insufficient shares of {symbol}. Available: {row[0] if row else 0}")
    
    avg_buy = row[1] / row[0]
    c.execute('UPDATE stocks SET quantity = quantity - ?, total_buy_cost = total_buy_cost - ? WHERE symbol = ?',
              (quantity, quantity * avg_buy, symbol))
    c.execute('DELETE FROM stocks WHERE quantity = 0')
    c.execute('INSERT INTO transactions (symbol, type, quantity, price, date) VALUES (?, ?, ?, ?, ?)',
              (symbol, 'SELL', quantity, price, date))
    conn.commit()
    conn.close()
    logger.info(f"Sold {quantity} shares of {symbol}")

def remove_stock(symbol: str):
    symbol = validate_symbol(symbol)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM stocks WHERE symbol = ?', (symbol,))
    c.execute('DELETE FROM transactions WHERE symbol = ?', (symbol,))
    conn.commit()
    conn.close()
    logger.info(f"Removed stock {symbol}")

def view_portfolio():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT symbol, quantity, total_buy_cost FROM stocks')
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        print("Portfolio is empty")
        return
    
    print(f"{'Symbol':<10} {'Quantity':<10} {'Avg Buy':<12} {'Total Cost':<15}")
    print("-" * 47)
    total_cost = 0
    for row in rows:
        avg = row[2] / row[1] if row[1] > 0 else 0
        total_cost += row[2]
        print(f"{row[0]:<10} {row[1]:<10} ${avg:<11.2f} ${row[2]:<14.2f}")
    print("-" * 47)
    print(f"{'Total Investment:':<25} ${total_cost:.2f}")

def view_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT symbol, type, quantity, price, date FROM transactions ORDER BY date DESC')
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        print("No transactions found")
        return
    
    print(f"{'Date':<12} {'Symbol':<10} {'Type':<6} {'Qty':<8} {'Price':<10}")
    print("-" * 50)
    for row in rows:
        print(f"{row[4]:<12} {row[0]:<10} {row[1]:<6} {row[2]:<8} ${row[3]:<9.2f}")

def calculate_profit() -> float:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT SUM(CASE WHEN type = "BUY" THEN quantity * price ELSE 0 END) FROM transactions')
    total_buy = c.fetchone()[0] or 0
    c.execute('SELECT SUM(CASE WHEN type = "SELL" THEN quantity * price ELSE 0 END) FROM transactions')
    total_sell = c.fetchone()[0] or 0
    conn.close()
    return total_sell - total_buy

def main():
    parser = argparse.ArgumentParser(description='Stock Portfolio Tracker')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    buy_parser = subparsers.add_parser('buy', help='Record a buy transaction')
    buy_parser.add_argument('symbol', help='Stock symbol')
    buy_parser.add_argument('quantity', help='Number of shares')
    buy_parser.add_argument('price', help='Price per share')
    buy_parser.add_argument('date', help='Transaction date (YYYY-MM-DD)')
    
    sell_parser = subparsers.add_parser('sell', help='Record a sell transaction')
    sell_parser.add_argument('symbol', help='Stock symbol')
    sell_parser.add_argument('quantity', help='Number of shares')
    sell_parser.add_argument('price', help='Price per share')
    sell_parser.add_argument('date', help='Transaction date (YYYY-MM-DD)')
    
    remove_parser = subparsers.add_parser('remove', help='Remove a stock from portfolio')
    remove_parser.add_argument('symbol', help='Stock symbol')
    
    subparsers.add_parser('view', help='View portfolio summary')
    subparsers.add_parser('history', help='View transaction history')
    subparsers.add_parser('profit', help='Calculate overall profit/loss')
    
    args = parser.parse_args()
    
    commands = {
        'buy': lambda: add_stock(args.symbol, args.quantity, args.price, args.date),
        'sell': lambda: sell_stock(args.symbol, args.quantity, args.price, args.date),
        'remove': lambda: remove_stock(args.symbol),
        'view': view_portfolio,
        'history': view_history,
        'profit': lambda: print(f"Total Profit/Loss: ${calculate_profit():.2f}")
    }
    
    if args.command:
        try:
            commands[args.command]()
        except Exception as e:
            logger.error(str(e))
    else:
        parser.print_help()

if __name__ == '__main__':
    init_db()
    main()