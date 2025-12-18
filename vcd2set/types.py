"""Type definitions and protocols for VCD2Set package."""

from pathlib import Path
from typing import Callable, List, Optional, Protocol, Tuple, Union

# Type aliases for clarity and documentation
Time = int
"""Integer timestamp in VCD time units."""

Value = str
"""Signal value as string: '0', '1', 'x', 'z', or multi-bit like '0101'."""

TimeValue = Tuple[Time, Value]
"""Tuple of (time, value) representing a signal transition."""


class SignalProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd Signal object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    tv: List[TimeValue]
    """List of (time, value) tuples representing signal transitions."""

    def __getitem__(self, time: Time) -> Value:
        """Random access to get signal value at specific time.

        Uses binary search to interpolate value at any time point,
        even between transitions.
        """
        ...


class VCDVCDProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd.VCDVCD object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    def keys(self) -> List[str]:
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


SignalCondition = Callable[[Optional[Value], Value, Optional[Value]], bool]
"""Type for signal condition callbacks.

A SignalCondition is a function that takes:
- sm1: Signal value at time-1 (None if at time 0)
- s: Signal value at current time
- sp1: Signal value at time+1 (None if at last time)

Returns:
- True if this time point should be included in the result set
- False otherwise

Examples:
    >>> # Rising edge detector
    >>> rising_edge: SignalCondition = lambda sm1, s, sp1: sm1 == "0" and s == "1"
    >>>
    >>> # High level detector
    >>> is_high: SignalCondition = lambda sm1, s, sp1: s == "1"
    >>>
    >>> # Change detector
    >>> changed: SignalCondition = lambda sm1, s, sp1: sm1 is not None and sm1 != s
"""

VCDInput = Union[str, Path, VCDVCDProtocol]
"""Type for VCD input to VCDSet.

Can be:
- str: Filename path to VCD file
- Path: Pathlib Path object to VCD file
- VCDVCDProtocol: Already-parsed vcdvcd.VCDVCD object
"""
