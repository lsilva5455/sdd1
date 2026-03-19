"""Unit tests for the startup banner module.

Tests cover config loading, capacity extraction, system info gathering,
the ASCII art constant, and the full banner printing.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils.banner import (
    SIGNAL_BARS_ART,
    _extract_capacity_info,
    _get_system_info,
    _load_config,
    print_startup_banner,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_config() -> dict:
    """Sample config matching real config.json structure."""
    return {
        "simbanks": [
            {
                "control_port": "COM19",
                "modems": [
                    {"port": "COM4", "col": "01"},
                    {"port": "COM3", "col": "02"},
                ],
            },
            {
                "control_port": "COM20",
                "modems": [
                    {"port": "COM11", "col": "01"},
                    {"port": "COM12", "col": "02"},
                ],
            },
        ],
        "filas": 16,
        "nodo": "N99",
        "flask_port": 8080,
    }


@pytest.fixture
def sample_config_file(tmp_path, sample_config) -> str:
    """Write sample config to a temp file and return its path."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(sample_config), encoding="utf-8")
    return str(config_file)


# ---------------------------------------------------------------------------
# Tests: _load_config
# ---------------------------------------------------------------------------


def test_should_load_valid_config_when_file_exists(
    sample_config_file,
    sample_config,
):
    """Loads parsed dict when file exists and is valid JSON."""
    result = _load_config(sample_config_file)
    assert result == sample_config


def test_should_return_empty_dict_when_file_not_found():
    """Returns {} when the file does not exist."""
    result = _load_config("/nonexistent/path/config.json")
    assert result == {}


def test_should_return_empty_dict_when_json_invalid(tmp_path):
    """_load_config returns {} when the file contains invalid JSON."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ not valid json !!!", encoding="utf-8")
    result = _load_config(str(bad_file))
    assert result == {}


# ---------------------------------------------------------------------------
# Tests: _extract_capacity_info
# ---------------------------------------------------------------------------


def test_should_extract_correct_counts_from_valid_config(sample_config):
    """Extracts 2 SimBanks, 4 modems, 16 rows, capacity 256."""
    result = _extract_capacity_info(sample_config)
    assert result["simbanks"] == "2"
    assert result["modems"] == "4"
    assert result["rows"] == "16"
    assert result["capacity"] == "256"
    assert result["node"] == "N99"
    assert result["flask_port"] == "8080"


def test_should_return_na_when_config_empty():
    """All fields return 'N/A' or defaults when config is empty."""
    result = _extract_capacity_info({})
    assert result["simbanks"] == "0"
    assert result["modems"] == "0"
    assert result["rows"] == "N/A"
    assert result["capacity"] == "N/A"
    assert result["node"] == "N/A"


def test_should_return_na_when_simbanks_key_missing():
    """Handles config with filas but no simbanks key."""
    result = _extract_capacity_info({"filas": 8})
    assert result["simbanks"] == "0"
    assert result["modems"] == "0"
    assert result["capacity"] == "N/A"


# ---------------------------------------------------------------------------
# Tests: _get_system_info
# ---------------------------------------------------------------------------


def test_should_return_platform_info():
    """_get_system_info returns a non-empty platform string."""
    result = _get_system_info()
    assert "platform" in result
    assert len(result["platform"]) > 0


def test_should_return_ip_address():
    """_get_system_info returns a string for ip_address."""
    result = _get_system_info()
    assert "ip_address" in result
    assert isinstance(result["ip_address"], str)


@patch("utils.banner.socket.gethostbyname", side_effect=OSError("no network"))
def test_should_return_na_when_network_unavailable(mock_socket):
    """_get_system_info returns 'N/A' for IP when network fails."""
    result = _get_system_info()
    assert result["ip_address"] == "N/A"


# ---------------------------------------------------------------------------
# Tests: SIGNAL_BARS_ART
# ---------------------------------------------------------------------------


def test_signal_bars_art_should_not_be_empty():
    """The ASCII art constant is not empty."""
    assert len(SIGNAL_BARS_ART.strip()) > 0


def test_signal_bars_art_should_contain_asterisks():
    """The ASCII art uses '*' characters."""
    assert "*" in SIGNAL_BARS_ART


def test_signal_bars_art_width_should_be_under_60_chars():
    """No line in the ASCII art exceeds 60 characters."""
    for line in SIGNAL_BARS_ART.splitlines():
        assert len(line) <= 60, f"Line too wide ({len(line)} chars): {line!r}"


# ---------------------------------------------------------------------------
# Tests: print_startup_banner
# ---------------------------------------------------------------------------


def test_should_print_banner_without_crashing(sample_config_file, capsys):
    """Banner prints without error and output contains 'mp-core'."""
    print_startup_banner(config_path=sample_config_file)
    captured = capsys.readouterr()
    assert "mp-core" in captured.out


def test_should_print_banner_with_missing_config(capsys):
    """Banner runs with missing config; output has 'N/A'."""
    print_startup_banner(config_path="/nonexistent/config.json")
    captured = capsys.readouterr()
    assert "N/A" in captured.out
