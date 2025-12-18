"""Exception classes for VCD2Set package."""


class VCDSetError(Exception):
    """Base exception for all VCD2Set errors.

    All exceptions raised by VCD2Set inherit from this class,
    making it easy to catch all VCD2Set-specific errors.
    """

    pass


class VCDFileNotFoundError(VCDSetError):
    """Raised when a VCD file cannot be found.

    This occurs when a filename is passed to VCDSet but the file
    doesn't exist at the specified path.
    """

    pass


class VCDParseError(VCDSetError):
    """Raised when a VCD file cannot be parsed.

    This can occur due to:
    - Malformed VCD file
    - Unsupported VCD format
    - vcdvcd library errors during parsing
    - Signal access errors
    """

    pass


class ClockSignalError(VCDSetError):
    """Raised when clock signal is not found or ambiguous.

    This occurs when:
    - Specified clock signal doesn't exist in VCD
    - Clock signal name is misspelled
    """

    pass


class SignalNotFoundError(VCDSetError):
    """Raised when requested signal is not in VCD.

    This occurs in the get() method when signal_name doesn't
    match any signal in the VCD file.
    """

    pass


class EmptyVCDError(VCDSetError):
    """Raised when VCD file has no signals or no time data.

    This can occur when:
    - VCD file is empty or has no signals
    - Clock signal has no time/value pairs
    - VCD has signals but no actual data
    """

    pass


class InvalidInputError(VCDSetError):
    """Raised when input type is invalid.

    This occurs when the vcd parameter is neither:
    - A string filename
    - A Path object
    - A vcdvcd.VCDVCD object
    """

    pass


class InvalidSignalConditionError(VCDSetError):
    """Raised when signal_condition is not callable or raises exception.

    This occurs when:
    - signal_condition is not a callable object
    - signal_condition raises an exception during evaluation
    """

    pass


class InvalidTimeRangeError(VCDSetError):
    """Raised when time range is invalid.

    This occurs when:
    - Clock signal has negative timestamps
    - Time iteration encounters invalid bounds
    """

    pass
