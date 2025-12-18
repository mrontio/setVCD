# VCD2Set

Convert VCD (Value Change Dump) signals to sets of time points based on custom conditions.

## Overview

VCD2Set is a Python package for analyzing Verilog VCD files and extracting time points where specific signal conditions are met. It provides a simple, type-safe interface for working with simulation waveforms using set-based operations.

## Installation

```bash
pip install vcd2set
```

Or for development:

```bash
pip install -e .
```

## Quick Start

```python
from vcd2set import VCDSet

# Load VCD file
vs = VCDSet("simulation.vcd", clock="top.clk")

# Get rising edges of a signal
rising_edges = vs.get("data", lambda sm1, s, sp1: sm1 == "0" and s == "1")

# Get falling edges
falling_edges = vs.get("data", lambda sm1, s, sp1: sm1 == "1" and s == "0")

# Get time points where signal is high
high_times = vs.get("enable", lambda sm1, s, sp1: s == "1")

# Combine sets for complex conditions
# For example: rising edges when enable is high
valid_edges = rising_edges & high_times
```

## Features

- **Simple API**: Just two methods - `__init__` and `get`
- **Type Safe**: Full type hints for IDE support and type checking with mypy
- **Flexible Input**: Accept filename strings, Path objects, or pre-parsed vcdvcd objects
- **Comprehensive Error Handling**: Clear error messages with helpful suggestions
- **Multi-bit Signals**: Support for both single-bit and multi-bit signals
- **Set Operations**: Use Python set operations (&, |, -, ^) for complex queries

## Usage

### Initialization

You can initialize VCDSet with either a filename or a vcdvcd object:

```python
from vcd2set import VCDSet
from pathlib import Path

# From string filename
vs = VCDSet("simulation.vcd", clock="clk")

# From Path object
vs = VCDSet(Path("simulation.vcd"), clock="clk")

# From vcdvcd object
import vcdvcd
vcd = vcdvcd.VCDVCD("simulation.vcd")
vs = VCDSet(vcd, clock="clk")
```

The `clock` parameter must be the exact name of the clock signal in your VCD file (case-sensitive). This signal determines the time range for queries.

### Signal Conditions

The `signal_condition` callback receives three arguments representing the signal value at three consecutive time points:

- `sm1`: Signal value at time-1 (None at time 0)
- `s`: Signal value at current time
- `sp1`: Signal value at time+1 (None at last time)

Signal values are strings: `'0'`, `'1'`, `'x'`, `'z'`, or multi-bit like `'0101'`.

The callback should return `True` to include that time point in the result set.

### Examples

#### Basic Signal Detection

```python
# Rising edge: 0 -> 1 transition
rising = vs.get("clk", lambda sm1, s, sp1: sm1 == "0" and s == "1")

# Falling edge: 1 -> 0 transition
falling = vs.get("clk", lambda sm1, s, sp1: sm1 == "1" and s == "0")

# Any edge: value changed
edges = vs.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)

# Level high
high = vs.get("enable", lambda sm1, s, sp1: s == "1")

# Level low
low = vs.get("reset", lambda sm1, s, sp1: s == "0")
```

#### Multi-bit Signals

```python
# Specific pattern on a bus
pattern = vs.get("bus[3:0]", lambda sm1, s, sp1: s == "1010")

# Bus is non-zero
active = vs.get("data[7:0]", lambda sm1, s, sp1: s != "00000000")

# Bus transition detection
bus_changed = vs.get("addr[15:0]", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
```

#### Complex Queries with Set Operations

```python
# Rising clock edges when enable is high
clk_rising = vs.get("clk", lambda sm1, s, sp1: sm1 == "0" and s == "1")
enable_high = vs.get("enable", lambda sm1, s, sp1: s == "1")
valid_clocks = clk_rising & enable_high

# Data changes while not in reset
data_changes = vs.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
not_reset = vs.get("reset", lambda sm1, s, sp1: s == "0")
valid_changes = data_changes & not_reset

# Either signal is high
sig1_high = vs.get("sig1", lambda sm1, s, sp1: s == "1")
sig2_high = vs.get("sig2", lambda sm1, s, sp1: s == "1")
either_high = sig1_high | sig2_high

# Exclusive high (one but not both)
exclusive_high = sig1_high ^ sig2_high
```

#### Advanced Pattern Detection

```python
# Detect setup violation: data changes right before clock edge
data_change = vs.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
clk_about_to_rise = vs.get("clk", lambda sm1, s, sp1: s == "0" and sp1 == "1")
setup_violations = data_change & clk_about_to_rise

# Handshake protocol: valid and ready both high
valid_high = vs.get("valid", lambda sm1, s, sp1: s == "1")
ready_high = vs.get("ready", lambda sm1, s, sp1: s == "1")
handshake_times = valid_high & ready_high

# State machine transitions
state_a = vs.get("state[1:0]", lambda sm1, s, sp1: s == "00")
state_b = vs.get("state[1:0]", lambda sm1, s, sp1: s == "01")
# Times when transitioning from state A to state B
transition = vs.get("state[1:0]", lambda sm1, s, sp1: sm1 == "00" and s == "01")
```

