# Lightweight Local System Monitoring Utility in Python
==============================================

## Introduction
---------------

This document outlines the core requirements and technical specifications for a lightweight local system monitoring utility written in Python. The utility aims to log real-time CPU percentages, RAM consumption metrics, and active disk IO status.

## Requirements
---------------

*   Python 3.8 or later
*   `psutil` library for system monitoring
*   `logging` library for log management
*   `schedule` library for scheduling tasks (optional)

## System Monitoring Modules
---------------------------

### CPU Monitoring

*   **Module Name:** `cpu_monitor.py`
*   **Description:** Logs real-time CPU percentages
*   **Functions:**
    *   `get_cpu_percent()`: Returns the current CPU percentage
    *   `log_cpu_percent()`: Logs the current CPU percentage
*   **Example Code:**
    ```python
import psutil
import logging

def get_cpu_percent():
    return psutil.cpu_percent()

def log_cpu_percent():
    cpu_percent = get_cpu_percent()
    logging.info(f"CPU Percentage: {cpu_percent}%")
```

### RAM Monitoring

*   **Module Name:** `ram_monitor.py`
*   **Description:** Logs real-time RAM consumption metrics
*   **Functions:**
    *   `get_ram_usage()`: Returns the current RAM usage
    *   `log_ram_usage()`: Logs the current RAM usage
*   **Example Code:**
    ```python
import psutil
import logging

def get_ram_usage():
    return psutil.virtual_memory()

def log_ram_usage():
    ram_usage = get_ram_usage()
    logging.info(f"RAM Usage: {ram_usage.percent}%")
```

### Disk IO Monitoring

*   **Module Name:** `disk_io_monitor.py`
*   **Description:** Logs active disk IO status
*   **Functions:**
    *   `get_disk_io()`: Returns the current disk IO statistics
    *   `log_disk_io()`: Logs the current disk IO statistics
*   **Example Code:**
    ```python
import psutil
import logging

def get_disk_io():
    return psutil.disk_io_counters()

def log_disk_io():
    disk_io = get_disk_io()
    logging.info(f"Disk IO: read={disk_io.read_bytes}, write={disk_io.write_bytes}")
```

## Logging Module
------------------

*   **Module Name:** `logger.py`
*   **Description:** Manages log output and rotation
*   **Functions:**
    *   `init_logger()`: Initializes the logger
    *   `log_message()`: Logs a message
*   **Example Code:**
    ```python
import logging

def init_logger():
    logging.basicConfig(filename='system_monitor.log', level=logging.INFO)

def log_message(message):
    logging.info(message)
```

## Scheduling Module (Optional)
------------------------------

*   **Module Name:** `scheduler.py`
*   **Description:** Schedules tasks to run at regular intervals
*   **Functions:**
    *   `schedule_task()`: Schedules a task to run at a specified interval
*   **Example Code:**
    ```python
import schedule
import time

def schedule_task(task, interval):
    schedule.every(interval).seconds.do(task)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)
```

## Main Program
----------------

*   **File Name:** `main.py`
*   **Description:** Runs the system monitoring utility
*   **Example Code:**
    ```python
import cpu_monitor
import ram_monitor
import disk_io_monitor
import logger
import scheduler

def main():
    logger.init_logger()
    cpu_monitor.log_cpu_percent()
    ram_monitor.log_ram_usage()
    disk_io_monitor.log_disk_io()

    # Schedule tasks to run at regular intervals (optional)
    scheduler.schedule_task(cpu_monitor.log_cpu_percent, 1)
    scheduler.schedule_task(ram_monitor.log_ram_usage, 1)
    scheduler.schedule_task(disk_io_monitor.log_disk_io, 1)
    scheduler.run_schedule()

if __name__ == "__main__":
    main()
```

## Conclusion
--------------

This document outlines the core requirements and technical specifications for a lightweight local system monitoring utility in Python. The utility logs real-time CPU percentages, RAM consumption metrics, and active disk IO status. The code is structured into separate modules for each monitoring function, logging, and scheduling (optional). The main program runs the utility and schedules tasks to run at regular intervals (if desired).