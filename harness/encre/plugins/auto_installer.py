"""Auto-discovery helper for bundled EA tool packages.

Discovery is directory-driven: the :mod:`encre.plugins.ea_scan` scanner walks
``ea_tools/`` and makes every ``ea-tool-*`` package importable (prepending its
directory to ``sys.path`` when needed) — in development and inside PyInstaller
frozen bundles alike.  No pip install step is required and no package name is
hardcoded here.
"""
from __future__ import annotations

import importlib
from typing import Any

from encre.logging_config import get_logger
from encre.plugins.ea_scan import iter_ea_packages

logger = get_logger("encre.plugins.auto_installer")


def ensure_ea_tools_installed() -> dict[str, bool]:
    """Make every bundled EA package importable.

    Returns dict mapping module_name → importable (bool).  Packages are
    resolved by scanning the ``ea_tools/`` tree; each package directory is
    added to ``sys.path`` when the module is not already importable.
    """
    results: dict[str, bool] = {}
    for pkg in iter_ea_packages():
        try:
            importlib.import_module(pkg.module_name)
            results[pkg.module_name] = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("EA package %s is not importable: %s", pkg.module_name, exc)
            results[pkg.module_name] = False
    return results


# Kept for backward compatibility with callers that expect a module-level
# MANDATORY_PACKAGES mapping.  The authoritative source is the directory scan.
def mandatory_packages() -> dict[str, str]:
    """Return module → tier for every bundled mandatory EA package."""
    return {
        pkg.module_name: pkg.tier
        for pkg in iter_ea_packages()
        if pkg.tier == "mandatory"
    }
