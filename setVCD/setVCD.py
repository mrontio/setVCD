"""SetVCD - Convert VCD signals to sets of time points based on conditions."""

import inspect
import re
from inspect import Parameter
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union
from weakref import WeakKeyDictionary

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
from .types import (
    FP,
    AnyValue,
    FPValue,
    Raw,
    RawValue,
    SignalProtocol,
    String,
    StringValue,
    Time,
    ValueType,
    VCDInput,
    VCDVCDProtocol,
    XZIgnore,
    XZMethod,
    XZValue,
)


def _convert_to_int(value: str) -> Optional[int]:
    """Convert vcdvcd binary string to integer (Raw conversion).

    Args:
        value: Binary string from vcdvcd (e.g., "1010", "xxxx", "z")

    Returns:
        Integer value for valid binary strings, None for x/z or malformed strings.

    Examples:
        >>> _convert_to_int("1010")  # Binary to decimal
        10
        >>> _convert_to_int("xxxx")  # X/Z values
        None
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


def _convert_to_string(value: str) -> Optional[str]:
    """Convert vcdvcd string to string (String conversion - passthrough)."""
    # Return as-is, only return None for truly invalid input
    if value is None or value == "":
        return None
    return value


def _convert_to_fp(value: str, frac: int, signed: bool) -> Optional[float]:
    """Convert vcdvcd binary string to fixed-point float (FP conversion)."""
    # Validate frac parameter
    if frac < 0:
        raise ValueError(f"frac must be >= 0, got {frac}")

    # Check for x/z - return NaN per requirements
    value_lower = value.lower()
    if "x" in value_lower or "z" in value_lower:
        return float("nan")

    try:
        # Convert binary string to integer (unsigned initially)
        int_value = int(value, 2)
        total_bits = len(value)

        # Handle signed values (two's complement)
        if signed and total_bits > 0:
            sign_bit = 1 << (total_bits - 1)
            if int_value & sign_bit:
                # Negative number in two's complement
                int_value = int_value - (1 << total_bits)

        # Apply fractional scaling: divide by 2^frac
        float_value = int_value / (1 << frac)

        return float_value

    except ValueError:
        # Malformed binary string
        return float("nan")


def _convert_value(value_str: str, value_type: ValueType) -> AnyValue:
    """Dispatch to appropriate converter based on ValueType."""
    if isinstance(value_type, Raw):
        return _convert_to_int(value_str)
    elif isinstance(value_type, String):
        return _convert_to_string(value_str)
    elif isinstance(value_type, FP):
        return _convert_to_fp(value_str, value_type.frac, value_type.signed)
    else:
        # Should never happen with proper typing
        raise ValueError(f"Unknown ValueType: {type(value_type)}")


def _has_xz(value_str: Optional[str]) -> bool:
    """Check if raw vcdvcd string contains x or z."""
    if value_str is None:
        return False
    return "x" in value_str.lower() or "z" in value_str.lower()


def _replace_xz(value_str: str, replacement: int) -> str:
    """Replace x/z in binary string with binary representation of replacement."""
    if not _has_xz(value_str):
        return value_str

    # Convert replacement to binary with same width
    width = len(value_str)
    binary = format(replacement, f"0{width}b")

    # Truncate if replacement is too large
    if len(binary) > width:
        binary = binary[-width:]

    return binary


def _inspect_condition_signature(func: Callable[..., bool]) -> int:
    """Determine number of parameters in signal condition function.

    Uses inspect.signature() to count parameters. Validates that
    the function accepts exactly 1, 2, or 3 parameters.

    Args:
        func: Signal condition callable to inspect

    Returns:
        Number of parameters (1, 2, or 3)

    Raises:
        InvalidSignalConditionError: If function doesn't have 1, 2, or 3 params

    Examples:
        >>> _inspect_condition_signature(lambda s: s == 1)
        1
        >>> _inspect_condition_signature(lambda s, sp1: s == 0 and sp1 == 1)
        2
        >>> _inspect_condition_signature(lambda sm1, s, sp1: sm1 == 0 and s == 1)
        3
    """
    try:
        sig = inspect.signature(func)

        # Reject *args and **kwargs
        for param in sig.parameters.values():
            if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
                raise InvalidSignalConditionError(
                    "Signal condition cannot use *args or **kwargs. "
                    "Use explicit parameters (1, 2, or 3)."
                )

        # Filter out 'self' if it's a bound method
        params = [p for p in sig.parameters.values() if p.name != "self"]
        param_count = len(params)

        if param_count not in (1, 2, 3):
            raise InvalidSignalConditionError(
                f"Signal condition must accept 1, 2, or 3 parameters, got {param_count}. "
                f"Supported signatures:\n"
                f"  - 1 parameter:  lambda s: ...\n"
                f"  - 2 parameters: lambda sm1, s: ...\n"
                f"  - 3 parameters: lambda sm1, s, sp1: ..."
            )

        return param_count

    except InvalidSignalConditionError:
        raise
    except Exception as e:
        raise InvalidSignalConditionError(
            f"Failed to inspect signal_condition signature: {e}"
        ) from e


class SetVCD:
    """
    Query VCD signals with functionally, and combine them with set theory operators.
    """

    def __init__(
        self,
        vcd: VCDInput,
        clock: str = "clk",
        xz_method: Optional[XZMethod] = None,
        none_ignore: bool = True,
    ) -> None:
        """
        Args:
            vcd: Either a filename (str/Path) to a VCD file, or an already-parsed
                vcdvcd.VCDVCD object. If a filename is provided, it will be loaded
                and parsed automatically.
            clock: Exact name of the clock signal to use as time reference. This
                signal's last transition determines the iteration range. Must match
                a signal name exactly (case-sensitive).
            xz_method: Controls how x/z values are handled in signal filters.
                - XZIgnore() (default): Skip timesteps where any value is x/z
                - XZNone(): Convert x/z to None and pass to filter
                - XZValue(replacement): Replace x/z with specific integer value
            none_ignore: Whether to skip timesteps with None values (default: True).
                When True, timesteps where sm1, s, or sp1 is None are skipped.
                When False, None values are passed to the filter function.
                Common None sources: boundaries (t=0, last_clock) and x/z values.
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

        # Store x/z and None handling configuration
        if xz_method is None:
            xz_method = XZIgnore()
        self.xz_method: XZMethod = xz_method
        self.none_ignore: bool = none_ignore

        # Cache for signal condition signature inspection
        # Use WeakKeyDictionary to avoid stale cache entries from reused object IDs
        self._condition_signature_cache: WeakKeyDictionary[Callable[..., bool], int] = (
            WeakKeyDictionary()
        )

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

    def get(
        self,
        signal_name: str,
        signal_condition: Callable[..., bool],
        value_type: Optional[ValueType] = None,
    ) -> Set[Time]:
        """Filter time points based on signal condition.

        Args:
            signal_name: Exact name of signal (case-sensitive). Must exist in VCD file.
            signal_condition: Function that evaluates signal values. Supports three signatures:
                - 1 parameter:  lambda s: bool
                  Receives only current value. Use for simple level checks.
                - 2 parameters: lambda sm1, s: bool
                  Receives previous and current value. Use for edge detection and transitions.
                - 3 parameters: lambda sm1, s, sp1: bool
                  Receives previous, current, and next values. Use for complex temporal patterns.
                The value types passed depend on value_type parameter:
                - Raw(): receives Optional[int] values
                - String(): receives Optional[str] values
                - FP(): receives Optional[float] values
            value_type: Value conversion type (default: Raw()).
                - Raw(): Binary to int, x/z become None
                - String(): Keep raw strings including x/z as literals
                - FP(frac, signed): Fixed-point to float, x/z become NaN

        Returns:
            Set of timesteps where signal_condition returns True.

        Examples:
            >>> # 1-parameter: Simple level detection
            >>> high = vs.get("valid", lambda s: s == 1)
            >>>
            >>> # 2-parameter: Rising edge (backward-looking)
            >>> rising = vs.get("clk", lambda sm1, s: sm1 == 0 and s == 1)
            >>>
            >>> # 3-parameter: Classic rising edge (backward-looking)
            >>> rising = vs.get("clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
            >>>
            >>> # String matching to detect x/z
            >>> has_x = vs.get("data", lambda s: s is not None and 'x' in s,
            ...                value_type=String())
            >>>
            >>> # Fixed-point comparison
            >>> above_threshold = vs.get("temp",
            ...                          lambda s: s is not None and s > 25.5,
            ...                          value_type=FP(frac=8, signed=True))
        """
        # Default to Raw() if not specified
        if value_type is None:
            value_type = Raw()

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

        # Inspect condition signature and cache result
        if signal_condition not in self._condition_signature_cache:
            self._condition_signature_cache[signal_condition] = (
                _inspect_condition_signature(signal_condition)
            )
        param_count = self._condition_signature_cache[signal_condition]

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

                # XZ handling (BEFORE conversion) - parameter-count aware
                if isinstance(self.xz_method, XZIgnore):
                    # Only check values that will be used
                    if _has_xz(s_str):  # Always check current
                        continue
                    if param_count >= 2 and _has_xz(sm1_str):  # Check sm1 if needed
                        continue
                    if param_count >= 3 and _has_xz(sp1_str):  # Check sp1 if needed
                        continue
                elif isinstance(self.xz_method, XZValue):
                    # Only replace for Raw/FP, not for String
                    if not isinstance(value_type, String):
                        if sm1_str is not None:
                            sm1_str = _replace_xz(sm1_str, self.xz_method.replacement)
                        s_str = _replace_xz(s_str, self.xz_method.replacement)
                        if sp1_str is not None:
                            sp1_str = _replace_xz(sp1_str, self.xz_method.replacement)
                # else XZNone: let conversion naturally handle x/z → None

                # Convert values using specified ValueType (None for boundaries)
                sm1: AnyValue = (
                    _convert_value(sm1_str, value_type) if sm1_str is not None else None
                )
                s: AnyValue = _convert_value(s_str, value_type)
                sp1: AnyValue = (
                    _convert_value(sp1_str, value_type) if sp1_str is not None else None
                )

                # None handling (AFTER conversion) - parameter-count aware
                if self.none_ignore:
                    # Only check None for values that will be passed to condition
                    if s is None:  # Current value always matters
                        continue
                    if param_count >= 2 and sm1 is None:
                        continue
                    if param_count >= 3 and sp1 is None:
                        continue

                # Evaluate user's condition with appropriate number of arguments
                try:
                    if param_count == 1:
                        check = signal_condition(s)
                    elif param_count == 2:
                        check = signal_condition(sm1, s)
                    else:  # param_count == 3
                        check = signal_condition(sm1, s, sp1)
                except Exception as e:
                    raise InvalidSignalConditionError(
                        f"signal_condition raised exception at time {time}: {e}. "
                        f"Note: signal values can be None (for x/z values or boundaries). "
                        f"Function signature: {param_count} parameters"
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
        self,
        signal_name: str,
        timesteps: Set[Time],
        value_type: Optional[ValueType] = None,
    ) -> Union[
        List[Tuple[Time, RawValue]],
        List[Tuple[Time, StringValue]],
        List[Tuple[Time, FPValue]],
    ]:
        """Get values of a signal for specific timesteps.

        This method takes a set of timesteps (typically from `get`) and returns
        the signal values at those times as a sorted list values.

        Args:
            signal_name: Exact name of the signal to query (case-sensitive).
                Must exist in the VCD file.
            timesteps: Set of integer timesteps to query. Can be empty.
            value_type: Value conversion type (default: Raw()).
                - Raw(): Binary to int, x/z become None → List[Tuple[Time, Optional[int]]]
                - String(): Keep raw strings including x/z → List[Tuple[Time, Optional[str]]]
                - FP(frac, signed): Fixed-point to float, x/z → NaN → List[Tuple[Time, Optional[float]]]

        Returns:
            Sorted list values. Value type depends on value_type parameter.

        Examples:
            >>> handshakes = valid_times & ready_times
            >>>
            >>> # Get as integers (default)
            >>> int_values = vs.get_values("counter", handshakes)
            >>>
            >>> # Get as strings to see x/z
            >>> str_values = vs.get_values("data_bus", handshakes, String())
            >>>
            >>> # Get as fixed-point floats
            >>> fp_values = vs.get_values("voltage", handshakes, FP(frac=12, signed=False))
        """
        vals_with_t = self.get_values_with_t(signal_name, timesteps, value_type)
        # Tell pyright to ignore this because we have dependent types.
        return [pair[1] for pair in vals_with_t]  # type: ignore[return-value]

    def get_values_with_t(
        self,
        signal_name: str,
        timesteps: Set[Time],
        value_type: Optional[ValueType] = None,
    ) -> Union[
        List[Tuple[Time, RawValue]],
        List[Tuple[Time, StringValue]],
        List[Tuple[Time, FPValue]],
    ]:
        """Get (timesteps, values) of a signal for specific timesteps.

        This method takes a set of timesteps (typically from get()) and returns
        the signal values at those times as a sorted list of (time, value) tuples.

        Args:
            signal_name: Exact name of the signal to query (case-sensitive).
                Must exist in the VCD file.
            timesteps: Set of integer timesteps to query. Can be empty.
            value_type: Value conversion type (default: Raw())).
                - Raw(): Binary to int, x/z become None → List[Tuple[Time, Optional[int]]]
                - String(): Keep raw strings including x/z → List[Tuple[Time, Optional[str]]]
                - FP(frac, signed): Fixed-point to float, x/z → NaN → List[Tuple[Time, Optional[float]]]

        Returns:
            Sorted list of (time, value) tuples. Value type depends on value_type parameter.

        Examples:
            >>> handshakes = valid_times & ready_times
            >>>
            >>> # Get as integers (default)
            >>> int_values = vs.get_values_with_t("counter", handshakes)
            >>>
            >>> # Get as strings to see x/z
            >>> str_values = vs.get_values_with_t("data_bus", handshakes, String())
            >>>
            >>> # Get as fixed-point floats
            >>> fp_values = vs.get_values_with_t("voltage", handshakes, FP(frac=12, signed=False))
        """
        # Default to Raw() if not specified
        if value_type is None:
            value_type = Raw()

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
        result: List[Tuple[Time, AnyValue]] = []
        for time in timesteps:
            try:
                value_str: str = signal_obj[time]
                value_converted: AnyValue = _convert_value(value_str, value_type)
                result.append((time, value_converted))
            except Exception as e:
                raise VCDParseError(
                    f"Failed to access signal '{signal_name}' at time {time}: {e}"
                ) from e

        # Sort by time
        result.sort(key=lambda x: x[0])

        # Tell pyright to ignore this because we have dependent types.
        return result  # type: ignore[return-value]
