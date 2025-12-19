"""SetVCD - Convert VCD signals to sets of time points."""

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
from .setVCD import SetVCD
from .types import SignalCondition, Time, TimeValue, Value, VCDInput

__version__ = "0.1.0"
__all__ = [
    "SetVCD",
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
