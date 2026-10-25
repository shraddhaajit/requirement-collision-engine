"""Command-Line Interface for the Requirement Collision Engine (RCE) (Phase 6).

Provides a reusable CLI to run static collision detection and change-impact analysis
across arbitrary Python projects without modifying RCE source code.

Execution:
    python -m rce [OPTIONS]
    python -m rce.cli [OPTIONS]

Documentation:
    Input Formats:
      - Requirements: Markdown file containing headings formatted as:
            ### REQ-01 — Requirement Title
            or
            ### REQ-01: Requirement Title
            followed by the requirement description text.
      - Traceability Tags: Python docstrings containing explicit tags:
            \"\"\"Function docstring summary.

            TRACE: REQ-01, REQ-02
            \"\"\"
    Static Analysis Guarantee:
      Analyzes source code via Python's built-in AST without importing,
      loading, or executing project files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from rce.engine import (
    STATUS_FAILED,
    EngineResult,
    format_engine_result,
    run_engine,
)

__version__ = "1.0.0"

_CLI_EPILOG = """
Documentation & Input Formats:
  Requirements Format:
    Markdown file (.md) containing headings such as:
      ### REQ-01 — Title
      or
      ### REQ-01: Title
      followed by the requirement specification prose.

  Traceability Tags:
    Python function, method, or class docstrings containing explicit tags:
      \"\"\"Implementation description.

      TRACE: REQ-01, REQ-03
      \"\"\"

  Static Analysis Safety:
    RCE inspects code purely using abstract syntax trees (ast module).
    Project source code is NEVER imported or executed.
"""


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser for RCE."""
    parser = argparse.ArgumentParser(
        prog="rce",
        description="Requirement Collision Engine (RCE) — Automated requirement collision detection and change-impact analysis for Python projects.",
        epilog=_CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--project-root",
        "-r",
        type=str,
        default=".",
        help="Path to the target project root directory (default: current directory).",
    )

    parser.add_argument(
        "--requirements",
        type=str,
        default=None,
        help="Path to requirements Markdown file (auto-detected if omitted).",
    )

    parser.add_argument(
        "--source-dirs",
        "-s",
        nargs="+",
        default=None,
        help="One or more source directories relative to project root to analyze.",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json"],
        default="text",
        help="Output format: 'text' (human-readable) or 'json' (machine-readable). Default: text.",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Optional path to write analysis output report.",
    )

    parser.add_argument(
        "--impact",
        "-i",
        type=str,
        default=None,
        help="Target requirement ID (e.g. 'REQ-01'), function name, module, or collision ID for change-impact analysis.",
    )

    parser.add_argument(
        "--max-depth",
        "-d",
        type=int,
        default=5,
        help="Maximum traversal depth for change-impact analysis (default: 5). Must be a positive integer.",
    )

    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"Requirement Collision Engine (RCE) v{__version__}",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for RCE.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 for success, non-zero for error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # 1. Validate max-depth
    if args.max_depth <= 0:
        sys.stderr.write(f"Error: --max-depth must be a positive integer, got {args.max_depth}.\n")
        return 2

    # 2. Run Engine
    result: EngineResult = run_engine(
        project_root=args.project_root,
        requirements_path=args.requirements,
        source_dirs=args.source_dirs,
        impact_target=args.impact,
        max_depth=args.max_depth,
    )

    # 3. Format Output
    if args.format == "json":
        output_content = result.to_json(indent=2)
    else:
        output_content = format_engine_result(result)

    # 4. Write Output (File or Stdout)
    if args.output:
        try:
            out_path = Path(args.output).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_content, encoding="utf-8")
            if args.format != "json":
                print(f"Report written to: {out_path}")
        except Exception as exc:
            sys.stderr.write(f"Error writing output to '{args.output}': {exc}\n")
            return 1
    else:
        # Machine-readable JSON or text output to stdout safely across terminal encodings
        try:
            sys.stdout.write(output_content + "\n")
            sys.stdout.flush()
        except UnicodeEncodeError:
            sys.stdout.buffer.write(output_content.encode("utf-8", errors="replace") + b"\n")
            sys.stdout.buffer.flush()

    # 5. Return appropriate exit code
    if result.status == STATUS_FAILED or not result.success:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
