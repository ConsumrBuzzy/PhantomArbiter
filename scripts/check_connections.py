#!/usr/bin/env python3
"""
Connection Health Check - Station Preflight

Tests all external connections from .env and reports status.
Run this when setting up a new station or debugging connectivity.

Usage:
    python scripts/check_connections.py
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.shared.system.connection_validator import validate_sync


def main():
    print("\n🔍 Testing connections from .env...")
    
    report = validate_sync()
    report.print_report()
    
    # Return exit code based on health
    summary = report.summary()
    
    if summary["failed"] > 0:
        print("💡 Tip: Check your .env file and network connectivity.")
        return 1
    elif summary["missing"] > 0:
        print("💡 Tip: Some optional services not configured.")
        return 0
    else:
        return 0


if __name__ == "__main__":
    sys.exit(main())
