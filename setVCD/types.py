"""Type definitions and protocols for setVCD package."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Tuple, TypeVar, Union

# Type aliases for clarity and documentation
Time = int
"""Integer timestamp in VCD time units."""

Value = Optional[int]
"""Signal value as integer (binary conversion) or None (for x/z/boundaries)."""

TimeValue = Tuple[Time, Value]
"""Tuple of (time, value) representing a signal transition."""


class SignalProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd Signal object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    tv: List[TimeValue]
    """List of (time, value) tuples representing signal transitions."""

    def __getitem__(self, time: Time) -> str:
        """Random access to get signal value at specific time.

        Returns RAW string value from vcdvcd - will be converted by SetVCD layer.
        Uses binary search to interpolate value at any time point,
        even between transitions.
        """
        ...


class VCDVCDProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd.VCDVCD object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    def get_signals(self) -> List[str]:
        """Returns list of all signal names in the VCD file."""
        ...

    def __getitem__(self, signal_name: str) -> SignalProtocol:
        """Returns Signal object for the given signal name.

        Args:
            signal_name: Exact signal name (case-sensitive).

        Returns:
            Signal object with tv attribute and random access.
        """
        ...


SignalCondition = Callable[[Optional[int], Optional[int], Optional[int]], bool]
"""Type for signal condition callbacks.

A SignalCondition is a function that takes:
- sm1: Signal value at time-1 (None if at time 0 or if value is x/z)
- s: Signal value at current time (None if value is x/z)
- sp1: Signal value at time+1 (None if at last time or if value is x/z)

Returns:
- True if this time point should be included in the result set
- False otherwise

Examples:
    >>> # Rising edge detector
    >>> rising_edge: SignalCondition = lambda sm1, s, sp1: sm1 == 0 and s == 1
    >>>
    >>> # High level detector
    >>> is_high: SignalCondition = lambda sm1, s, sp1: s == 1
    >>>
    >>> # Change detector
    >>> changed: SignalCondition = lambda sm1, s, sp1: sm1 is not None and sm1 != s
"""

VCDInput = Union[str, Path, VCDVCDProtocol]
"""Type for VCD input to SetVCD.

Can be:
- str: Filename path to VCD file
- Path: Pathlib Path object to VCD file
- VCDVCDProtocol: Already-parsed vcdvcd.VCDVCD object
"""


# ValueType classes for controlling signal value conversion
@dataclass(frozen=True)
class Raw:
    """Represent signal bits as integers (default).

    X and Z values get turned to None.

    Example:
        >>> # Default behavior - binary to decimal
        >>> vs.get("data[3:0]", lambda sm1, s, sp1: s == 10, value_type=setvcd.Raw)  # "1010" → 10
    """

    pass


@dataclass(frozen=True)
class String:
    """Represent signal bits as a string.

    X and Z values stay in the string.

    Example:
        >>> # Detect x/z values in signal
        >>> vs.get("data", lambda sm1, s, sp1: s is not None and 'x' in s,
        ...        value_type=String())
    """

    pass


@dataclass(frozen=True)
class FP:
    """Represent signal bits as floating point, by assuming its fixed point.

    X and Z values get turned to None.

    Args:
        frac: Number of fractional bits (LSBs). Must be >= 0.
        signed: Whether value has a sign bit (MSB in two's complement).
            Default is False (unsigned).

    Examples:
        >>> # Temperature sensor with 8 fractional bits, unsigned
        >>> vs.get("temp", lambda sm1, s, sp1: s is not None and s > 25.5,
        ...        value_type=FP(frac=8, signed=False))
    """

    frac: int
    signed: bool = False


# Union type for all value types
ValueType = Union[Raw, String, FP]
"""Union of all ValueType options for signal value conversion."""

# Polymorphic value type aliases
RawValue = Optional[int]
"""Signal value as integer (binary conversion) or None (for x/z/boundaries)."""

StringValue = Optional[str]
"""Signal value as string (preserved from vcdvcd) or None (for boundaries)."""

FPValue = Optional[float]
"""Signal value as float (fixed-point conversion) or None."""

AnyValue = Union[RawValue, StringValue, FPValue]
"""Any signal value type (int, str, or float, or None)."""

# Generic type variable for signal conditions
T = TypeVar("T", int, str, float, contravariant=True)
"""Type variable for signal value types (contravariant for function parameters)."""


class SignalConditionProtocol(Protocol[T]):
    """Protocol for value-type-aware signal condition functions.

    A generic protocol that accepts signal values of a specific type (int, str, or float)
    and returns a boolean indicating whether the condition is met.
    """

    def __call__(self, sm1: Optional[T], s: Optional[T], sp1: Optional[T]) -> bool:
        """Evaluate condition on three consecutive signal values.

        Args:
            sm1: Signal value at time-1 (None if at time 0 or x/z for Raw)
            s: Signal value at current time (None if x/z for Raw)
            sp1: Signal value at time+1 (None if at last time or x/z for Raw)

        Returns:
            True if this time point should be included in the result set
        """
        ...
