#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Analyze previously collected Encre benchmark results.

This is a thin command-line wrapper around
:func:`encre.eval.benchmark_suite.analyze_benchmark_results`. It reads a
benchmark results JSON file (as produced by ``runner.py``), computes a gap
analysis of where the flagship agent falls short, and prints (and optionally
writes) the analysis as JSON.

Usage:
    python analyze_results.py --input results.json [--output analysis.json]
"""

import argparse
import json
from pathlib import Path

from encre.eval.benchmark_suite import analyze_benchmark_results


# This script intentionally stays thin: all analysis logic lives in
# ``encre.eval.benchmark_suite.analyze_benchmark_results`` so it can be reused
# programmatically. Here we only handle CLI I/O and shape normalization.


def main() -> None:
    """Parse CLI arguments, load benchmark results, and emit the analysis.

    Reads the JSON file referenced by ``--input`` (only the ``results`` array
    inside it is used), runs the gap analysis, and either writes the rendered
    analysis to ``--output`` (when provided) or prints it to stdout.

    Args:
        (none) - Behavior is driven entirely by ``sys.argv`` via
            :mod:`argparse`.

    Raises:
        FileNotFoundError: If the ``--input`` file does not exist.
        json.JSONDecodeError: If the input file is not valid JSON.
    """
    parser = argparse.ArgumentParser(description="Analyze benchmark results for flagship-agent gaps.")
    parser.add_argument("--input", required=True, help="Path to benchmark results JSON.")
    parser.add_argument("--output", default="", help="Optional path to write analysis JSON.")
    args = parser.parse_args()

    # Load the raw payload and tolerate both a bare results array and a
    # wrapping object; fall back to an empty list when the shape is unexpected.
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = payload.get("results", []) if isinstance(payload, dict) else []
    # Delegate the actual gap analysis to the shared library function.
    analysis = analyze_benchmark_results(results)
    rendered = json.dumps(analysis, ensure_ascii=False, indent=2)

    if args.output:
        # Persist to disk when an output path was supplied.
        Path(args.output).write_text(rendered, encoding="utf-8")
    # Always echo the analysis to stdout for pipelines/logging.
    print(rendered)


if __name__ == "__main__":
    main()
