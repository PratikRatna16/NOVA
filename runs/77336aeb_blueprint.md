# CLI File Organizer Technical Specification
## Overview
The CLI file organizer is a command-line application designed to watch a specified directory for new files, sort them into subfolders based on file type and date, handle duplicate files using MD5 hashing, generate a JSON activity log, and support an undo command.

## Requirements
### Functional Requirements
1. **Directory Watching**: The application must watch a specified directory for new files.
2. **File Sorting**: The application must sort new files into subfolders based on file type and date.
3. **Duplicate File Handling**: The application must detect and handle duplicate files using MD5 hashing.
4. **Activity Logging**: The application must generate a JSON activity log of all file moves.
5. **Undo Command**: The application must support an undo command to reverse the last operation.

### Non-Functional Requirements
1. **Performance**: The application must be able to handle a large number of files without significant performance degradation.
2. **Security**: The application must ensure the integrity of files and prevent data loss or corruption.
3. **Usability**: The application must provide a user-friendly interface and clear instructions for use.

## Design
### System Components
1. **Directory Watcher**: Responsible for monitoring the specified directory for new files.
2. **File Sorter**: Responsible for sorting new files into subfolders based on file type and date.
3. **Duplicate File Handler**: Responsible for detecting and handling duplicate files using MD5 hashing.
4. **Activity Logger**: Responsible for generating a JSON activity log of all file moves.
5. **Undo Manager**: Responsible for managing the undo command and reversing the last operation.

### System Flow
1. The directory watcher monitors the specified directory for new files.
2. When a new file is detected, the file sorter sorts it into a subfolder based on file type and date.
3. The duplicate file handler checks for duplicate files using MD5 hashing and handles them accordingly.
4. The activity logger generates a JSON activity log of the file move.
5. The undo manager stores the file move operation for potential reversal.

## Implementation
### Directory Watching
* Utilize the `watchdog` library to monitor the specified directory for new files.
* Implement a callback function to handle new file events.

### File Sorting
* Utilize the `pathlib` library to determine file type and date.
* Create subfolders based on file type and date.
* Move files into corresponding subfolders.

### Duplicate File Handling
* Utilize the `hashlib` library to generate MD5 hashes for files.
* Compare MD5 hashes to detect duplicate files.
* Handle duplicate files by renaming or deleting them.

### Activity Logging
* Utilize the `json` library to generate a JSON activity log.
* Log file move operations, including source and destination paths.

### Undo Command
* Utilize a stack data structure to store file move operations.
* Implement an undo command to reverse the last operation.

## Testing
### Unit Testing
* Test individual components, such as the directory watcher and file sorter.
* Utilize a testing framework, such as `unittest`, to write and run tests.

### Integration Testing
* Test the entire system, including all components and interactions.
* Utilize a testing framework, such as `pytest`, to write and run tests.

## Deployment
### Installation
* Utilize a package manager, such as `pip`, to install dependencies.
* Install the application using a setup script or package manager.

### Configuration
* Provide a configuration file or command-line options to specify the directory to watch and other settings.
* Utilize a configuration library, such as `configparser`, to parse configuration files.

## Maintenance
### Updates
* Regularly update dependencies and libraries to ensure security and stability.
* Utilize a version control system, such as `git`, to track changes and collaborate with developers.

### Bug Fixing
* Utilize a bug tracking system, such as `github issues`, to report and track bugs.
* Fix bugs and release updates to ensure the application remains stable and functional.