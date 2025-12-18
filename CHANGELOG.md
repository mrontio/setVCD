# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2024-12-18

### Added
- Initial release of VCD2Set
- Core `VCDSet` class with `__init__` and `get` methods
- Support for filename (str/Path) and vcdvcd object input
- Comprehensive error handling with 8 custom exception types:
  - `VCDSetError` (base exception)
  - `VCDFileNotFoundError`
  - `VCDParseError`
  - `ClockSignalError`
  - `SignalNotFoundError`
  - `EmptyVCDError`
  - `InvalidInputError`
  - `InvalidSignalConditionError`
  - `InvalidTimeRangeError`
- Full type hints with mypy strict compliance
- Protocol-based types for vcdvcd interface (no hard dependency in type system)
- Support for both single-bit and multi-bit signals
- Set-based query interface for time point extraction
- Comprehensive documentation with usage examples
- PEP 561 type marker (py.typed)

### Features
- Iterate every time step from 0 to last clock transition
- Exact clock signal name matching (case-sensitive)
- Signal condition callbacks with (time-1, time, time+1) context
- Helpful error messages with suggestions for similar signal names
- Duck typing validation for vcdvcd objects

### Documentation
- Comprehensive README with quick start and examples
- Full API reference
- Type-annotated docstrings for all public methods
- Example usage patterns for common scenarios

[0.1.0]: https://github.com/yourusername/vcd2set/releases/tag/v0.1.0
