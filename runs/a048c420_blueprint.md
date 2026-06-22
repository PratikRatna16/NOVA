# CLI Regex Batch File Renamer
## Overview
The goal of this project is to design a CLI regex batch file renamer that matches against full filenames including extensions. This tool will allow users to rename multiple files at once based on a provided regex pattern.

## Requirements
### Input & Arguments
* The tool will accept a regex pattern as a required positional argument.
* The tool will accept a directory path as an optional positional argument. If not provided, the current working directory will be used.
* The tool will accept a `-r` or `--recursive` flag to enable recursive renaming of files in subdirectories.
* The tool will accept a `-d` or `--dry-run` flag to simulate the renaming process without actually renaming the files.
* The tool will accept a `-v` or `--verbose` flag to enable verbose output.

### Regex Pattern
* The regex pattern will be used to match against the full filenames, including extensions.
* The pattern will be validated before renaming any files to ensure it is a valid regex pattern.

### Renaming
* The tool will rename the files based on the provided regex pattern.
* The tool will use the `re.sub()` function to replace the matched pattern with the replacement string.
* The tool will preserve the file extension during renaming.

### Output
* The tool will output the renamed files to the console.
* The tool will output any errors that occur during the renaming process to the console.

## Design
### Layout
* The tool will use the `argparse` library to parse the command-line arguments.
* The tool will use the `os` library to interact with the file system.
* The tool will use the `re` library to work with regex patterns.

### Fallbacks
* If the provided regex pattern is invalid, the tool will output an error message and exit.
* If the provided directory path is invalid, the tool will output an error message and exit.
* If the `-r` or `--recursive` flag is used, the tool will recursively rename files in subdirectories.

### Error Handling
* The tool will handle any errors that occur during the renaming process and output them to the console.

## Implementation
### Code Structure
* The tool will consist of the following modules:
	+ `main.py`: The main entry point of the tool.
	+ `renamer.py`: The module responsible for renaming the files.
	+ `utils.py`: The module responsible for utility functions, such as regex pattern validation.

### Example Usage
* `python cli_regex_renamer.py -r -d "old_name" "new_name" /path/to/directory`
* `python cli_regex_renamer.py -v "old_name" "new_name" /path/to/directory`

## Testing
* The tool will be tested using a combination of unit tests and integration tests.
* The tests will cover the following scenarios:
	+ Valid regex pattern
	+ Invalid regex pattern
	+ Recursive renaming
	+ Dry-run mode
	+ Verbose output

## Optimization
* The tool will be optimized for performance by using efficient regex pattern matching and file system operations.

## Security
* The tool will follow best practices for security, such as validating user input and handling errors properly.

## Future Development
* The tool will be designed to be extensible, with the ability to add new features and functionality in the future.

### API Documentation
* The tool will include API documentation for the `renamer.py` module.
* The documentation will include information on the available functions, classes, and variables.

### Commit Messages
* Commit messages will follow the standard format of `type(scope): brief description`.
* The `type` will be one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, or `build`.
* The `scope` will be the module or component being modified.
* The `brief description` will be a short summary of the changes made.

### Code Review
* Code reviews will be performed using a combination of automated tools and manual review.
* The review will cover the following aspects:
	+ Code quality
	+ Security
	+ Performance
	+ Documentation

## Conclusion
The CLI regex batch file renamer will be a powerful tool for renaming multiple files at once based on a provided regex pattern. The tool will be designed with performance, security, and extensibility in mind, and will include features such as recursive renaming, dry-run mode, and verbose output. The tool will be tested thoroughly to ensure it works correctly and efficiently.