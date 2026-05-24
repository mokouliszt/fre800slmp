"""
fre800slmp - SLMP client for Mitsubishi FR-E800 series inverters.

Quick example:
    >>> from fre800slmp import FRE800Slmp
    >>> with FRE800Slmp("192.168.50.1", 5010) as inv:
    ...     inv.write("W7", 30)           # Pr.7 (acceleration time)
    ...     print(inv.read("W7"))
"""

from .address import Address, Device, parse_address
from .client import FRE800Slmp, SlmpError

__version__ = "0.1.0"

__all__ = [
    "FRE800Slmp",
    "SlmpError",
    "Device",
    "Address",
    "parse_address",
    "__version__",
]
