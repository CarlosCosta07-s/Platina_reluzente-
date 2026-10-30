#!/usr/bin/env python3
"""Run the repository's ROM-free Python test tiers.

Usage:
  python scripts/test.py --quick  Run the importer/cache/runtime fixture suites.
  python scripts/test.py --full   Run every Python test under tools/tests.

Both tiers use synthetic fixtures and must never require a commercial ROM,
firmware, extracted game assets, saves, or binary patches.
"""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tools" / "tests"
QUICK_MODULES = (
    "test_import_localization.py",
    "test_check_runtime_data.py",
    "test_prepare_native_runtime.py",
    "test_pin_native_dependencies.py",
    "test_verify_native_package.py",
    "test_smoke_test_native_startup.py",
)


def build_suite(tier: str) -> unittest.TestSuite:
    loader = unittest.TestLoader()
    if tier == "full":
        return loader.discover(start_dir=str(TESTS), pattern="test*.py")

    suite = unittest.TestSuite()
    for filename in QUICK_MODULES:
        if not (TESTS / filename).is_file():
            raise FileNotFoundError(f"Quick-test module is missing: {TESTS / filename}")
        suite.addTests(loader.discover(start_dir=str(TESTS), pattern=filename))
    return suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quick", action="store_true", help="Run the fast ROM-free fixture tier.")
    group.add_argument("--full", action="store_true", help="Run all Python tests (default).")
    args = parser.parse_args(argv)

    # Keep imports stable whether invoked from the repository root or elsewhere.
    sys.path.insert(0, str(ROOT))
    tier = "quick" if args.quick else "full"
    print(f"Platina Reluzente ROM-free test tier: {tier}", flush=True)
    print("No ROM, firmware, extracted game data, save, or patch is required.", flush=True)

    try:
        suite = build_suite(tier)
    except (OSError, ImportError) as error:
        print(f"Could not build the {tier} test suite: {error}", file=sys.stderr)
        return 2

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
