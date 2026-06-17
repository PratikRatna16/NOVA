#!/usr/bin/env python3
"""Loan EMI Calculator CLI Tool"""

import argparse
from decimal import Decimal, ROUND_HALF_UP
from tabulate import tabulate


def validate_positive(value: str, name: str) -> Decimal:
    try:
        val = Decimal(value)
        if val <= 0:
            raise ValueError(f"{name} must be positive, got {val}")
        return val
    except Exception as e:
        raise ValueError(f"Invalid {name}: {value}") from e


def calculate_emi(principal: Decimal, annual_rate: Decimal, tenure_months: int) -> Decimal:
    monthly_rate = annual_rate / Decimal(1200)
    if monthly_rate == 0 or tenure_months == 0:
        raise ValueError("Cannot calculate EMI with zero interest rate or tenure")
    
    factor = (1 + monthly_rate) ** tenure_months
    emi = (principal * monthly_rate * factor) / (factor - 1)
    return emi.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def generate_amortization_schedule(principal: Decimal, annual_rate: Decimal, tenure_months: int, emi: Decimal) -> list:
    schedule = []
    balance = principal
    monthly_rate = annual_rate / Decimal(1200)
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for month in range(1, tenure_months + 1):
        interest_paid = (balance * monthly_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        principal_paid = (emi - interest_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        balance = (balance - principal_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Adjust last payment to clear remaining balance
        if month == tenure_months:
            principal_paid = balance + interest_paid
            emi = principal_paid + interest_paid
            balance = Decimal('0')
        
        year = month // 12 + 1
        month_num = (month - 1) % 12 + 1
        period = f"{month_names[month_num - 1]} {year}"
        
        schedule.append([period, float(emi), float(interest_paid), float(principal_paid), float(balance)])
    
    return schedule


def parse_tenure(tenure: str) -> int:
    tenure = tenure.lower().strip()
    if tenure.endswith('years') or tenure.endswith('year') or tenure.endswith('yrs') or tenure.endswith('yr'):
        years = tenure.rstrip('s').removesuffix('ar').removesuffix('rs') if tenure.endswith('rs') else tenure.rstrip('s').removesuffix('r')
        return int(Decimal(years) * 12)
    if tenure.endswith('months') or tenure.endswith('month') or tenure.endswith('mos') or tenure.endswith('mo'):
        months = tenure.rstrip('s').removesuffix('h').removesuffix('ths') if tenure.endswith('ths') else tenure.rstrip('s')
        return int(Decimal(months))
    return int(Decimal(tenure))


def main():
    parser = argparse.ArgumentParser(description="Loan EMI Calculator")
    parser.add_argument("--principal", required=True, help="Loan principal amount")
    parser.add_argument("--interest-rate", required=True, help="Annual interest rate (percentage)")
    parser.add_argument("--tenure", required=True, help="Tenure in months or years (e.g., 12 or 1 year)")
    
    args = parser.parse_args()
    
    try:
        principal = validate_positive(args.principal, "Principal amount")
        annual_rate = validate_positive(args.interest_rate, "Interest rate")
        tenure_months = parse_tenure(args.tenure)
        
        if tenure_months <= 0:
            raise ValueError("Tenure must be positive")
        
        emi = calculate_emi(principal, annual_rate, tenure_months)
        total_payment = emi * tenure_months
        total_interest = total_payment - principal
        
        print(f"\nEMI Calculation:")
        print(f"Principal: {principal}")
        print(f"Annual Interest Rate: {annual_rate}%")
        print(f"Tenure: {tenure_months} months")
        print(f"Monthly EMI: {emi}")
        print(f"Total Payment: {total_payment.quantize(Decimal('0.01'))}")
        print(f"Total Interest: {total_interest.quantize(Decimal('0.01'))}\n")
        
        schedule = generate_amortization_schedule(principal, annual_rate, tenure_months, emi)
        print(tabulate(schedule[:min(12, len(schedule))] + 
                      (schedule[12:] and [["...", "...", "...", "...", "..."]] or []),
                      headers=["Month/Year", "Payment", "Interest", "Principal", "Balance"],
                      floatfmt=".2f", tablefmt="grid"))
        if len(schedule) > 12:
            print(f"... {len(schedule) - 12} more rows (showing first 12)")
            
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)


if __name__ == "__main__":
    main()