## API Reference

### VCDSet

```python
class VCDSet:
    def __init__(
        self,
        vcd: Union[str, Path, VCDVCD],
        clock: str = "clk"
    ) -> None:
        """Initialize with VCD file and clock signal.

        Args:
            vcd: Filename (str/Path) or vcdvcd.VCDVCD object
            clock: Exact name of clock signal (case-sensitive)

        Raises:
            VCDFileNotFoundError: VCD file not found
            VCDParseError: VCD parsing failed
            InvalidInputError: Invalid input type
            EmptyVCDError: VCD has no data
            ClockSignalError: Clock signal not found
        """

    def get(
        self,
        signal_name: str,
        signal_condition: Callable[[Optional[str], str, Optional[str]], bool]
    ) -> Set[int]:
        """Get time points where signal_condition is True.

        Args:
            signal_name: Exact signal name (case-sensitive)
            signal_condition: Function (sm1, s, sp1) -> bool

        Returns:
            Set of integer time points where condition was True

        Raises:
            SignalNotFoundError: Signal not found in VCD
            InvalidSignalConditionError: Invalid condition callback
        """
```

### Exceptions

All exceptions inherit from `VCDSetError`:

- `VCDFileNotFoundError` - VCD file not found
- `VCDParseError` - VCD parsing failed or signal access error
- `ClockSignalError` - Clock signal not found
- `SignalNotFoundError` - Signal not found in VCD (in get())
- `EmptyVCDError` - VCD has no signals or no data
- `InvalidInputError` - Invalid input type
- `InvalidSignalConditionError` - Callback not callable or raised exception
- `InvalidTimeRangeError` - Invalid time range

Example error handling:

```python
from vcd2set import VCDSet, VCDSetError, ClockSignalError

try:
    vs = VCDSet("simulation.vcd", clock="wrong_clock_name")
except ClockSignalError as e:
    print(f"Clock error: {e}")
except VCDSetError as e:
    print(f"General VCD2Set error: {e}")
```

## Requirements

- Python 3.8+
- vcdvcd >= 2.0.0

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/vcd2set
cd vcd2set

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

### Running Tests

The test suite uses pytest and includes comprehensive tests with a real VCD file:

```bash
# Run all tests with coverage
pytest

# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/test_vcd2set.py

# Run specific test class
pytest tests/test_vcd2set.py::TestVCDSetInit

# Run specific test
pytest tests/test_vcd2set.py::TestVCDSetInit::test_init_from_string_filename

# Generate HTML coverage report
pytest --cov=vcd2set --cov-report=html
# Then open htmlcov/index.html in browser

# Run without coverage for faster execution
pytest --no-cov
```

### Test Structure

The test suite includes:
- **70+ test cases** covering all functionality
- **Real VCD file** (12.6MB hardware simulation) in `tests/fixtures/wave.vcd`
- Tests for initialization, signal queries, error handling, boundary conditions
- Hardware-specific patterns (AXI Stream handshakes, clock edges, reset)
- Set operations (intersection, union, difference, XOR)

### Code Quality

```bash
# Type check with mypy (strict mode)
mypy vcd2set

# Format code with black
black vcd2set tests

# Sort imports with isort
isort vcd2set tests

# Lint with ruff
ruff check vcd2set tests

# Run all quality checks
mypy vcd2set && black vcd2set tests && isort vcd2set tests && ruff check vcd2set tests
```

### Continuous Integration

The project includes a GitHub Actions workflow (`.github/workflows/test.yml`) that:
- Runs tests on Python 3.8, 3.9, 3.10, 3.11, 3.12
- Checks code formatting (black)
- Checks import sorting (isort)
- Runs linting (ruff)
- Performs type checking (mypy)
- Builds the package
- Uploads coverage to Codecov (optional)

### Type Checking

This package fully supports type hints and passes `mypy --strict`:

```bash
mypy vcd2set
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests and type checks pass
5. Submit a pull request

## Changelog

### v0.1.0 (Initial Release)

- Core VCDSet class with `__init__` and `get` methods
- Support for both filename and vcdvcd object input
- Comprehensive error handling with 8 exception types
- Full type hints and mypy strict compliance
- Support for single-bit and multi-bit signals
- Set-based query interface

## Future Enhancements

Planned for future versions:

- Reset signal handling and reset-aware queries
- Performance optimization for large VCD files
- Additional helper methods (edges(), levels(), etc.)
- Streaming interface for very large files
- MCP (Model Context Protocol) integration

## Support

For issues, questions, or contributions, please visit:
https://github.com/yourusername/vcd2set/issues
