#!/usr/bin/env python3
import argparse
import gzip
import bz2
import zipfile
import json
import os
import sys
from pathlib import Path

def get_algorithm(filepath, specified_algo=None):
    if specified_algo:
        return specified_algo
    ext = Path(filepath).suffix.lower()
    algo_map = {'.zip': 'zip', '.gz': 'gzip', '.bz2': 'bz2'}
    if ext in algo_map:
        return algo_map[ext]
    return 'zip'

def compress_file(filepath, algorithm, output_path=None, force=False):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    
    original_size = os.path.getsize(filepath)
    if original_size == 0:
        raise ValueError(f"File is empty: {filepath}")
    
    input_path = Path(filepath)
    
    algo_handlers = {
        'gzip': lambda: _compress_gzip(filepath, output_path),
        'bz2': lambda: _compress_bz2(filepath, output_path),
        'zip': lambda: _compress_zip(filepath, output_path)
    }
    
    compressed_path, compressed_size = algo_handlers[algorithm]()
    
    if output_path and Path(output_path).suffix.lower() == '.json':
        _append_json_result(output_path, filepath, algorithm, original_size, compressed_size, force)
    
    ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
    return {
        'file': filepath,
        'algorithm': algorithm,
        'original_size': original_size,
        'compressed_size': compressed_size,
        'ratio': ratio
    }

def _compress_gzip(filepath, output_path):
    output = output_path or f"{filepath}.gz"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with open(filepath, 'rb') as f_in:
        with gzip.open(output, 'wb') as f_out:
            f_out.writelines(f_in)
    return output, os.path.getsize(output)

def _compress_bz2(filepath, output_path):
    output = output_path or f"{filepath}.bz2"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with open(filepath, 'rb') as f_in:
        with bz2.open(output, 'wb') as f_out:
            f_out.writelines(f_in)
    return output, os.path.getsize(output)

def _compress_zip(filepath, output_path):
    output = output_path or f"{filepath}.zip"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(filepath, Path(filepath).name)
    return output, os.path.getsize(output)

def decompress_file(filepath, algorithm, output_path=None, force=False):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")
    
    compressed_size = os.path.getsize(filepath)
    
    algo_handlers = {
        'gzip': lambda: _decompress_gzip(filepath, output_path),
        'bz2': lambda: _decompress_bz2(filepath, output_path),
        'zip': lambda: _decompress_zip(filepath, output_path)
    }
    
    output, original_size = algo_handlers[algorithm]()
    
    if output_path and Path(output_path).suffix.lower() == '.json':
        _append_json_result(output_path, filepath, algorithm, compressed_size, original_size, force)
    
    ratio = (1 - original_size / compressed_size) * 100 if compressed_size > 0 else 0
    return {
        'file': filepath,
        'algorithm': algorithm,
        'original_size': compressed_size,
        'compressed_size': original_size,
        'ratio': ratio
    }

def _decompress_gzip(filepath, output_path):
    output = output_path or filepath[:-3] if filepath.endswith('.gz') else f"{filepath}.decompressed"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with gzip.open(filepath, 'rb') as f_in:
        with open(output, 'wb') as f_out:
            f_out.writelines(f_in)
    return output, os.path.getsize(output)

def _decompress_bz2(filepath, output_path):
    output = output_path or filepath[:-4] if filepath.endswith('.bz2') else f"{filepath}.decompressed"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with bz2.open(filepath, 'rb') as f_in:
        with open(output, 'wb') as f_out:
            f_out.writelines(f_in)
    return output, os.path.getsize(output)

def _decompress_zip(filepath, output_path):
    output = output_path or filepath[:-4] if filepath.endswith('.zip') else f"{filepath}.decompressed"
    if os.path.exists(output) and output_path:
        raise FileExistsError(f"Output file exists: {output}")
    with zipfile.ZipFile(filepath, 'r') as zf:
        zf.extractall(Path(output).parent if output_path else '.')
        name = zf.namelist()[0]
        if not output_path:
            output = filepath[:-4]
    return output, os.path.getsize(output)

def _append_json_result(output_path, input_file, algorithm, original_size, compressed_size, force):
    if force and os.path.exists(output_path):
        os.remove(output_path)
    results = []
    if os.path.exists(output_path):
        with open(output_path, 'r') as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                results = []
    results.append({
        'file': input_file,
        'algorithm': algorithm,
        'original_size': original_size,
        'compressed_size': compressed_size
    })
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description='CLI File Compression and Decompression Tool')
    parser.add_argument('files', nargs='+', help='File paths to process')
    parser.add_argument('-a', '--algorithm', choices=['zip', 'gzip', 'bz2'], help='Compression algorithm')
    parser.add_argument('-c', '--compress', action='store_true', help='Compress file(s)')
    parser.add_argument('-d', '--decompress', action='store_true', help='Decompress file(s)')
    parser.add_argument('-o', '--output', help='Output file path')
    parser.add_argument('-f', '--force', action='store_true', help='Overwrite existing files')
    
    args = parser.parse_args()
    
    if not args.compress and not args.decompress:
        args.compress = True
    
    if args.compress and args.decompress:
        print("Error: Cannot use both compress and decompress flags", file=sys.stderr)
        sys.exit(1)
    
    for filepath in args.files:
        try:
            algorithm = get_algorithm(filepath, args.algorithm)
            if args.compress:
                result = compress_file(filepath, algorithm, args.output, args.force)
            else:
                result = decompress_file(filepath, algorithm, args.output, args.force)
            
            print(f"File: {result['file']}")
            print(f"Algorithm: {result['algorithm']}")
            print(f"Original size: {result['original_size']} bytes")
            print(f"Compressed size: {result['compressed_size']} bytes")
            print(f"Ratio: {result['ratio']:.2f}%")
            print("-" * 40)
        except Exception as e:
            print(f"Error processing {filepath}: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == '__main__':
    main()