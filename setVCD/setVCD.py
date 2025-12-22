"""SetVCD - Convert VCD signals to sets of time points based on conditions."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import vcdvcd

from .exceptions import (
    ClockSignalError,
    EmptyVCDError,
    InvalidInputError,
    InvalidSignalConditionError,
    SignalNotFoundError,
    VCDFileNotFoundError,
    VCDParseError,
)
from .types import SignalCondition, SignalProtocol, Time, VCDInput, VCDVCDProtocol


def _value_to_int(value: str) -> Optional[int]:
    """Convert VCD string value to Optional[int].

    Converts binary string to decimal integer. Returns None if value
    contains 'x' or 'z' (unknown/high-impedance).

    Args:
        value: VCD signal value string (e.g., "0", "1", "1010", "x", "01xz")

    Returns:
        Integer if all bits are 0/1, None if any x/z present

    Examples:
        "0" -> 0
        "1" -> 1
        "1010" -> 10
        "x" -> None
        "z" -> None
        "01xz" -> None
    """
    # Case-insensitive check for unknown/high-impedance
    value_lower = value.lower()
    if "x" in value_lower or "z" in value_lower:
        return None

    # Binary to decimal conversion
    try:
        return int(value, 2)
    except ValueError:
        # Defensive: malformed VCD value
        return None


class SetVCD:
    """
    Query VCD signals with functionally, and combine them with set theory operators.
    """

    def __init__(self, vcd: VCDInput, clock: str = "clk") -> None:
        """
        Args:
            vcd: Either a filename (str/Path) to a VCD file, or an already-parsed
                vcdvcd.VCDVCD object. If a filename is provided, it will be loaded
                and parsed automatically.
            clock: Exact name of the clock signal to use as time reference. This
                signal's last transition determines the iteration range. Must match
                a signal name exactly (case-sensitive).
        """
        # Load VCD object
        if isinstance(vcd, (str, Path)):
            vcd_path = Path(vcd)
            if not vcd_path.exists():
                raise VCDFileNotFoundError(f"VCD file not found: {vcd_path}")

            try:
                self.wave: VCDVCDProtocol = vcdvcd.VCDVCD(str(vcd_path))
            except Exception as e:
                raise VCDParseError(f"Failed to parse VCD file: {e}") from e
        elif hasattr(vcd, "get_signals") and hasattr(vcd, "__getitem__"):
            # Duck typing check for VCDVCD-like object
            self.wave = vcd
        else:
            raise InvalidInputError(
                f"vcd must be a filename (str/Path) or VCDVCD object, "
                f"got {type(vcd).__name__}"
            )

        # Validate VCD has signals
        try:
            all_signals = self.wave.get_signals()
        except Exception as e:
            raise VCDParseError(f"Failed to retrieve signals from VCD: {e}") from e

        if not all_signals:
            raise EmptyVCDError("VCD file contains no signals")

        # Initialize signal storage
        self.sigs: Dict[str, SignalProtocol] = {}

        # Find clock signal - EXACT match only
        if clock not in all_signals:
            # Provide helpful error message with similar signals using fuzzy matching
            # Split the search term into parts and find signals containing those parts
            search_parts = [p for p in clock.lower().split(".") if p]
            similar = []

            # Score each signal based on how many parts match
            scored_signals = []
            for sig in all_signals:
                sig_lower = sig.lower()
                matches = sum(1 for part in search_parts if part in sig_lower)
                if matches > 0:
                    scored_signals.append((matches, sig))

            # Sort by number of matches (descending) and take top matches
            scored_signals.sort(reverse=True, key=lambda x: x[0])
            similar = [sig for _, sig in scored_signals[:5]]

            error_msg = f"Clock signal '{clock}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar}?"
            else:
                error_msg += f" Available signals: {all_signals[:10]}..."
            raise ClockSignalError(error_msg)

        try:
            self.sigs["clock"] = self.wave[clock]
        except Exception as e:
            raise VCDParseError(f"Failed to access clock signal '{clock}': {e}") from e

        # Verify clock has data
        if not self.sigs["clock"].tv:
            raise EmptyVCDError(f"Clock signal '{clock}' has no time/value data")

        # Get last clock timestamp
        try:
            self.last_clock: Time = self.sigs["clock"].tv[-1][0]
        except (IndexError, TypeError) as e:
            raise EmptyVCDError(
                f"Failed to get last timestamp from clock signal: {e}"
            ) from e

    def search(self, search_regex: str = "") -> List[str]:
        """Search for signals matching a regex pattern.

        Args:
            search_regex: Regular expression pattern to match signal names.
                Empty string returns all signals.

        Returns:
            List of signal names matching the pattern.

        Example:
            >>> vs = SetVCD("sim.vcd", clock="TOP.clk")
            >>> output_signals = vs.search("output")
            >>> accelerator_signals = vs.search("Accelerator.*valid")
        """
        signals = self.wave.get_signals()
        searched = [s for s in signals if re.search(search_regex, s)]
        return searched

    def get(self, signal_name: str, signal_condition: SignalCondition) -> Set[Time]:
        """
        Filter time points
        """
        # Validate signal exists
        try:
            all_signals = self.wave.get_signals()
        except Exception as e:
            raise VCDParseError(f"Failed to retrieve signals: {e}") from e

        if signal_name not in all_signals:
            # Provide helpful error with similar signals using fuzzy matching
            # Split the search term into parts and find signals containing those parts
            search_parts = [p for p in signal_name.lower().split(".") if p]
            similar = []

            # Score each signal based on how many parts match
            scored_signals = []
            for sig in all_signals:
                sig_lower = sig.lower()
                matches = sum(1 for part in search_parts if part in sig_lower)
                if matches > 0:
                    scored_signals.append((matches, sig))

            # Sort by number of matches (descending) and take top matches
            scored_signals.sort(reverse=True, key=lambda x: x[0])
            similar = [sig for _, sig in scored_signals[:5]]

            error_msg = f"Signal '{signal_name}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar}?"
            else:
                error_msg += f" Available signals: {all_signals[:10]}..."
            raise SignalNotFoundError(error_msg)

        # Validate signal_condition is callable
        if not callable(signal_condition):
            raise InvalidSignalConditionError(
                f"signal_condition must be callable, got {type(signal_condition).__name__}"
            )

        # Get signal object
        try:
            signal_obj = self.wave[signal_name]
        except Exception as e:
            raise VCDParseError(f"Failed to access signal '{signal_name}': {e}") from e

        # Iterate through ALL time steps (not just deltas)
        out: Set[Time] = set()

        for time in range(0, self.last_clock + 1):
            try:
                # Get raw string values from vcdvcd
                sm1_str: Optional[str] = signal_obj[time - 1] if time > 0 else None
                s_str: str = signal_obj[time]
                sp1_str: Optional[str] = (
                    signal_obj[time + 1] if time < self.last_clock else None
                )

                # Convert to integers (None for boundaries or x/z)
                sm1: Optional[int] = (
                    _value_to_int(sm1_str) if sm1_str is not None else None
                )
                s: Optional[int] = _value_to_int(s_str)
                sp1: Optional[int] = (
                    _value_to_int(sp1_str) if sp1_str is not None else None
                )

                # Evaluate user's condition
                try:
                    check = signal_condition(sm1, s, sp1)
                except Exception as e:
                    raise InvalidSignalConditionError(
                        f"signal_condition raised exception at time {time}: {e}. "
                        f"Note: signal values can be None (for x/z values or boundaries)."
                    ) from e

                # Add time to result set if condition is True
                if check:
                    out.add(time)

            except InvalidSignalConditionError:
                # Re-raise our own exceptions
                raise
            except Exception as e:
                # Wrap any other errors
                raise VCDParseError(
                    f"Failed to access signal '{signal_name}' at time {time}: {e}"
                ) from e

        return out

    def get_values(
        self, signal_name: str, timesteps: Set[Time]
    ) -> List[Tuple[Time, Optional[int]]]:
        """Get signal values at specific timesteps.

        This method takes a set of timesteps (typically from get()) and returns
        the signal values at those times as a sorted list of (time, value) tuples.

        Args:
            signal_name: Exact name of the signal to query (case-sensitive).
                Must exist in the VCD file.
            timesteps: Set of integer timesteps to query. Can be empty.

        Returns:
            List of (time, value) tuples sorted by time. Values are Optional[int]:
            integers for valid binary values (decimal conversion), None for x/z.

        """
        # Validate signal exists
        try:
            all_signals = self.wave.get_signals()
        except Exception as e:
            raise VCDParseError(f"Failed to retrieve signals: {e}") from e

        if signal_name not in all_signals:
            # Provide helpful error with similar signals using fuzzy matching
            search_parts = [p for p in signal_name.lower().split(".") if p]
            similar = []

            # Score each signal based on how many parts match
            scored_signals = []
            for sig in all_signals:
                sig_lower = sig.lower()
                matches = sum(1 for part in search_parts if part in sig_lower)
                if matches > 0:
                    scored_signals.append((matches, sig))

            # Sort by number of matches (descending) and take top matches
            scored_signals.sort(reverse=True, key=lambda x: x[0])
            similar = [sig for _, sig in scored_signals[:5]]

            error_msg = f"Signal '{signal_name}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar}?"
            else:
                error_msg += f" Available signals: {all_signals[:10]}..."
            raise SignalNotFoundError(error_msg)

        # Get signal object
        try:
            signal_obj = self.wave[signal_name]
        except Exception as e:
            raise VCDParseError(f"Failed to access signal '{signal_name}': {e}") from e

        # Get values at each timestep and sort by time
        result: List[Tuple[Time, Optional[int]]] = []
        for time in timesteps:
            try:
                value_str: str = signal_obj[time]
                value_int: Optional[int] = _value_to_int(value_str)
                result.append((time, value_int))
            except Exception as e:
                raise VCDParseError(
                    f"Failed to access signal '{signal_name}' at time {time}: {e}"
                ) from e

        # Sort by time
        result.sort(key=lambda x: x[0])

        return result
