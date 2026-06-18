#!/usr/bin/env python3
import argparse
import sys
import pandas as pd
import numpy as np
from tabulate import tabulate

def parse_csv_file(file_path):
    try:
        df = pd.read_csv(file_path)
        return df
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
    except pd.errors.EmptyDataError:
        print(f"Error: File '{file_path}' is empty.", file=sys.stderr)
    except pd.errors.ParserError as e:
        print(f"Error parsing CSV file '{file_path}': {e}", file=sys.stderr)
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}", file=sys.stderr)
    return None

def generate_summary_statistics(df):
    summary_stats = {}
    numeric_cols = df.select_dtypes(include=['number']).columns
    
    for column in numeric_cols:
        values = df[column].dropna()
        if len(values) == 0:
            continue
            
        mode_series = values.mode()
        mode_val = mode_series.iloc[0] if len(mode_series) > 0 else None
        
        stats = {
            'mean': float(values.mean()),
            'median': float(values.median()),
            'mode': float(mode_val) if mode_val is not None else None,
            'std_dev': float(values.std()),
            'variance': float(values.var()),
            'min': float(values.min()),
            'max': float(values.max()),
            'count': int(len(values))
        }
        summary_stats[column] = stats
    
    return summary_stats

def format_output(summary_stats):
    if not summary_stats:
        return "No numeric columns with valid data found."
    
    rows = []
    for column, stats in summary_stats.items():
        rows.append([
            column,
            round(stats['mean'], 6) if stats['mean'] is not None else 'N/A',
            round(stats['median'], 6) if stats['median'] is not None else 'N/A',
            round(stats['mode'], 6) if stats['mode'] is not None else 'N/A',
            round(stats['std_dev'], 6) if stats['std_dev'] is not None else 'N/A',
            round(stats['variance'], 6) if stats['variance'] is not None else 'N/A',
            round(stats['min'], 6) if stats['min'] is not None else 'N/A',
            round(stats['max'], 6) if stats['max'] is not None else 'N/A'
        ])
    
    return tabulate(
        rows,
        headers=['Column', 'Mean', 'Median', 'Mode', 'Std Dev', 'Variance', 'Min', 'Max'],
        tablefmt='orgtbl'
    )

def main():
    parser = argparse.ArgumentParser(
        description='Generate summary statistics for numeric columns in a CSV file.'
    )
    parser.add_argument('file', help='Path to the CSV file')
    parser.add_argument('--output', '-o', choices=['table', 'json'], default='table',
                       help='Output format (default: table)')
    args = parser.parse_args()
    
    df = parse_csv_file(args.file)
    if df is None:
        sys.exit(1)
    
    summary_stats = generate_summary_statistics(df)
    
    if args.output == 'json':
        import json
        print(json.dumps(summary_stats, indent=2))
    else:
        print(format_output(summary_stats))

if __name__ == '__main__':
    main()