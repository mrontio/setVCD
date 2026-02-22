"""SetVCD - Convert VCD signals to sets of time points based on conditions."""

import inspect
import re
from collections.abc import Callable
from inspect import Parameter
from pathlib import Path
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
    CompiledInput,
    FPValue,
    Raw,
    RawValue,
    SignalCondition,
    SignalExpression,
    SignalProtocol,
    String,
    StringValue,
    Time,
    ValueType,
    VCDInput,
    VCDVCDProtocol,
    XZIgnore,
    XZMethod,
)


def _convert_to_int(value: str) -> int | None:
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


def _convert_to_string(value: str) -> str | None:
    """Convert vcdvcd string to string (String conversion - passthrough)."""
    # Return as-is, only return None for truly invalid input
    if value is None or value == "":
        return None
    return value


def _convert_to_fp(value: str, frac: int, signed: bool) -> float | None:
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


def _has_xz(value_str: str | None) -> bool:
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
        xz_method: XZMethod | None = None,
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
        if isinstance(vcd, str | Path):
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
        self.sigs: dict[str, SignalProtocol] = {}

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

    def search(self, search_regex: str = "") -> list[str]:
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

    def validate_signal_name(self, signal_name: str) -> bool:
        """
        Side-effect function to throw exception if signal name is not found
        in the wavefile.
        """
        # Validate signal exists
        try:
            all_signals = self.wave.get_signals()
        except Exception as e:
            raise VCDParseError(f"Failed to retrieve signals: {e}") from e

        if signal_name not in all_signals:
            search_parts = [p for p in signal_name.lower().split(".") if p]
            scored_signals = []
            for sig in all_signals:
                sig_lower = sig.lower()
                matches = sum(1 for part in search_parts if part in sig_lower)
                if matches > 0:
                    scored_signals.append((matches, sig))
            scored_signals.sort(reverse=True, key=lambda x: x[0])
            similar = [sig for _, sig in scored_signals[:5]]

            error_msg = f"Signal '{signal_name}' not found in VCD."
            if similar:
                error_msg += f" Did you mean one of: {similar}?"
            else:
                error_msg += f" Available signals: {all_signals[:10]}..."
            raise SignalNotFoundError(error_msg)

        return True

    def get(
        self,
        signal_name: str,
        signal_condition: Callable[..., bool],
        value_type: ValueType | None = None,
    ) -> SignalExpression:
        """Build a signal filter expression (no evaluation yet).

        Args:
            signal_name: Exact name of signal (case-sensitive). Must exist in VCD file.
            signal_condition: Function that evaluates signal values. Supports three signatures:
                - 1 parameter:  lambda s: bool
                - 2 parameters: lambda sm1, s: bool
                - 3 parameters: lambda sm1, s, sp1: bool
            value_type: Value conversion type (default: Raw()).

        Returns:
            SignalExpression that can be combined with &, |, - and evaluated via
            get_times() or get_values_with_t().
        """
        if value_type is None:
            value_type = Raw()

        self.validate_signal_name(signal_name)

        if not callable(signal_condition):
            raise InvalidSignalConditionError(
                f"signal_condition must be callable, got {type(signal_condition).__name__}"
            )

        if signal_condition not in self._condition_signature_cache:
            self._condition_signature_cache[signal_condition] = (
                _inspect_condition_signature(signal_condition)
            )
        arity = self._condition_signature_cache[signal_condition]

        return SignalExpression(
            SignalCondition(
                name=signal_name,
                valueType=value_type,
                xzMethod=self.xz_method,
                noneIgnore=self.none_ignore,
                arity=arity,
                condition=signal_condition,
            )
        )

    def get_times(self, expr: SignalExpression) -> set[Time]:
        """Evaluate a SignalExpression and return the set of matching timesteps.

        Args:
            expr: A SignalExpression built from get() calls and &, |, - operators.

        Returns:
            Set of timesteps where the expression evaluates to True.
        """
        compiled_fn = expr.compile()
        needed = expr.get_signals()
        sig_objects: dict[str, SignalProtocol] = {
            name: self.wave[name] for name in needed
        }

        result: set[Time] = set()
        for time in range(0, self.last_clock + 1):
            try:
                c: CompiledInput = {}
                for sig_name, sig_obj in sig_objects.items():
                    sm1_str: str | None = sig_obj[time - 1] if time > 0 else None
                    s_str: str = sig_obj[time]
                    sp1_str: str | None = (
                        sig_obj[time + 1] if time < self.last_clock else None
                    )
                    c[sig_name] = (sm1_str, s_str, sp1_str)

                try:
                    if compiled_fn(c):
                        result.add(time)
                except Exception as e:
                    raise InvalidSignalConditionError(
                        f"signal_condition raised exception at time {time}: {e}. "
                        f"Note: signal values can be None (for x/z values or boundaries). "
                        f"Function signature: {self._get_arity_from_expr(expr)} parameters"
                    ) from e

            except InvalidSignalConditionError:
                raise
            except Exception as e:
                raise VCDParseError(
                    f"Failed to evaluate expression at time {time}: {e}"
                ) from e

        return result

    def _get_arity_from_expr(self, expr: SignalExpression) -> str:
        """Extract arity info from the outermost SignalCondition for error messages."""
        match expr.expr:
            case SignalCondition() as c:
                return str(c.arity)
            case _:
                return "unknown"

    def get_values(
        self,
        signal_name: str,
        expr: SignalExpression,
        value_type: ValueType | None = None,
    ) -> list[RawValue] | list[StringValue] | list[FPValue]:
        """Evaluate expr and return values of signal_name at matching timesteps.

        Args:
            signal_name: Signal whose values to retrieve at matching times.
            expr: Expression that determines which timesteps to include.
            value_type: Value conversion type (default: Raw()).

        Returns:
            Sorted list of values (no timestamps).
        """
        vals_with_t = self.get_values_with_t(signal_name, expr, value_type)
        return [pair[1] for pair in vals_with_t]  # type: ignore[return-value]

    def get_values_with_t(
        self,
        signal_name: str,
        expr: SignalExpression,
        value_type: ValueType | None = None,
    ) -> (
        list[tuple[Time, RawValue]]
        | list[tuple[Time, StringValue]]
        | list[tuple[Time, FPValue]]
    ):
        """Evaluate expr and return (time, value) pairs for signal_name at matching timesteps.

        Compiles the expression once and iterates the VCD in a single pass.

        Args:
            signal_name: Signal whose values to retrieve at matching times.
            expr: Expression (from get() and &/|/- operators) that filters timesteps.
            value_type: Value conversion type for the output signal (default: Raw()).

        Returns:
            Sorted list of (time, value) tuples.
        """
        if value_type is None:
            value_type = Raw()

        self.validate_signal_name(signal_name)

        try:
            signal_obj = self.wave[signal_name]
        except Exception as e:
            raise VCDParseError(f"Failed to access signal '{signal_name}': {e}") from e

        compiled_fn = expr.compile()
        needed = expr.get_signals()
        sig_objects: dict[str, SignalProtocol] = {
            name: self.wave[name] for name in needed
        }

        result: list[tuple[Time, AnyValue]] = []
        for time in range(0, self.last_clock + 1):
            try:
                c: CompiledInput = {}
                for sig_name, sig_obj in sig_objects.items():
                    sm1_str: str | None = sig_obj[time - 1] if time > 0 else None
                    s_str: str = sig_obj[time]
                    sp1_str: str | None = (
                        sig_obj[time + 1] if time < self.last_clock else None
                    )
                    c[sig_name] = (sm1_str, s_str, sp1_str)

                try:
                    if compiled_fn(c):
                        value_str: str = signal_obj[time]
                        result.append((time, _convert_value(value_str, value_type)))
                except Exception as e:
                    raise InvalidSignalConditionError(
                        f"signal_condition raised exception at time {time}: {e}. "
                        f"Note: signal values can be None (for x/z values or boundaries). "
                        f"Function signature: {self._get_arity_from_expr(expr)} parameters"
                    ) from e

            except InvalidSignalConditionError:
                raise
            except Exception as e:
                raise VCDParseError(
                    f"Failed to access signal '{signal_name}' at time {time}: {e}"
                ) from e

        result.sort(key=lambda x: x[0])
        return result  # type: ignore[return-value]
