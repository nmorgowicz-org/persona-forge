"""``python -m persona_forge`` — same entry point as the ``persona-forge`` console script."""

from __future__ import annotations

import sys

from persona_forge.cli import main

if __name__ == "__main__":
    sys.exit(main())
