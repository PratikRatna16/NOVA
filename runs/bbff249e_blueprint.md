# CLI File Compression and Decompression Tool
## Overview
The purpose of this CLI tool is to provide a simple and efficient way to compress and decompress files using multiple algorithms. The tool will support zip, gzip, and bz2 compression formats.

## Requirements
### Input & Arguments
* The tool will accept variable positional arguments (nargs=+) for file paths.
* The tool will favor standard CLI arguments first.
* The tool will accept the following optional arguments:
	+ `-a` or `--algorithm` to specify the compression algorithm (zip, gzip, or bz2).
	+ `-c` or `--compress` to compress the file.
	+ `-d` or `--decompress` to decompress the file.
	+ `-o` or `--output` to specify the output file path.
	+ `-f` or `--force` to overwrite existing files.
* The tool will infer the file format from the file extension automatically.

### File Handling
* The tool will append to existing JSON array structure if the output file is in JSON format. Otherwise, it will overwrite the file.
* The tool will never overwrite with w mode directly if the output file already exists.

### Limit/Flag Logic
* The tool will not have a `-l` or `--limit` flag.

### Search & Ambiguity
* The tool will not perform search or ambiguity resolution.

### Stream Processing
* The tool will evaluate each file only once.
* The tool will not have throttling counters.

### Feature Completeness
* The tool will parse the user's input for every explicit feature requested.
* The tool will display the following information for each file:
	+ Compression algorithm used.
	+ Compression ratio.
	+ Original file size.
	+ Compressed file size.

### Smart Defaults & Inference
* The tool will infer the file format from the file extension automatically.
* The tool will never throw validation errors for missing type declarations when standard extensions are provided.

### Boundary Conditions
* The tool will validate all numeric inputs against realistic min/max before use.

## Usage
### Compression
* To compress a file using the default algorithm (zip), use the following command: `compress_tool file.txt`
* To compress a file using a specific algorithm, use the following command: `compress_tool -a gzip file.txt`
* To compress multiple files, use the following command: `compress_tool file1.txt file2.txt file3.txt`

### Decompression
* To decompress a file, use the following command: `compress_tool -d file.zip`
* To decompress a file using a specific algorithm, use the following command: `compress_tool -d -a gzip file.gz`

## Code Structure
The tool will be written in Python and will use the following libraries:
* `argparse` for parsing command-line arguments.
* `zipfile` for zip compression.
* `gzip` for gzip compression.
* `bz2` for bz2 compression.
* `json` for handling JSON output.

The tool will consist of the following modules:
* `main.py`: The main entry point of the tool.
* `compress.py`: Handles file compression.
* `decompress.py`: Handles file decompression.
* `utils.py`: Contains utility functions for file handling and output formatting.

## Error Handling
The tool will handle the following errors:
* Invalid command-line arguments.
* Invalid file format.
* File not found.
* Permission denied.
* Compression/decompression failed.

The tool will display error messages to the user and exit with a non-zero status code.

## Testing
The tool will be tested using the following test cases:
* Compression and decompression of single files.
* Compression and decompression of multiple files.
* Compression and decompression using different algorithms.
* Error handling for invalid command-line arguments, invalid file format, file not found, permission denied, and compression/decompression failed.

The tool will be tested on different operating systems and file systems to ensure compatibility.