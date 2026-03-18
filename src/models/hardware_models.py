"""
STUB / SCAFFOLD — Not used in production.

This module defines dataclass models for hardware entities. These are placeholder
domain models for a future DDD refactoring. Production code currently uses plain
dictionaries loaded from config.json and signal_data.csv.

Production data structures: config.json (simbanks), data/signal_data.csv
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SignalData:
    timestamp: str
    signal_strength: int
    quality: int


@dataclass
class Modem:
    port: str
    model: str
    signal_data: List[SignalData]


@dataclass
class SimBank:
    control_port: str
    modems: List[Modem]
    rows: int
    columns: int


@dataclass
class HardwareModels:
    sim_bank: SimBank
    modems: List[Modem]
