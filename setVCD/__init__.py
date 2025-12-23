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
from .types import (
    FP,
    Raw,
    SignalCondition,
    String,
    Time,
    TimeValue,
    Value,
    ValueType,
    VCDInput,
)

__version__ = "0.2.0"
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
    # ValueTypes
    "ValueType",
    "Raw",
    "String",
    "FP",
]
