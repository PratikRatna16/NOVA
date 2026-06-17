#!/usr/bin/env python3
"""Budget Tracker CLI with SQLite storage and secure password hashing."""

import argparse
import csv
import getpass
import hashlib
import os
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("BUDGET_DB", Path.home() / ".budget_tracker.db"))
SESSION_PATH = Path(os.environ.get("BUDGET_SESSION", Path.home() / ".budget_tracker.session"))


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE RESTRICT
        );
        """
    )
    conn.commit()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return digest.hex(), salt


def get_current_user(conn: sqlite3.Connection) -> sqlite3.Row | None:
    if not SESSION_PATH.exists():
        return None
    try:
        user_id = int(SESSION_PATH.read_text().strip())
    except ValueError:
        return None
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def require_user(conn: sqlite3.Connection) -> sqlite3.Row:
    user = get_current_user(conn)
    if not user:
        raise SystemExit("Not logged in. Run: python budget_tracker.py auth login")
    return user


def prompt_password(prompt: str = "Password: ") -> str:
    password = getpass.getpass(prompt)
    if not password:
        raise SystemExit("Password cannot be empty.")
    return password


def parse_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise SystemExit(f"Invalid date '{value}'. Use YYYY-MM-DD.")


def parse_amount(value: float) -> float:
    if value <= 0:
        raise SystemExit("Amount must be greater than zero.")
    return round(value, 2)


def get_category(conn: sqlite3.Connection, user_id: int, identifier: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM categories WHERE (id = ? OR name = ?) AND user_id = ?",
        (identifier, identifier, user_id),
    ).fetchone()
    if not row:
        raise SystemExit(f"Category not found: {identifier}")
    return row


def get_expense(conn: sqlite3.Connection, user_id: int, expense_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
    ).fetchone()
    if not row:
        raise SystemExit(f"Expense not found: {expense_id}")
    return row


def cmd_auth_register(args: argparse.Namespace) -> None:
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (args.username,)).fetchone():
            raise SystemExit(f"Username already exists: {args.username}")
        password = args.password or prompt_password("New password: ")
        password_hash, salt = hash_password(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (args.username, password_hash, salt),
        )
        conn.commit()
        print(f"User '{args.username}' created.")


def cmd_auth_login(args: argparse.Namespace) -> None:
    with connect() as conn:
        username = args.username or input("Username: ").strip()
        password = args.password or prompt_password()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            raise SystemExit("Invalid username or password.")
        password_hash, _ = hash_password(password, user["salt"])
        if not secrets.compare_digest(password_hash, user["password_hash"]):
            raise SystemExit("Invalid username or password.")
        SESSION_PATH.write_text(str(user["id"]))
        SESSION_PATH.chmod(0o600)
        print(f"Logged in as {username}.")


def cmd_auth_logout(_: argparse.Namespace) -> None:
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()
    print("Logged out.")


def cmd_auth_whoami(_: argparse.Namespace) -> None:
    with connect() as conn:
        user = get_current_user(conn)
        print(user["username"] if user else "Not logged in")


def cmd_category_create(args: argparse.Namespace) -> None:
    name = args.name.strip()
    if not name:
        raise SystemExit("Category name cannot be empty.")
    with connect() as conn:
        user = require_user(conn)
        try:
            conn.execute(
                "INSERT INTO categories (name, user_id) VALUES (?, ?)",
                (name, user["id"]),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise SystemExit(f"Category already exists: {name}")
        print(f"Category created: {name}")


def cmd_category_list(_: argparse.Namespace) -> None:
    with connect() as conn:
        user = require_user(conn)
        rows = conn.execute(
            "SELECT id, name FROM categories WHERE user_id = ? ORDER BY name", (user["id"],)
        ).fetchall()
        if not rows:
            print("No categories.")
            return
        print("\n".join(f"{r['id']}. {r['name']}" for r in rows))


def cmd_category_delete(args: argparse.Namespace) -> None:
    with connect() as conn:
        user = require_user(conn)
        category = get_category(conn, user["id"], args.identifier)
        count = conn.execute("SELECT COUNT(*) FROM expenses WHERE category_id = ?", (category["id"],)).fetchone()[0]
        if count:
            raise SystemExit("Cannot delete category with expenses. Delete or move those expenses first.")
        conn.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (category["id"], user["id"]))
        conn.commit()
        print(f"Category deleted: {category['name']}")


def cmd_category_edit(args: argparse.Namespace) -> None:
    new_name = args.name.strip()
    if not new_name:
        raise SystemExit("Category name cannot be empty.")
    with connect() as conn:
        user = require_user(conn)
        category = get_category(conn, user["id"], args.identifier)
        try:
            conn.execute(
                "UPDATE categories SET name = ? WHERE id = ? AND user_id = ?",
                (new_name, category["id"], user["id"]),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise SystemExit(f"Category already exists: {new_name}")
        print(f"Category renamed to: {new_name}")


def cmd_expense_add(args: argparse.Namespace) -> None:
    date = parse_date(args.date)
    amount = parse_amount(args.amount)
    description = (args.description or "").strip()
    with connect() as conn:
        user = require_user(conn)
        category = get_category(conn, user["id"], args.category)
        conn.execute(
            "INSERT INTO expenses (user_id, category_id, date, amount, description) VALUES (?, ?, ?, ?, ?)",
            (user["id"], category["id"], date, amount, description),
        )
        conn.commit()
        print("Expense added.")


def cmd_expense_list(_: argparse.Namespace) -> None:
    with connect() as conn:
        user = require_user(conn)
        rows = conn.execute(
            """
            SELECT e.id, e.date, c.name AS category, e.amount, e.description
            FROM expenses e JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = ?
            ORDER BY e.date DESC, e.id DESC
            """,
            (user["id"],),
        ).fetchall()
        if not rows:
            print("No expenses.")
            return
        print(f"{'ID':<5} {'Date':<12} {'Category':<18} {'Amount':>10} Description")
        for r in rows:
            print(f"{r['id']:<5} {r['date']:<12} {r['category']:<18} {r['amount']:>10.2f} {r['description']}")


def cmd_expense_delete(args: argparse.Namespace) -> None:
    with connect() as conn:
        user = require_user(conn)
        expense = get_expense(conn, user["id"], args.id)
        conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense["id"], user["id"]))
        conn.commit()
        print("Expense deleted.")


def cmd_expense_edit(args: argparse.Namespace) -> None:
    with connect() as conn:
        user = require_user(conn)
        expense = get_expense(conn, user["id"], args.id)
        date = parse_date(args.date) if args.date else expense["date"]
        amount = parse_amount(args.amount) if args.amount is not None else expense["amount"]
        category = get_category(conn, user["id"], args.category).id if args.category else expense["category_id"]
        description = args.description if args.description is not None else expense["description"]
        conn.execute(
            """
            UPDATE expenses
            SET date = ?, category_id = ?, amount = ?, description = ?
            WHERE id = ? AND user_id = ?
            """,
            (date, category, amount, description, expense["id"], user["id"]),
        )
        conn.commit()
        print("Expense updated.")


def cmd_report(args: argparse.Namespace) -> None:
    if not 1 <= args.month <= 12:
        raise SystemExit("Month must be between 1 and 12.")
    start = f"{args.year:04d}-{args.month:02d}-01"
    if args.month == 12:
        end = f"{args.year + 1:04d}-01-01"
    else:
        end = f"{args.year:04d}-{args.month + 1:02d}-01"
    with connect() as conn:
        user = require_user(conn)
        rows = conn.execute(
            """
            SELECT c.name AS category, COALESCE(SUM(e.amount), 0) AS total
            FROM categories c
            LEFT JOIN expenses e ON e.category_id = c.id AND e.user_id = c.user_id
                AND e.date >= ? AND e.date < ?
            WHERE c.user_id = ?
            GROUP BY c.id, c.name
            ORDER BY total DESC, c.name
            """,
            (start, end, user["id"]),
        ).fetchall()
        grand_total = sum(float(r["total"]) for r in rows)
        print(f"Monthly Report: {args.month:02d}/{args.year}")
        print(f"{'Category':<20} {'Total':>12} {'Share':>10}")
        print("-" * 44)
        for r in rows:
            share = (float(r["total"]) / grand_total * 100) if grand_total else 0.0
            print(f"{r['category']:<20} {float(r['total']):>12.2f} {share:>9.1f}%")
        print("-" * 44)
        print(f"{'Total':<20} {grand_total:>12.2f}")


def cmd_export(args: argparse.Namespace) -> None:
    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if start > end:
        raise SystemExit("Start date must be on or before end date.")
    output = Path(args.output)
    with connect() as conn:
        user = require_user(conn)
        rows = conn.execute(
            """
            SELECT e.date, c.name AS category, e.amount, e.description
            FROM expenses e JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = ? AND e.date >= ? AND e.date <= ?
            ORDER BY e.date, e.id
            """,
            (user["id"], start, end),
        ).fetchall()
        with output.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "category", "amount", "description"])
            writer.writeheader()
            for r in rows:
                writer.writerow(dict(r))
        print(f"Exported {len(rows)} expense(s) to {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track expenses by category.")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    p = auth_sub.add_parser("register")
    p.add_argument("--username", required=True)
    p.add_argument("--password")
    p.set_defaults(func=cmd_auth_register)

    p = auth_sub.add_parser("login")
    p.add_argument("--username")
    p.add_argument("--password")
    p.set_defaults(func=cmd_auth_login)

    auth_sub.add_parser("logout").set_defaults(func=cmd_auth_logout)
    auth_sub.add_parser("whoami").set_defaults(func=cmd_auth_whoami)

    cat = sub.add_parser("category")
    cat_sub = cat.add_subparsers(dest="category_command", required=True)
    p = cat_sub.add_parser("create")
    p.add_argument("name")
    p.set_defaults(func=cmd_category_create)

    cat_sub.add_parser("list").set_defaults(func=cmd_category_list)

    p = cat_sub.add_parser("delete")
    p.add_argument("identifier")
    p.set_defaults(func=cmd_category_delete)

    p = cat_sub.add_parser("edit")
    p.add_argument("identifier")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_category_edit)

    exp = sub.add_parser("expense")
    exp_sub = exp.add_subparsers(dest="expense_command", required=True)
    p = exp_sub.add_parser("add")
    p.add_argument("--date", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--description", default="")
    p.set_defaults(func=cmd_expense_add)

    exp_sub.add_parser("list").set_defaults(func=cmd_expense_list)

    p = exp_sub.add_parser("delete")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_expense_delete)

    p = exp_sub.add_parser("edit")
    p.add_argument("id", type=int)
    p.add_argument("--date")
    p.add_argument("--category")
    p.add_argument("--amount", type=float)
    p.add_argument("--description")
    p.set_defaults(func=cmd_expense_edit)

    p = sub.add_parser("report")
    p.add_argument("--month", type=int, required=True)
    p.add_argument("--year", type=int, required=True)
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("export")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--output", default="expenses.csv")
    p.set_defaults(func=cmd_export)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except sqlite3.Error as exc:
        raise SystemExit(f"Database error: {exc}")


if __name__ == "__main__":
    main()

