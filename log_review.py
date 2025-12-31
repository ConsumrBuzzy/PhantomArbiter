#!/usr/bin/env python3
"""
Log Review Tool v1.0 (V133)
===========================
Scan recent PhantomArbiter logs for errors, warnings, and debug messages.

Usage:
    python log_review.py              # Last run only
    python log_review.py --all        # All recent logs (last 5)
    python log_review.py --errors     # Errors only
    python log_review.py --tail 50    # Last 50 lines of each log
    python log_review.py --grep "SharedPriceCache"  # Search for pattern

Examples:
    python log_review.py --errors --all
    python log_review.py --grep "RPC" --tail 100
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Resolve log directory
SCRIPT_DIR = Path(__file__).parent
LOG_DIR = SCRIPT_DIR / "logs"


# ANSI Colors (works on Windows 10+ with ENABLE_VIRTUAL_TERMINAL_PROCESSING)
class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def enable_windows_ansi():
    """Enable ANSI escape codes on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def get_log_files(max_files: int = 5) -> List[Path]:
    """Get the most recent log files from multiple possible locations."""
    log_dirs = [LOG_DIR, SCRIPT_DIR / "src" / "logs"]
    log_files = []

    for d in log_dirs:
        if d.exists():
            log_files.extend(list(d.glob("phantom_*.log")))
            # Also include the legacy static phantom.log if it exists and has content
            static_log = d / "phantom.log"
            if static_log.exists() and static_log.stat().st_size > 0:
                log_files.append(static_log)

    # Sort by modification time (newest first)
    log_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return log_files[:max_files]


def classify_line(line: str) -> Optional[str]:
    """Classify a log line by severity."""
    line_upper = line.upper()
    if "[ERROR]" in line_upper or "❌" in line or "🛑" in line:
        return "ERROR"
    elif "[WARNING]" in line_upper or "⚠️" in line:
        return "WARNING"
    elif "[DEBUG]" in line_upper:
        return "DEBUG"
    elif "✅" in line or "[SUCCESS]" in line_upper:
        return "SUCCESS"
    return None


def colorize_line(line: str, severity: Optional[str]) -> str:
    """Apply color based on severity."""
    if severity == "ERROR":
        return f"{Colors.RED}{line}{Colors.RESET}"
    elif severity == "WARNING":
        return f"{Colors.YELLOW}{line}{Colors.RESET}"
    elif severity == "DEBUG":
        return f"{Colors.DIM}{line}{Colors.RESET}"
    elif severity == "SUCCESS":
        return f"{Colors.GREEN}{line}{Colors.RESET}"
    return line


def scan_log(log_path: Path, args) -> dict:
    """Scan a single log file and return statistics."""
    stats = {"errors": 0, "warnings": 0, "total": 0, "matched": []}

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"{Colors.RED}Error reading {log_path.name}: {e}{Colors.RESET}")
        return stats

    # Apply tail filter
    if args.tail:
        lines = lines[-args.tail :]

    for line_num, line in enumerate(lines, 1):
        line = line.rstrip()
        severity = classify_line(line)

        # Count severity
        if severity == "ERROR":
            stats["errors"] += 1
        elif severity == "WARNING":
            stats["warnings"] += 1
        stats["total"] += 1

        # Apply filters
        show_line = False

        if args.errors and severity == "ERROR":
            show_line = True
        elif args.warnings and severity in ["ERROR", "WARNING"]:
            show_line = True
        elif args.grep and args.grep.lower() in line.lower():
            show_line = True
        elif not args.errors and not args.warnings and not args.grep:
            # Default: show errors and warnings
            if severity in ["ERROR", "WARNING"]:
                show_line = True

        if show_line:
            stats["matched"].append((line_num, line, severity))

    return stats


def print_log_header(log_path: Path):
    """Print a log file header."""
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
    size_kb = log_path.stat().st_size / 1024
    print(f"\n{Colors.CYAN}{'═' * 60}{Colors.RESET}")
    print(f"{Colors.BOLD}📋 {log_path.name}{Colors.RESET}")
    print(
        f"{Colors.DIM}   Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')} | Size: {size_kb:.1f} KB{Colors.RESET}"
    )
    print(f"{Colors.CYAN}{'═' * 60}{Colors.RESET}")


def main():
    enable_windows_ansi()

    parser = argparse.ArgumentParser(
        description="Scan PhantomArbiter logs for errors and patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Scan all recent logs (default: last run only)",
    )
    parser.add_argument("--errors", "-e", action="store_true", help="Show errors only")
    parser.add_argument(
        "--warnings", "-w", action="store_true", help="Show warnings and errors"
    )
    parser.add_argument(
        "--tail", "-t", type=int, metavar="N", help="Show only last N lines of each log"
    )
    parser.add_argument(
        "--grep",
        "-g",
        type=str,
        metavar="PATTERN",
        help="Search for pattern (case-insensitive)",
    )
    parser.add_argument(
        "--summary",
        "-s",
        action="store_true",
        help="Show summary only (no line output)",
    )

    args = parser.parse_args()

    # Get log files
    max_files = 5 if args.all else 1
    log_files = get_log_files(max_files)

    if not log_files:
        print(f"{Colors.YELLOW}⚠️  No log files found in {LOG_DIR}{Colors.RESET}")
        print("Run the bot first to generate logs.")
        return 1

    print(f"\n{Colors.BOLD}🔍 PhantomArbiter Log Review{Colors.RESET}")
    print(f"{Colors.DIM}   Found {len(log_files)} log file(s){Colors.RESET}")

    total_errors = 0
    total_warnings = 0

    for log_path in log_files:
        print_log_header(log_path)
        stats = scan_log(log_path, args)

        total_errors += stats["errors"]
        total_warnings += stats["warnings"]

        if not args.summary:
            for line_num, line, severity in stats["matched"]:
                colored = colorize_line(line, severity)
                print(f"{Colors.DIM}L{line_num:4d}{Colors.RESET} {colored}")

        # Per-file summary
        err_color = Colors.RED if stats["errors"] > 0 else Colors.GREEN
        warn_color = Colors.YELLOW if stats["warnings"] > 0 else Colors.GREEN
        print(
            f"\n   {err_color}Errors: {stats['errors']}{Colors.RESET} | "
            f"{warn_color}Warnings: {stats['warnings']}{Colors.RESET} | "
            f"Matched: {len(stats['matched'])}/{stats['total']}"
        )

    # Grand total
    print(f"\n{Colors.CYAN}{'─' * 60}{Colors.RESET}")
    err_symbol = "🔴" if total_errors > 0 else "✅"
    warn_symbol = "🟡" if total_warnings > 0 else "✅"
    print(
        f"{Colors.BOLD}Summary:{Colors.RESET} {err_symbol} {total_errors} errors | "
        f"{warn_symbol} {total_warnings} warnings"
    )

    return 1 if total_errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
