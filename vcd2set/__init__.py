"""VCD2Set - Convert VCD signals to sets of time points.

This package provides tools for analyzing Verilog Value Change Dump (VCD) files
and extracting time points where specific signal conditions are met.

Example:
    >>> from vcd2set import VCDSet
    >>> vs = VCDSet("simulation.vcd", clock="clk")
    >>> rising_edges = vs.get("data", lambda sm1, s, sp1: sm1 == "0" and s == "1")
"""

from .exceptions import (
    ClockSignalError,
    EmptyVCDError,
    InvalidInputError,
    InvalidSignalConditionError,
    InvalidTimeRangeError,
    SignalNotFoundError,
    VCDFileNotFoundError,
    VCDParseError,
    VCDSetError,
)
from .types import SignalCondition, Time, TimeValue, VCDInput, Value
from .vcd2set import VCDSet

__version__ = "0.1.0"
__all__ = [
    "VCDSet",
    # Exceptions
    "VCDSetError",
    "VCDFileNotFoundError",
    "VCDParseError",
    "ClockSignalError",
    "SignalNotFoundError",
    "EmptyVCDError",
    "InvalidInputError",
    "InvalidSignalConditionError",
    "InvalidTimeRangeError",
    # Types
    "Time",
    "Value",
    "TimeValue",
    "SignalCondition",
    "VCDInput",
]
