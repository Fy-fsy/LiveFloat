#!/usr/bin/env python3
"""Entry point for running LiveFloat from source or a PyInstaller build."""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller: everything is bundled.
    from app.main import main
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from app.main import main

if __name__ == "__main__":
    sys.exit(main())
