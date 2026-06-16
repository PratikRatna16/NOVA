```python
#!/usr/bin/env python3
"""
TCP Port Scanner CLI

Performs TCP connect scans against an authorized target and reports open/closed
status plus TCP handshake response time for open ports.

Security note: only scan systems you own or have explicit permission to test.
This tool does not send payloads, attempt authentication, or use stealth techniques.

For hostnames that resolve to multiple addresses, verbose mode displays all
resolved TCP addresses. The scanner uses the first IPv4 address if available;
otherwise it uses the first resolved address. Pass an explicit IP address to
control the exact target address.
"""

from __future__ import annotations

import argparse
import errno
import math
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

MIN_PORT = 1
MAX_PORT = 65535
MAX_WORKERS = 128

# Some platforms do not define every errno constant.
ECONNREFUSED = getattr(errno, "ECONNREFUSED", None)


@dataclass(frozen=True)
class ScanResult:
    """Result for a single port scan attempt."""

    port: int
    status: str
    response_ms: Optional[float]
    detail: Optional[str] = None


def parse_port_range(raw_range: str) -> List[int]:
    """
    Parse a port range expression.

    Supported forms:
      - "80"
      - "80,443,8080"
      - "1-1024"
      - "22,80,443,8000-8010"

    Raises:
        ValueError: If the input is malformed or outside 1-65535.
    """
    if not raw_range or not raw_range.strip():
        raise ValueError("Port range cannot be empty.")

    ports: List[int] = []
    tokens = [token.strip() for token in raw_range.split(",")]

    if any(not token for token in tokens):
        raise ValueError("Port range contains an empty entry; expected e.g. 1-1024 or 80,443.")

    for token in tokens:
        if "-" in token:
            if token.count("-") != 1:
                raise ValueError(
                    "Invalid port range segment {!r}; expected a single start-end range.".format(token)
                )

            start_text, end_text = token.split("-", 1)

            try:
                start = int(start_text, 10)
                end = int(end_text, 10)
            except ValueError as exc:
                raise ValueError("Invalid port range segment {!r}; ports must be integers.".format(token)) from exc

            if start > end:
                raise ValueError("Invalid port range segment {!r}; start port is greater than end port.".format(token))

            if not (MIN_PORT <= start <= MAX_PORT and MIN_PORT <= end <= MAX_PORT):
                raise ValueError("Invalid port range segment {!r}; ports must be between 1 and 65535.".format(token))

            ports.extend(range(start, end + 1))
        else:
            try:
                port = int(token, 10)
            except ValueError as exc:
                raise ValueError("Invalid port {!r}; ports must be integers.".format(token)) from exc

            if not (MIN_PORT <= port <= MAX_PORT):
                raise ValueError("Invalid port {!r}; ports must be between 1 and 65535.".format(port))

            ports.append(port)

    # Remove duplicates while keeping output predictable.
    return sorted(set(ports))


def parse_timeout(value: str) -> float:
    """Validate and parse timeout seconds."""
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds.") from exc

    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number of seconds.")

    return timeout


def parse_workers(value: str) -> int:
    """Validate and parse worker count."""
    try:
        workers = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("workers must be a positive integer.") from exc

    if workers < 1:
        raise argparse.ArgumentTypeError("workers must be a positive integer.")

    return workers


def normalize_target(target: str) -> str:
    """Normalize user-provided target input."""
    target = (target or "").strip()

    # Allow bracketed IPv6 literals such as [::1].
    if target.startswith("[") and target.endswith("]"):
        target = target[1:-1].strip()

    if not target:
        raise ValueError("Target cannot be empty.")

    return target


def resolve_tcp_addresses(target: str) -> List[Tuple[int, Tuple[Any, ...]]]:
    """
    Resolve a hostname or IP address to TCP-capable socket addresses.

    Returns:
        A list of (address_family, sockaddr) tuples.
    """
    try:
        infos = socket.getaddrinfo(
            target,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError("Could not resolve target {!r}: {}".format(target, exc)) from exc
    except OSError as exc:
        raise ValueError("Could not resolve target {!r}: {}".format(target, exc)) from exc

    addresses: List[Tuple[int, Tuple[Any, ...]]] = []
    seen = set()

    for family, socktype, _proto, _canonname, sockaddr in infos:
        if int(socktype) != int(socket.SOCK_STREAM):
            continue

        key = (int(family), sockaddr)
        if key in seen:
            continue

        seen.add(key)
        addresses.append((int(family), sockaddr))

    if not addresses:
        raise ValueError("No TCP addresses found for target {!r}.".format(target))

    return addresses


def select_scan_address(addresses: Sequence[Tuple[int, Tuple[Any, ...]]]) -> Tuple[int, Tuple[Any, ...]]:
    """
    Choose the address to scan.

    Prefer IPv4 when a hostname resolves to both IPv4 and IPv6, because IPv4 is
    commonly reachable in mixed environments. IPv6-only targets still work.
    """
    for family, sockaddr in addresses:
        if family == socket.AF_INET:
            return family, sockaddr

    return addresses[0]


def format_address(family: int, sockaddr: Sequence[Any]) -> str:
    """Format a socket address for display."""
    if len(sockaddr) < 2:
        return str(sockaddr)

    host = str(sockaddr[0])
    port = int(sockaddr[1])

    if family == socket.AF_INET6:
        return "[{}]:{}".format(host, port)

    return "{}:{}".format(host, port)


def sockaddr_with_port(sockaddr: Sequence[Any], port: int) -> Tuple[Any, ...]:
    """
    Add a scan port to a sockaddr returned by getaddrinfo.

    getaddrinfo is called with service=None, so the original sockaddr has port 0.
    """
    if len(sockaddr) == 2:
        return (sockaddr[0], port)

    if len(sockaddr) == 4:
        return (sockaddr[0], port, sockaddr[2], sockaddr[3])

    raise ValueError("Unsupported socket address format: {!r}".format(sockaddr))


def default_worker_count() -> int:
    """Return a safe automatic worker count."""
    cpu_count = os.cpu_count() or 2
    return min(MAX_WORKERS, max(1, cpu_count * 4))


def effective_worker_count(requested: Optional[int], total_ports: int) -> int:
    """Resolve requested worker count with a safe upper bound."""
    workers = requested if requested is not None else default_worker_count()
    return min(workers, MAX_WORKERS, max(1, total_ports))


def scan_port(
    family: int,
    base_sockaddr: Sequence[Any],
    port: int,
    timeout: float,
) -> ScanResult:
    """
    Scan a single TCP port.

    Response time is measured as the time required to complete the TCP handshake.
    Closed and filtered ports report N/A for response time.
    """
    start = time.perf_counter()
    sock: Optional[socket.socket] = None

    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(sockaddr_with_port(base_sockaddr, port))

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return ScanResult(port=port, status="Open", response_ms=elapsed_ms)

    except socket.timeout as exc:
        return ScanResult(
            port=port,
            status="Filtered",
            response_ms=None,
            detail=str(exc) or "timeout",
        )

    except ConnectionRefusedError as exc:
        return ScanResult(
            port=port,
            status="Closed",
            response_ms=None,
            detail=str(exc) or "connection refused",
        )

    except OSError as exc:
        code = getattr(exc, "errno", None)
        status = "Closed" if code == ECONNREFUSED else "Filtered"
        message = exc.strerror or exc.__class__.__name__

        if code is not None:
            message = "{} (errno {})".format(message, code)

        return ScanResult(
            port=port,
            status=status,
            response_ms=None,
            detail=message,
        )

    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                # Socket close failure should not mask the scan result.
                pass


def scan_ports(
    address: Tuple[int, Sequence[Any]],
    ports: Sequence[int],
    timeout: float,
    workers: Optional[int],
    verbose: bool,
) -> List[ScanResult]:
    """Scan all requested ports using a bounded thread pool."""
    total_ports = len(ports)
    if total_ports == 0:
        return []

    family, base_sockaddr = address
    max_workers = effective_worker_count(workers, total_ports)

    results: List[ScanResult] = []
    completed = 0
    lock = threading.Lock()
    progress_interval = max(1, total_ports // 10)

    def mark_complete() -> None:
        nonlocal completed

        with lock:
            completed += 1

            if verbose and (completed == total_ports or completed % progress_interval == 0):
                percent = completed / total_ports * 100
                print(
                    "\rScanned {}/{} ports ({:.1f}%)".format(completed, total_ports, percent),
                    end="",
                    flush=True,
                )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_port = {
            executor.submit(scan_port, family, base_sockaddr, port, timeout): port
            for port in ports
        }

        for future in as_completed(future_to_port):
            port = future_to_port[future]

            try:
                result = future.result()
            except Exception as exc:
                result = ScanResult(
                    port=port,
                    status="Error",
                    response_ms=None,
                    detail=str(exc),
                )

            results.append(result)
            mark_complete()

    if verbose:
        print()

    return sorted(results, key=lambda item: item.port)


def format_response_time(response_ms: Optional[float]) -> str:
    """Format response time for table output."""
    if response_ms is None:
        return "N/A"

    if response_ms < 10:
        return "{:.2f}ms".format(response_ms)

    if response_ms < 100:
        return "{:.1f}ms".format(response_ms)

    return "{:.0f}ms".format(response_ms)


def print_results(results: Sequence[ScanResult]) -> None:
    """Print scan results in the requested table format."""
    if not results:
        print("No ports were scanned.")
        return

    print()
    print(f"{'Port':<5} | {'Status':<8} | Response Time")
    print(f"{'-' * 5}-|{'-' * 8}-|{'-' * 13}")

    for result in results:
        print(
            "{:<5} | {:<8} | {:>13}".format(
                result.port,
                result.status,
                format_response_time(result.response_ms),
            )
        )


def print_summary(results: Sequence[ScanResult]) -> None:
    """Print a concise status summary."""
    counts = {"Open": 0, "Closed": 0, "Filtered": 0, "Error": 0}

    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    print()
    print(
        "Summary: {} open, {} closed, {} filtered/timeout".format(
            counts.get("Open", 0),
            counts.get("Closed", 0),
            counts.get("Filtered", 0),
        )
    )

    if counts.get("Error", 0):
        print("         {} error(s)".format(counts["Error"]))

    if results and counts.get("Open", 0) == 0:
        print("No open ports found.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Scan TCP ports on an authorized IP address or hostname.",
        epilog="Only scan systems you own or have explicit permission to test. This tool performs TCP connect scans.",
    )

    parser.add_argument(
        "-i",
        "--target",
        required=True,
        metavar="HOST",
        help="IP address or hostname to scan.",
    )

    parser.add_argument(
        "-p",
        "--ports",
        required=True,
        metavar="RANGE",
        help="Port range to scan, e.g. 1-1024 or 80,443,8000-8010.",
    )

    parser.add_argument(
        "-t",
        "--timeout",
        type=parse_timeout,
        default=1.0,
        metavar="SECONDS",
        help="Maximum seconds to wait for a TCP connection. Default: 1.0.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show scan progress, resolved addresses, and configuration.",
    )

    parser.add_argument(
        "--workers",
        type=parse_workers,
        default=None,
        metavar="N",
        help="Concurrent port checks. Default: auto, capped at {}.".format(MAX_WORKERS),
    )

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        target = normalize_target(args.target)
        ports = parse_port_range(args.ports)
        addresses = resolve_tcp_addresses(target)
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    except Exception as exc:
        print("Unexpected error while preparing scan: {}".format(exc), file=sys.stderr)
        return 1

    family, base_sockaddr = select_scan_address(addresses)
    effective_workers = effective_worker_count(args.workers, len(ports))

    if args.verbose:
        print("TCP Port Scanner")
        print("Target: {}".format(target))
        print("Resolved TCP addresses:")
        for address_family, sockaddr in addresses:
            print("  - {}".format(format_address(address_family, sockaddr)))
        print("Using address: {}".format(format_address(family, base_sockaddr)))
        print("Ports to scan: {}".format(len(ports)))
        print("Timeout: {}s".format(args.timeout))
        print("Workers: {}".format(effective_workers))
        print()

    try:
        results = scan_ports(
            address=(family, base_sockaddr),
            ports=ports,
            timeout=args.timeout,
            workers=effective_workers,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\nScan interrupted by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print("Unexpected error during scan: {}".format(exc), file=sys.stderr)
        return 1

    try:
        print_results(results)
        print_summary(results)
    except BrokenPipeError:
        # Common when piping output to tools like `head`.
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```