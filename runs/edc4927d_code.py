#!/usr/bin/env python3
"""Personal Budget Manager CLI Tool"""

import argparse
import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fpdf import FPDF

DATA_FILE = "budget_data.json"

def load_data():
    """Load budget data from JSON file."""
    if not os.path.exists(DATA_FILE):
        return {"income": {}, "expenses": {}, "spending_limits": {}, "rollover": {}}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"income": {}, "expenses": {}, "spending_limits": {}, "rollover": {}}

def save_data(data):
    """Save budget data to JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def validate_decimal(value, field_name):
    """Validate and convert to Decimal, raising ValueError on invalid input."""
    try:
        d = Decimal(str(value))
        if d < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return d
    except InvalidOperation:
        raise ValueError(f"{field_name} must be a valid number")

def validate_month(month_str):
    """Validate month format YYYY-MM."""
    try:
        datetime.strptime(month_str, "%Y-%m")
        return month_str
    except ValueError:
        raise ValueError("Month must be in YYYY-MM format")

def add_income(args):
    """Add an income record for a specific month."""
    month = validate_month(args.month)
    amount = validate_decimal(args.amount, "Income amount")
    
    data = load_data()
    data["income"][month] = float(amount)
    save_data(data)
    print(f"Added income: ${amount:.2f} for {month}")

def add_expense(args):
    """Add an expense record for a specific month and category."""
    month = validate_month(args.month)
    amount = validate_decimal(args.amount, "Expense amount")
    
    data = load_data()
    if month not in data["expenses"]:
        data["expenses"][month] = {}
    if args.category not in data["expenses"][month]:
        data["expenses"][month][args.category] = []
    
    data["expenses"][month][args.category].append({
        "amount": float(amount),
        "note": args.note or ""
    })
    save_data(data)
    print(f"Added expense: ${amount:.2f} for {args.category} in {month}")

def set_spending_limit(args):
    """Set a spending limit for a category."""
    amount = validate_decimal(args.amount, "Spending limit")
    
    data = load_data()
    data["spending_limits"][args.category] = float(amount)
    save_data(data)
    print(f"Set spending limit: ${amount:.2f} for {args.category}")

def calculate_rollover(args):
    """Calculate and apply rollover for a specific month."""
    month = validate_month(args.month)
    data = load_data()
    
    if month not in data["expenses"]:
        print(f"No expenses found for {month}")
        return
    
    expenses = data["expenses"].get(month, {})
    limits = data["spending_limits"]
    
    rollover_amounts = {}
    total_income = Decimal(str(data["income"].get(month, 0)))
    total_expenses = Decimal("0")
    
    for category, exp_list in expenses.items():
        spent = sum(Decimal(str(e["amount"])) for e in exp_list)
        limit = Decimal(str(limits.get(category, float("inf"))))
        rollover = limit - spent
        rollover_amounts[category] = float(rollover)
        total_expenses += spent
    
    data["rollover"][month] = rollover_amounts
    save_data(data)
    
    print(f"\nRollover calculations for {month}:")
    print(f"Total Income: ${total_income:.2f}")
    print(f"Total Expenses: ${total_expenses:.2f}")
    print(f"Net Balance: ${(total_income - total_expenses):.2f}")
    for cat, rol in rollover_amounts.items():
        status = "surplus" if rol >= 0 else "overspent"
        print(f"  {cat}: ${rol:.2f} ({status})")

def generate_report(args):
    """Generate a PDF financial report."""
    month = validate_month(args.month) if args.month else None
    
    data = load_data()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    months_to_report = [month] if month else sorted(data["income"].keys() | data["expenses"].keys())
    
    for m in months_to_report:
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 10, f"Financial Report: {m}", ln=True)
        pdf.set_font("Helvetica", size=12)
        
        # Income
        income = Decimal(str(data["income"].get(m, 0)))
        pdf.cell(0, 8, f"Income: ${income:.2f}", ln=True)
        
        # Expenses breakdown
        expenses = data["expenses"].get(m, {})
        if expenses:
            pdf.cell(0, 8, "Expenses:", ln=True)
            for cat, exp_list in sorted(expenses.items()):
                spent = sum(Decimal(str(e["amount"])) for e in exp_list)
                limit = Decimal(str(data["spending_limits"].get(cat, 0)))
                pdf.cell(0, 6, f"  - {cat}: ${spent:.2f} / ${limit:.2f} limit", ln=True)
        
        # Rollover
        rollover = data["rollover"].get(m, {})
        if rollover:
            pdf.cell(0, 8, "Rollover:", ln=True)
            for cat, rol in sorted(rollover.items()):
                status = "surplus" if rol >= 0 else "overspent"
                pdf.cell(0, 6, f"  - {cat}: ${rol:.2f} ({status})", ln=True)
        
        pdf.ln(5)
    
    # Add spending limits summary
    if data["spending_limits"]:
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 10, "Spending Limits Summary:", ln=True)
        pdf.set_font("Helvetica", size=12)
        for cat, lim in sorted(data["spending_limits"].items()):
            pdf.cell(0, 8, f"  {cat}: ${lim:.2f}", ln=True)
    
    output_path = args.output or "budget_report.pdf"
    pdf.output(output_path)
    print(f"Report generated: {output_path}")

def list_records(args):
    """List income, expenses, or spending limits."""
    data = load_data()
    cmd_map = {
        "income": lambda: [f"{k}: ${v:.2f}" for k, v in sorted(data["income"].items())],
        "expenses": lambda: [f"{k}: {v}" for k, v in sorted(data["expenses"].items())],
        "limits": lambda: [f"{k}: ${v:.2f}" for k, v in sorted(data["spending_limits"].items())],
        "rollover": lambda: [f"{k}: {v}" for k, v in sorted(data["rollover"].items())]
    }
    
    if args.type not in cmd_map:
        print(f"Unknown type: {args.type}")
        return
    
    records = cmd_map[args.type]()
    if records:
        print(f"\n{args.type.title()}:")
        for rec in records:
            print(f"  {rec}")
    else:
        print(f"No {args.type} records found.")

def delete_record(args):
    """Delete an income, expense, or limit record."""
    data = load_data()
    
    if args.type == "income":
        if args.month in data["income"]:
            del data["income"][args.month]
            print(f"Deleted income record for {args.month}")
        else:
            print(f"No income record found for {args.month}")
    elif args.type == "limit":
        if args.category in data["spending_limits"]:
            del data["spending_limits"][args.category]
            print(f"Deleted spending limit for {args.category}")
        else:
            print(f"No spending limit found for {args.category}")
    elif args.type == "expense":
        if args.month in data["expenses"] and args.category in data["expenses"][args.month]:
            del data["expenses"][args.month][args.category]
            if not data["expenses"][args.month]:
                del data["expenses"][args.month]
            print(f"Deleted expenses for {args.category} in {args.month}")
        else:
            print(f"No expense record found for {args.category} in {args.month}")
    else:
        print(f"Unknown type: {args.type}")
        return
    
    save_data(data)

def main():
    parser = argparse.ArgumentParser(description="Personal Budget Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # add_income
    p = subparsers.add_parser("add_income", help="Add income record")
    p.add_argument("month", help="Month in YYYY-MM format")
    p.add_argument("amount", help="Income amount")
    p.set_defaults(func=add_income)
    
    # add_expense
    p = subparsers.add_parser("add_expense", help="Add expense record")
    p.add_argument("month", help="Month in YYYY-MM format")
    p.add_argument("category", help="Expense category")
    p.add_argument("amount", help="Expense amount")
    p.add_argument("--note", "-n", default="", help="Optional note")
    p.set_defaults(func=add_expense)
    
    # set_spending_limit
    p = subparsers.add_parser("set_spending_limit", help="Set spending limit")
    p.add_argument("category", help="Category name")
    p.add_argument("amount", help="Spending limit amount")
    p.set_defaults(func=set_spending_limit)
    
    # calculate_rollover
    p = subparsers.add_parser("calculate_rollover", help="Calculate rollover for a month")
    p.add_argument("month", help="Month in YYYY-MM format")
    p.set_defaults(func=calculate_rollover)
    
    # generate_report
    p = subparsers.add_parser("generate_report", help="Generate PDF report")
    p.add_argument("--month", "-m", help="Specific month (YYYY-MM), or all months")
    p.add_argument("--output", "-o", help="Output PDF filename")
    p.set_defaults(func=generate_report)
    
    # list_records
    p = subparsers.add_parser("list", help="List records")
    p.add_argument("type", choices=["income", "expenses", "limits", "rollover"])
    p.set_defaults(func=list_records)
    
    # delete_record
    p = subparsers.add_parser("delete", help="Delete a record")
    p.add_argument("type", choices=["income", "limit", "expense"])
    p.add_argument("--month", "-m", help="Month (required for income/expense)")
    p.add_argument("--category", "-c", help="Category (required for expense/limit)")
    p.set_defaults(func=delete_record)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        try:
            args.func(args)
        except ValueError as e:
            print(f"Error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()