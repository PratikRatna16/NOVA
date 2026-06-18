# CLI File Organizer Technical Specification
## Overview
The CLI file organizer is a command-line application designed to watch a specified directory for new files, sort them into subfolders based on file type and date, handle duplicate files using MD5 hashing, generate a JSON activity log, and support an undo command.

## Requirements
### Functional Requirements
1. **Directory Watcher**: The application must watch a specified directory for new files.
2. **File Sorting**: The application must sort new files into subfolders based on file type and date.
3. **Duplicate File Handling**: The application must detect and handle duplicate files using MD5 hashing.
4. **JSON Activity Log**: The application must generate a JSON activity log of all file moves.
5. **Undo Command**: The application must support an undo command to reverse the last operation.

### Non-Functional Requirements
1. **Performance**: The application must be able to handle a large number of files without significant performance degradation.
2. **Security**: The application must ensure the integrity of the files and the directory structure.
3. **Usability**: The application must provide a user-friendly interface for configuring the directory watcher and viewing the activity log.

## System Components
### Directory Watcher
* **Component Name**: `dir_watcher`
* **Description**: Watches a specified directory for new files.
* **Input**: Directory path
* **Output**: List of new files

### File Sorter
* **Component Name**: `file_sorter`
* **Description**: Sorts new files into subfolders based on file type and date.
* **Input**: List of new files
* **Output**: List of sorted files

### Duplicate File Handler
* **Component Name**: `dup_handler`
* **Description**: Detects and handles duplicate files using MD5 hashing.
* **Input**: List of sorted files
* **Output**: List of unique files

### JSON Activity Log
* **Component Name**: `activity_log`
* **Description**: Generates a JSON activity log of all file moves.
* **Input**: List of file moves
* **Output**: JSON activity log

### Undo Command
* **Component Name**: `undo_cmd`
* **Description**: Reverses the last operation.
* **Input**: None
* **Output**: None

## System Architecture
```markdown
+---------------+
|  dir_watcher  |
+---------------+
       |
       |
       v
+---------------+
|  file_sorter  |
+---------------+
       |
       |
       v
+---------------+
|  dup_handler  |
+---------------+
       |
       |
       v
+---------------+
|  activity_log  |
+---------------+
       |
       |
       v
+---------------+
|  undo_cmd     |
+---------------+
```

## Data Structures
### File Object
* **Attribute**: `name` (string)
* **Attribute**: `type` (string)
* **Attribute**: `date` (string)
* **Attribute**: `hash` (string)

### Activity Log
* **Attribute**: `timestamp` (string)
* **Attribute**: `file_name` (string)
* **Attribute**: `source_dir` (string)
* **Attribute**: `dest_dir` (string)

## Algorithms
### Directory Watcher
1. Initialize directory watcher
2. Loop indefinitely
3. Check for new files
4. If new files found, trigger file sorting

### File Sorter
1. Initialize file sorter
2. Loop through new files
3. Determine file type and date
4. Move file to corresponding subfolder

### Duplicate File Handler
1. Initialize duplicate file handler
2. Loop through sorted files
3. Calculate MD5 hash for each file
4. Check for duplicate files
5. If duplicate file found, skip it

### JSON Activity Log
1. Initialize activity log
2. Loop through file moves
3. Generate JSON object for each file move
4. Append JSON object to activity log

### Undo Command
1. Initialize undo command
2. Check if last operation can be undone
3. If undoable, reverse last operation

## APIs and Interfaces
### Directory Watcher API
* **Method**: `watch_directory`
* **Input**: `directory_path`
* **Output**: `list_of_new_files`

### File Sorter API
* **Method**: `sort_files`
* **Input**: `list_of_new_files`
* **Output**: `list_of_sorted_files`

### Duplicate File Handler API
* **Method**: `handle_duplicates`
* **Input**: `list_of_sorted_files`
* **Output**: `list_of_unique_files`

### JSON Activity Log API
* **Method**: `generate_log`
* **Input**: `list_of_file_moves`
* **Output**: `json_activity_log`

### Undo Command API
* **Method**: `undo_last_operation`
* **Input**: None
* **Output**: None

## Testing and Validation
### Unit Testing
* Test each component individually
* Test directory watcher
* Test file sorter
* Test duplicate file handler
* Test JSON activity log
* Test undo command

### Integration Testing
* Test the entire system
* Test directory watcher with file sorter
* Test file sorter with duplicate file handler
* Test duplicate file handler with JSON activity log
* Test JSON activity log with undo command

### Validation
* Validate system functionality
* Validate performance
* Validate security
* Validate usability

## Deployment and Maintenance
### Deployment
* Deploy system on a server or cloud platform
* Configure directory watcher and file sorter
* Initialize JSON activity log and undo command

### Maintenance
* Monitor system performance and security
* Update system components as needed
* Fix bugs and issues
* Improve system functionality and usability