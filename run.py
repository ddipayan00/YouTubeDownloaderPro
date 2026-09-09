#!/usr/bin/env python3
"""Convenience launcher: ``python run.py`` is the same as ``python -m ytdpro``."""

from ytdpro.app import main

if __name__ == "__main__":
    raise SystemExit(main())
