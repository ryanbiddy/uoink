"""Backward-compatibility shim: yoink_mcp.py was renamed to uoink_mcp.py in
Uoink v2.1. Existing MCP client configs that still launch ``yoink_mcp.py`` (or
import it) keep working through the v2.x alias window; update them to
``uoink_mcp.py`` before v3, when this shim is removed.
"""

from uoink_mcp import *  # noqa: F401,F403
from uoink_mcp import mcp  # explicit re-export for the stdio entry point below


if __name__ == "__main__":
    mcp.run(transport="stdio")
