"""Type definitions and protocols for setVCD package."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Protocol, TypeVar

# Type aliases for clarity and documentation
Time = int
"""Integer timestamp in VCD time units."""

Value = int | None
"""Signal value as integer (binary conversion) or None (for x/z/boundaries)."""

TimeValue = tuple[Time, Value]
"""Tuple of (time, value) representing a signal transition."""


class SignalProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd Signal object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    tv: list[TimeValue]
    """List of (time, value) tuples representing signal transitions."""

    def __getitem__(self, time: Time) -> str:
        """Random access to get signal value at specific time."""
        ...


class VCDVCDProtocol(Protocol):
    """Protocol describing the interface of a vcdvcd.VCDVCD object.

    This protocol documents the expected interface without requiring
    an explicit dependency on vcdvcd for type checking.
    """

    def get_signals(self) -> list[str]:
        """Returns list of all signal names in the VCD file."""
        ...

    def __getitem__(self, signal_name: str) -> SignalProtocol:
        """Returns Signal object for the given signal name."""
        ...


# ValueType classes — must come before Conversions


@dataclass(frozen=True)
class Raw:
    """Represent signal bits as integers (default).

    X and Z values get turned to None.
    """

    pass


@dataclass(frozen=True)
class String:
    """Represent signal bits as a string.

    X and Z values stay in the string.
    """

    pass


@dataclass(frozen=True)
class FP:
    """Represent signal bits as floating point, by assuming its fixed point.

    Args:
        frac: Number of fractional bits (LSBs). Must be >= 0.
        signed: Whether value has a sign bit (MSB in two's complement).
            Default is False (unsigned).
    """

    total_bits: int
    frac: int
    signed: bool = False

    def __post_init__(self) -> None:
        if self.frac < 0:
            raise ValueError(f"frac must be >= 0, got {self.frac}")
        if self.total_bits < 1:
            raise ValueError(f"total_bits must be >= 1, got {self.total_bits}")


ValueType = Raw | String | FP
"""Union of all ValueType options for signal value conversion."""


# XZMethod classes — must come before Conversions


@dataclass(frozen=True)
class XZIgnore:
    """Skip timesteps where any signal value contains x or z (default behavior)."""

    pass


@dataclass(frozen=True)
class XZNone:
    """Convert x/z values to None before passing to filter function."""

    pass


@dataclass(frozen=True)
class XZValue:
    """Replace x/z values with a specific integer value."""

    replacement: int


XZMethod = XZIgnore | XZNone | XZValue
"""Union of all XZMethod options for x/z value handling."""

# Polymorphic value type aliases
RawValue = int | None
"""Signal value as integer (binary conversion) or None (for x/z/boundaries)."""

StringValue = str | None
"""Signal value as string (preserved from vcdvcd) or None (for boundaries)."""

FPValue = float | None
"""Signal value as float (fixed-point conversion) or None."""

AnyValue = RawValue | StringValue | FPValue
"""Any signal value type (int, str, or float, or None)."""


class Conversions:
    @staticmethod
    def to_int(value: str, xz: XZMethod) -> int | None:
        value_lower = value.lower()
        if "x" in value_lower or "z" in value_lower:
            match xz:
                case XZNone():
                    return None
                case XZValue():
                    return xz.replacement
                case XZIgnore():
                    return None  # Shouldn't be executed due to prop.

        try:
            return int(value, 2)
        except ValueError:
            return None

    @staticmethod
    def float(
        value: str, total_bits: int, frac: int, signed: bool, xz: XZMethod
    ) -> FPValue:
        value_lower = value.lower()
        if "x" in value_lower or "z" in value_lower:
            match xz:
                case XZNone():
                    return None
                case XZValue():
                    return float("nan")
                case XZIgnore():
                    return None  # Shouldn't be executed due to prop.

        try:
            int_value = int(value, 2)

            if signed and total_bits > 0:
                sign_bit = 1 << (total_bits - 1)
                if int_value & sign_bit:
                    int_value = int_value - (1 << total_bits)

            return int_value / (1 << frac)
        except ValueError:
            return float("nan")

    @staticmethod
    def string(value: str, xz: XZMethod) -> str | None:
        value_lower = value.lower()
        if "x" in value_lower or "z" in value_lower:
            match xz:
                case XZNone():
                    return None
                case XZValue():
                    return value
                case XZIgnore():
                    return None  # Shouldn't be executed due to prop.

        return value


StringTuple = tuple[str | None, str | None, str | None]
ValueTuple = tuple[AnyValue | None, AnyValue | None, AnyValue | None]
CompiledInput = dict[str, StringTuple]
SignalFunction = Callable[..., bool]
CompiledSignalFunction = Callable[[CompiledInput], bool]
TransformationFunction = Callable[[CompiledInput], ValueTuple]


@dataclass(frozen=True)
class SignalCondition:
    """Leaf node of the expression tree: one signal with one condition function."""

    name: str
    valueType: ValueType
    xzMethod: XZMethod
    noneIgnore: bool
    arity: int
    condition: SignalFunction

    def _xz_proposition(self) -> CompiledSignalFunction:
        if not isinstance(self.xzMethod, XZIgnore):
            return lambda _: True

        def has_xz_at(c: CompiledInput, idx: int) -> bool:
            s = c[self.name][idx]
            return s is not None and ("x" in s.lower() or "z" in s.lower())

        if self.arity == 1:
            return lambda c: not has_xz_at(c, 1)
        elif self.arity == 2:
            return lambda c: not has_xz_at(c, 0) and not has_xz_at(c, 1)
        else:
            return lambda c: not any(has_xz_at(c, i) for i in range(3))

    def _none_proposition(self) -> Callable[[ValueTuple], bool]:
        if not self.noneIgnore:
            return lambda _: True
        if self.arity == 1:
            return lambda v: v[1] is not None
        elif self.arity == 2:
            return lambda v: v[0] is not None and v[1] is not None
        else:
            return lambda v: all(x is not None for x in v)

    def _transformation_function(self) -> TransformationFunction:
        conversion: Callable[[str], AnyValue]
        match self.valueType:
            case Raw():
                conversion = partial(Conversions.to_int, xz=self.xzMethod)
            case String():
                conversion = partial(Conversions.string, xz=self.xzMethod)
            case FP(total_bits, frac, signed):
                conversion = partial(
                    Conversions.float,
                    total_bits=total_bits,
                    frac=frac,
                    signed=signed,
                    xz=self.xzMethod,
                )
            case _:
                raise ValueError(f"Unknown ValueType: {self.valueType}")
        return lambda c: tuple(  # type: ignore[return-value]
            conversion(s) if s is not None else None for s in c[self.name]
        )

    def compile(self) -> CompiledSignalFunction:
        p_xz: CompiledSignalFunction = self._xz_proposition()
        f_t: TransformationFunction = self._transformation_function()
        p_none: Callable[[ValueTuple], bool] = self._none_proposition()

        match self.arity:
            case 1:

                def f1(c: CompiledInput) -> bool:
                    v: ValueTuple = f_t(c)
                    _, v2, _ = v
                    return p_xz(c) and p_none(v) and bool(self.condition(v2))

                return f1
            case 2:

                def f2(c: CompiledInput) -> bool:
                    v: ValueTuple = f_t(c)
                    v1, v2, _ = v
                    return p_xz(c) and p_none(v) and bool(self.condition(v1, v2))

                return f2
            case 3:

                def f3(c: CompiledInput) -> bool:
                    v: ValueTuple = f_t(c)
                    v1, v2, v3 = v
                    return p_xz(c) and p_none(v) and bool(self.condition(v1, v2, v3))

                return f3
            case _:
                raise ValueError(
                    f"SignalCondition received arity {self.arity}, which is not supported."
                )


@dataclass(frozen=True)
class SignalOperation:
    """Internal node: binary operator combining two SignalExpression nodes."""

    class Operator(Enum):
        INTERSECTION = "intersection"
        UNION = "union"
        DIFFERENCE = "difference"

    operator: SignalOperation.Operator
    lhs: SignalExpression
    rhs: SignalExpression


@dataclass(frozen=True)
class SignalExpression:
    """Wrapper holding either a leaf (SignalCondition) or internal node (SignalOperation)."""

    expr: SignalCondition | SignalOperation

    def compile(self) -> CompiledSignalFunction:
        return SignalExpression._compile(self)

    def get_signals(self) -> set[str]:
        match self.expr:
            case SignalCondition() as c:
                return {c.name}
            case SignalOperation() as o:
                return o.lhs.get_signals() | o.rhs.get_signals()
        return set()  # unreachable

    def __and__(self, other: SignalExpression) -> SignalExpression:
        return SignalExpression(
            SignalOperation(SignalOperation.Operator.INTERSECTION, self, other)
        )

    def __or__(self, other: SignalExpression) -> SignalExpression:
        return SignalExpression(
            SignalOperation(SignalOperation.Operator.UNION, self, other)
        )

    def __sub__(self, other: SignalExpression) -> SignalExpression:
        return SignalExpression(
            SignalOperation(SignalOperation.Operator.DIFFERENCE, self, other)
        )

    @staticmethod
    def _compile(e: SignalExpression) -> CompiledSignalFunction:
        match e.expr:
            case SignalCondition() as c:
                return c.compile()
            case SignalOperation() as o:
                f1 = SignalExpression._compile(o.lhs)
                f2 = SignalExpression._compile(o.rhs)
                match o.operator:
                    case SignalOperation.Operator.INTERSECTION:
                        return lambda c: f1(c) and f2(c)
                    case SignalOperation.Operator.UNION:
                        return lambda c: f1(c) or f2(c)
                    case SignalOperation.Operator.DIFFERENCE:
                        return lambda c: f1(c) and not f2(c)
        raise ValueError(f"Unknown expression type: {type(e.expr)}")


VCDInput = str | Path | VCDVCDProtocol
"""Type for VCD input to SetVCD.

Can be:
- str: Filename path to VCD file
- Path: Pathlib Path object to VCD file
- VCDVCDProtocol: Already-parsed vcdvcd.VCDVCD object
"""

# Generic type variable for signal conditions (contravariant: used in parameter position)
T_contra = TypeVar("T_contra", contravariant=True)
"""Contravariant type variable for signal condition parameter types."""


class SignalConditionProtocol(Protocol[T_contra]):
    """Protocol for value-type-aware signal condition functions."""

    def __call__(
        self, sm1: T_contra | None, s: T_contra | None, sp1: T_contra | None
    ) -> bool:
        """Evaluate condition on three consecutive signal values."""
        ...
