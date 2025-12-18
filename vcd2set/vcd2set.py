"""VCD2Set - Convert VCD signals to sets of time points based on conditions."""

from pathlib import Path
from typing import Dict, Optional, Set

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


class VCDSet:
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
            # Provide helpful error message with similar signals
            similar = [s for s in all_signals if clock.lower() in s.lower()]
            error_msg = f"Clock signal '{clock}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar[:5]}?"
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

    def get(
        self, signal_name: str, signal_condition: SignalCondition
    ) -> Set[Time]:
        """
        Filter time points
        """
        # Validate signal exists
        try:
            all_signals = self.wave.get_signals()
        except Exception as e:
            raise VCDParseError(f"Failed to retrieve signals: {e}") from e

        if signal_name not in all_signals:
            # Provide helpful error with similar signals
            similar = [s for s in all_signals if signal_name.lower() in s.lower()]
            error_msg = f"Signal '{signal_name}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar[:5]}?"
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
            raise VCDParseError(
                f"Failed to access signal '{signal_name}': {e}"
            ) from e

        # Iterate through ALL time steps (not just deltas)
        out: Set[Time] = set()

        for time in range(0, self.last_clock + 1):
            try:
                # Get signal values at time-1, time, and time+1
                # Use None for boundary conditions
                sm1: Optional[str] = signal_obj[time - 1] if time > 0 else None
                s: str = signal_obj[time]
                sp1: Optional[str] = (
                    signal_obj[time + 1] if time < self.last_clock else None
                )

                # Evaluate user's condition
                try:
                    check = signal_condition(sm1, s, sp1)
                except Exception as e:
                    raise InvalidSignalConditionError(
                        f"signal_condition raised exception at time {time}: {e}"
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
