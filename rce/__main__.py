"""Module execution entry point for `python -m rce`."""

from __future__ import annotations

import sys
from rce.cli import main

if __name__ == "__main__":
    sys.exit(main())
