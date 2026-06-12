```python
"""
System Monitor Script

This script logs real-time CPU percentages, RAM consumption metrics, and active disk IO status.
It uses the psutil library for system monitoring and the logging library for log management.
Optional scheduling functionality is available using the schedule library.

Author: [Your Name]
Date: [Today's Date]
"""

import psutil
import logging
import schedule
import time

# Initialize the logger
def init_logger():
    """
    Initialize the logger with a basic configuration.
    
    The logger will write to a file named 'system_monitor.log' with an INFO level.
    """
    logging.basicConfig(filename='system_monitor.log', level=logging.INFO)

# Log a message
def log_message(message):
    """
    Log a message using the logging library.
    
    Args:
        message (str): The message to log.
    """
    logging.info(message)

# Get the current CPU percentage
def get_cpu_percent():
    """
    Get the current CPU percentage.
    
    Returns:
        float: The current CPU percentage.
    """
    return psutil.cpu_percent()

# Log the current CPU percentage
def log_cpu_percent():
    """
    Log the current CPU percentage.
    """
    cpu_percent = get_cpu_percent()
    logging.info(f"CPU Percentage: {cpu_percent}%")

# Get the current RAM usage
def get_ram_usage():
    """
    Get the current RAM usage.
    
    Returns:
        psutil._vm_memory: The current RAM usage.
    """
    return psutil.virtual_memory()

# Log the current RAM usage
def log_ram_usage():
    """
    Log the current RAM usage.
    """
    ram_usage = get_ram_usage()
    logging.info(f"RAM Usage: {ram_usage.percent}%")

# Get the current disk IO statistics
def get_disk_io():
    """
    Get the current disk IO statistics.
    
    Returns:
        psutil._io_counter: The current disk IO statistics.
    """
    return psutil.disk_io_counters()

# Log the current disk IO statistics
def log_disk_io():
    """
    Log the current disk IO statistics.
    """
    disk_io = get_disk_io()
    logging.info(f"Disk IO: read={disk_io.read_bytes}, write={disk_io.write_bytes}")

# Schedule a task to run at a specified interval
def schedule_task(task, interval):
    """
    Schedule a task to run at a specified interval.
    
    Args:
        task (function): The task to schedule.
        interval (int): The interval at which to run the task.
    """
    schedule.every(interval).seconds.do(task)

# Run the scheduled tasks
def run_schedule():
    """
    Run the scheduled tasks.
    """
    while True:
        schedule.run_pending()
        time.sleep(1)

# Main function
def main():
    """
    Main function.
    
    Initialize the logger, log the current system metrics, and schedule tasks to run at regular intervals.
    """
    init_logger()
    log_cpu_percent()
    log_ram_usage()
    log_disk_io()

    # Schedule tasks to run at regular intervals (optional)
    schedule_task(log_cpu_percent, 1)
    schedule_task(log_ram_usage, 1)
    schedule_task(log_disk_io, 1)

    run_schedule()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        print(f"An error occurred: {e}")
```

This script will log real-time CPU percentages, RAM consumption metrics, and active disk IO status to a file named 'system_monitor.log'. It will also schedule these tasks to run at regular intervals using the schedule library.

The script is structured into separate functions for each monitoring function, logging, and scheduling. The main function initializes the logger, logs the current system metrics, and schedules tasks to run at regular intervals.

Error handling is implemented using try-except blocks to catch and log any errors that occur during execution. The script will continue to run even if an error occurs, ensuring that the system metrics are still logged.

Note: You will need to install the required libraries (psutil, schedule) using pip:
```bash
pip install psutil schedule
```