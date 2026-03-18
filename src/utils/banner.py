"""Startup banner module for mp-core.

Displays an ASCII art signal bars icon and colored system information
when the program launches.
"""

import json
import os
import platform
import socket
from datetime import datetime
from typing import Any

from colorama import Fore, init

from version import __version__

SIGNAL_BARS_ART: str = r"""
               *
          *    *
     *    *    *
*    *    *    *
*    *    *    *
*____*____*____*
"""


def _load_config(config_path: str) -> dict[str, Any]:
    """Load config.json safely, returning empty dict on failure.

    Args:
        config_path: Path to the configuration JSON file.

    Returns:
        Parsed configuration dictionary, or empty dict on error.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _get_system_info() -> dict[str, str]:
    """Gather platform and IP address information.

    Returns:
        Dictionary with 'platform' and 'ip_address' keys.
    """
    os_info = f"{platform.system()} {platform.release()}"
    try:
        ip_address = socket.gethostbyname(socket.gethostname())
    except (socket.gaierror, OSError):
        ip_address = "N/A"

    return {
        "platform": os_info,
        "ip_address": ip_address,
    }


def _extract_capacity_info(config: dict[str, Any]) -> dict[str, str]:
    """Extract capacity info from config.

    Handles the array-based SimBanks format:
    ``"simbanks": [{"control_port": "COMx", "modems": [...]}]``

    Args:
        config: Parsed configuration dictionary.

    Returns:
        Dictionary with capacity-related fields as strings.
    """
    simbanks = config.get("simbanks", [])
    simbank_count = len(simbanks)
    modem_count = sum(len(sb.get("modems", [])) for sb in simbanks)
    rows = config.get("filas", "N/A")

    if isinstance(rows, int) and simbank_count > 0:
        # Each SimBank has 8 slots, total capacity = simbanks * 8 * rows
        capacity = str(simbank_count * 8 * rows)
    else:
        capacity = "N/A"

    node = str(config.get("node", os.environ.get("MP_NODE", "N/A")))
    flask_port = str(config.get("flask_port", "5000"))

    return {
        "simbanks": str(simbank_count),
        "modems": str(modem_count),
        "rows": str(rows),
        "capacity": capacity,
        "node": node,
        "flask_port": flask_port,
    }


def print_startup_banner(config_path: str = "config.json") -> None:
    """Print the startup banner with ASCII art and colored system information.

    Displays signal bars ASCII art, program metadata, hardware capacity,
    and system information using colorama for colored output.

    Args:
        config_path: Path to the configuration JSON file.
            Defaults to ``config.json`` in the current working directory.
    """
    init(autoreset=True)

    # ASCII art in cyan
    print(f"{Fore.CYAN}{SIGNAL_BARS_ART}")

    # Load data sources
    config = _load_config(config_path)
    system_info = _get_system_info()
    capacity_info = _extract_capacity_info(config)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Program name and version (green)
    print(f"{Fore.GREEN}  mp-core v{__version__}")
    print()

    # Capacity data (yellow)
    print(f"{Fore.YELLOW}  SimBanks    : {capacity_info['simbanks']}")
    print(f"{Fore.YELLOW}  Modems      : {capacity_info['modems']}")
    print(f"{Fore.YELLOW}  Rows        : {capacity_info['rows']}")
    capacity = capacity_info["capacity"]
    print(f"{Fore.YELLOW}  Capacity    : {capacity} SIM slots")
    print()

    # System info (white)
    print(f"{Fore.WHITE}  Date/Time   : {timestamp}")
    print(f"{Fore.WHITE}  Platform    : {system_info['platform']}")
    print(f"{Fore.WHITE}  IP Address  : {system_info['ip_address']}")
    print(f"{Fore.WHITE}  Flask Port  : {capacity_info['flask_port']}")
    print()

    # Node identifier (magenta)
    print(f"{Fore.MAGENTA}  Node        : {capacity_info['node']}")
    print()

    # Separator
    print(f"{Fore.CYAN}{'=' * 50}")
    print()
