# SetVCD
Programmatically inspect hardware VCD signals using a high-level functional interface.

Higher-order programming constructs and set operations are a natural fit for inspecting VCD signals, and this Python library allows you to easily specify, in text, what simulation timesteps matter to functional correctness.

## Motivating Example
Say you are debugging a streaming input interface (`Accelerator.io_input`) and you would like to extract only the values when the streaming transaction is valid. Typically when viewing a wavefile in a viewer, the points we care about look like this:
![img/gtkwave.png](img/gtkwave.png "GTKWave screenshot of streaming interface we want to debug.")

We can write this desired condition, parameterised by simulation timestep `t` as a formal statement:
```python
(clk(t - 1) == 0 and clk(t) == 1) and
reset(t) == 0 and
input_ready(t) == 1 and
input_valid(t) == 1
```
This is a very natural fit for [higher-order functions](https://en.wikipedia.org/wiki/Higher-order_function) and [set operations](https://en.wikipedia.org/wiki/Set_(mathematics)#Basic_operations).

This library provides you two important methods:
- Get set of timesteps with condition:
   ```python
    SetVCD.get : (signal: String,
                  condition: (Value, Value, Value) -> Bool,
                  value_type: Raw or String or FP)
                  -> Set(Timestep)
   ```
   - Given a signal in the VCD file with name `signal`, return a set of timesteps where condition is True.
   - `condition` is a function that should take three values relating to the current timestep: $(t-1, t, t+1)$, which allows to detect things like rising edges. The `Value` depends on the
   - `value_type` reflects how the signal values are interpretted.
      - `setVCD.Raw()` outputs (`int`),
      - `setVCD.String()` outputs `str`),
      - `setVCD.FP(fractional_bits: int, signed: bool)` outputs `float`, which is converted using fixed point.
   - Return type `Set(Timestep)` allows it to be seamlessly combined with other signals using [set operations](https://en.wikipedia.org/wiki/Set_(mathematics)#Basic_operations).
- Get the values at a set of timesteps:
  ```python
  SetVCD.get_value : (timesteps: Set(Timestep), ValueType: Raw or String or FP) -> List(Value)
  SetVCD.get_value_with_t : (timesteps: Set(Timestep), ValueType: Raw or String or FP) -> List((Timestep, Value))
  ```
You can see how this works in our [pre-filled notebook: example.ipynb](example.ipynb)

## Overview

SetVCD is a Python package for analyzing Verilog VCD files and extracting time points where specific signal conditions are met. It provides a simple, type-safe interface for working with simulation waveforms using set-based operations.

## Installation
The package is available in PyPI:
```bash
pip install setVCD
```


## Usage
### Initialization

You can initialize SetVCD with either a filename or a vcdvcd object:

```python
import setVCD
from pathlib import Path

# From string filename
sv = SetVCD("simulation.vcd", clock="clk")

# From Path object
sv = SetVCD(Path("simulation.vcd"), clock="clk")

# From vcdvcd object
import vcdvcd
vcd = vcdvcd.VCDVCD("simulation.vcd")
sv = SetVCD(vcd, clock="clk")
```

The `clock` parameter must be the exact name of the clock signal in your VCD file (case-sensitive). This signal determines the time range for queries.

### Signal Conditions

The `signal_condition` callback receives three arguments representing the signal value at three consecutive time points:

- `sm1`: Signal value at time-1 (None at time 0 or if value is x/z)
- `s`: Signal value at current time (None if value is x/z)
- `sp1`: Signal value at time+1 (None at last time or if value is x/z)

Signal values are `Optional[int]`:
- Integers: Binary values converted to decimal (e.g., "1010" → 10)
- None: Represents x/z values or boundary conditions (t-1 at time 0, t+1 at last time)

The callback should return `True` to include that time point in the result set.

### Examples

#### Basic Signal Detection

```python
# Rising edge: 0 -> 1 transition
rising = sv.get("clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)

# Falling edge: 1 -> 0 transition
falling = sv.get("clk", lambda sm1, s, sp1: sm1 == 1 and s == 0)

# Any edge: value changed
edges = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)

# Level high
high = sv.get("enable", lambda sm1, s, sp1: s == 1)

# Level low
low = sv.get("reset", lambda sm1, s, sp1: s == 0)
```

#### Multi-bit Signals

```python
# Specific pattern on a bus (binary "1010" = decimal 10)
pattern = sv.get("bus[3:0]", lambda sm1, s, sp1: s == 10)

# Bus is non-zero
active = sv.get("data[7:0]", lambda sm1, s, sp1: s != 0)

# Bus transition detection
bus_changed = sv.get("addr[15:0]", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
```

#### Complex Queries with Set Operations

```python
# Rising clock edges when enable is high
clk_rising = sv.get("clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
enable_high = sv.get("enable", lambda sm1, s, sp1: s == 1)
valid_clocks = clk_rising & enable_high

# Data changes while not in reset
data_changes = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
not_reset = sv.get("reset", lambda sm1, s, sp1: s == 0)
valid_changes = data_changes & not_reset

# Either signal is high
sig1_high = sv.get("sig1", lambda sm1, s, sp1: s == 1)
sig2_high = sv.get("sig2", lambda sm1, s, sp1: s == 1)
either_high = sig1_high | sig2_high

# Exclusive high (one but not both)
exclusive_high = sig1_high ^ sig2_high
```

#### Advanced Pattern Detection

```python
# Detect setup violation: data changes right before clock edge
data_change = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
clk_about_to_rise = sv.get("clk", lambda sm1, s, sp1: s == 0 and sp1 == 1)
setup_violations = data_change & clk_about_to_rise

# Handshake protocol: valid and ready both high
valid_high = sv.get("valid", lambda sm1, s, sp1: s == 1)
ready_high = sv.get("ready", lambda sm1, s, sp1: s == 1)
handshake_times = valid_high & ready_high

# State machine transitions (binary "00" = 0, "01" = 1)
state_a = sv.get("state[1:0]", lambda sm1, s, sp1: s == 0)
state_b = sv.get("state[1:0]", lambda sm1, s, sp1: s == 1)
# Times when transitioning from state A to state B
transition = sv.get("state[1:0]", lambda sm1, s, sp1: sm1 == 0 and s == 1)
```

## Flexible Signatures

Signal condition functions can accept 1, 2, or 3 parameters, automatically detected:

### 1-Parameter: Current Value Only

Use when you only need the current signal value:

```python
# Find all times when signal is high
high_times = sv.get("valid", lambda s: s == 1)

# Arithmetic comparisons
large_values = sv.get("counter", lambda s: s is not None and s > 100)

# With String ValueType
pattern = sv.get("bus[3:0]", lambda s: s == "1111", value_type=String())
```

**Boundary behavior**: No boundary effects - all timesteps available.

### 2-Parameter: Previous and Current

Use for edge detection and transitions:

```python
# Rising edge detection (classic pattern)
rising = sv.get("clk", lambda sm1, s: sm1 == 0 and s == 1)

# Falling edge detection
falling = sv.get("clk", lambda sm1, s: sm1 == 1 and s == 0)

# Change detection (any transition)
changes = sv.get("data", lambda sm1, s: sm1 is not None and sm1 != s)
```

**Boundary behavior**: First timestep excluded when `none_ignore=True` (default), since `sm1=None` there.

### 3-Parameter: Previous, Current, and Next

Use for complex temporal patterns (classic mode):

```python
# Rising edge (backward-looking)
rising = sv.get("clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)

# Glitch detection (short pulse)
glitch = sv.get("sig", lambda sm1, s, sp1: sm1 == 0 and s == 1 and sp1 == 0)

# Change detection
changes = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
```

**Boundary behavior**: First timestep has `sm1=None`, last has `sp1=None` (excluded with `none_ignore=True`).

### Choosing the Right Signature

| Signature | Use Case | Boundary Impact |
|-----------|----------|-----------------|
| 1-param   | Simple state checks (high/low, thresholds) | None |
| 2-param   | Edge detection and transitions | First timestep |
| 3-param   | Complex temporal patterns (glitches, multi-cycle) | First & last |

## Value Types

SetVCD supports three ValueType options to control how signal values are converted before being passed to your condition lambdas:

### Raw() - Integer Conversion (Default)

Converts binary strings to decimal integers. X/Z values become `None`. This is the default behavior.

```python
from setVCD import SetVCD, Raw

sv = SetVCD("simulation.vcd", clock="clk")

# Default behavior (Raw is implicit)
rising = sv.get("data[7:0]", lambda sm1, s, sp1: sm1 is not None and sm1 < s)

# Explicit Raw (same as above)
rising = sv.get("data[7:0]", lambda sm1, s, sp1: sm1 is not None and sm1 < s, value_type=Raw())

# Multi-bit signals converted to decimal
# Binary "00001010" → integer 10
high_values = sv.get("bus[7:0]", lambda sm1, s, sp1: s is not None and s > 128)
```

### String() - Preserve Raw Strings

Keeps vcdvcd's raw string representation, including X/Z values as literal strings. Useful for detecting unknown states.

```python
from setVCD import SetVCD, String

sv = SetVCD("simulation.vcd", clock="clk")

# Detect X/Z values in data bus
has_x = sv.get("data[7:0]",
               lambda sm1, s, sp1: s is not None and 'x' in s.lower(),
               value_type=String())

# String pattern matching
all_ones = sv.get("bus[3:0]",
                  lambda sm1, s, sp1: s == "1111",
                  value_type=String())

# Get string values
values = sv.get_values("data", timesteps, value_type=String())
# Returns: [(50, "1010"), (60, "1111"), (70, "xxxx"), ...]
```

**X/Z Handling:** X and Z values are preserved as strings (`"x"`, `"z"`, `"xxxx"`, etc.)

### FP() - Fixed-Point to Float

Converts binary strings to floating-point by interpreting them as fixed-point numbers with configurable fractional bits and optional sign bit.

```python
from setVCD import SetVCD, FP

sv = SetVCD("simulation.vcd", clock="clk")

# Temperature sensor with 8 fractional bits (Q8.8 format)
# Binary "0001100100000000" → 25.0 degrees
above_threshold = sv.get("temp_sensor[15:0]",
                        lambda sm1, s, sp1: s is not None and s > 25.5,
                        value_type=FP(frac=8, signed=False))

# Signed fixed-point (Q3.4 format - 1 sign bit, 3 integer bits, 4 fractional bits)
# Binary "11111110" → -0.125 (two's complement)
negative_values = sv.get("signed_value[7:0]",
                        lambda sm1, s, sp1: s is not None and s < 0,
                        value_type=FP(frac=4, signed=True))

# Get fixed-point values
voltages = sv.get_values("adc_reading[11:0]", timesteps,
                        value_type=FP(frac=12, signed=False))
# Returns: [(50, 1.2), (60, 2.5), (70, 3.8), ...]
```

**X/Z Handling:** X and Z values become `float('nan')`. Use `math.isnan()` to detect them:

```python
import math

# Filter out NaN values
valid_readings = sv.get("sensor",
                       lambda sm1, s, sp1: s is not None and not math.isnan(s),
                       value_type=FP(frac=8, signed=False))
```

**Fixed-Point Formula:**
- Unsigned: `value = int_value / (2^frac)`
- Signed: Two's complement, then divide by `2^frac`

**Examples:**
- `"00001010"` with `frac=4, signed=False` → `10 / 16 = 0.625`
- `"11111110"` with `frac=4, signed=True` → `-2 / 16 = -0.125`
- `"00010000"` with `frac=0, signed=False` → `16 / 1 = 16.0` (integer)

### Hardware Use Cases

**Raw (Default):** Most general-purpose verification - state machines, counters, addresses, data comparisons

**String:** Debugging X/Z propagation, detecting uninitialized signals, bit-pattern analysis

**FP:** Analog interfaces (ADC/DAC), sensor data, fixed-point DSP verification, power/temperature monitors

## X/Z and None Handling

SetVCD provides fine-grained control over how x/z (unknown/high-impedance) values and None values are handled during signal filtering.

### X/Z Handling Methods

Control how x/z values in VCD signals are processed using the `xz_method` parameter:

#### XZIgnore() - Skip X/Z Timesteps (Default)

Skips any timestep where any signal value (sm1, s, or sp1) contains x or z. This is the most efficient option.

```python
from setVCD import SetVCD, XZIgnore

# Default behavior - skip all x/z timesteps
sv = SetVCD("sim.vcd", clock="clk")  # xz_method=XZIgnore() by default
valid = sv.get("data", lambda sm1, s, sp1: s == 5)
# Timesteps with x/z are automatically excluded
```

#### XZNone() - Convert X/Z to None

Converts x/z values to None (for Raw/FP) or preserves them as strings (for String), then passes to the filter function.

```python
from setVCD import SetVCD, XZNone, Raw

sv = SetVCD("sim.vcd", clock="clk", xz_method=XZNone(), none_ignore=False)

# Filter can explicitly handle x/z values (converted to None)
valid_or_unknown = sv.get("data",
                          lambda sm1, s, sp1: s is None or s == 5,
                          value_type=Raw())
```

#### XZValue(replacement) - Replace X/Z with Value

Replaces x/z values with a specific integer value before conversion. For String type, x/z is preserved (replacement ignored).

```python
from setVCD import SetVCD, XZValue, Raw

# Replace x/z with 0 for comparison
sv = SetVCD("sim.vcd", clock="clk", xz_method=XZValue(replacement=0))
result = sv.get("data", lambda sm1, s, sp1: s == 0, value_type=Raw())
# x/z values are treated as 0
```

### None Handling

Control whether None values (from boundaries or x/z) are passed to filter functions using `none_ignore`:

#### none_ignore=True (Default)

Skips timesteps where any value (sm1, s, sp1) is None. This includes:
- Boundary conditions: sm1 at t=0, sp1 at last_clock
- X/Z values when using XZNone()

```python
from setVCD import SetVCD

sv = SetVCD("sim.vcd", clock="clk")  # none_ignore=True by default

# Boundary timesteps (t=0, last_clock) are skipped
result = sv.get("data", lambda sm1, s, sp1: s == 5)
# Result will not include t=0 or last_clock
```

#### none_ignore=False - Pass None to Filter

Allows filter functions to receive and handle None values explicitly.

```python
from setVCD import SetVCD, XZNone

sv = SetVCD("sim.vcd", clock="clk", xz_method=XZNone(), none_ignore=False)

# Filter receives None at boundaries
boundary_times = sv.get("data", lambda sm1, s, sp1: sm1 is None or sp1 is None)
# Result includes t=0 (sm1=None) and last_clock (sp1=None)
```

### Interaction Matrix

| xz_method    | none_ignore | Behavior at X/Z     | Behavior at Boundaries   |
|--------------|-------------|---------------------|-------------------------|
| XZIgnore()   | True        | Skipped (x/z check) | Skipped (None check)    |
| XZIgnore()   | False       | Skipped (x/z check) | Passed to filter        |
| XZNone()     | True        | Skipped (None check)| Skipped (None check)    |
| XZNone()     | False       | Passed as None      | Passed as None          |
| XZValue(n)   | True        | Replaced with n     | Skipped (None check)    |
| XZValue(n)   | False       | Replaced with n     | Passed as None          |

**Note:** XZNone() + none_ignore=True is functionally equivalent to XZIgnore()

### Migration from v0.3.x

Version 0.4.0 introduces **breaking changes** to x/z and None handling defaults:

**Old behavior (v0.3.x and earlier):**
- X/Z values converted to None and passed to filters
- None values (boundaries) passed to filters
- Filter functions needed to handle None explicitly

**New behavior (v0.4.0+):**
- X/Z timesteps skipped by default (`xz_method=XZIgnore()`)
- None values skipped by default (`none_ignore=True`)
- Filter functions receive cleaner, non-None values

**To restore old behavior:**
```python
from setVCD import SetVCD, XZNone

# v0.4.0+ with old behavior
sv = SetVCD("sim.vcd", clock="clk", xz_method=XZNone(), none_ignore=False)
```

**Recommended migration:**
- Review filter functions that check for None values
- Consider using new defaults for cleaner logic
- Add explicit `xz_method=XZNone(), none_ignore=False` if old behavior needed

## Future Enhancements

Planned for future versions:

- Higher-order operations for signal conditions
- Performance optimization for large VCD files
- Streaming interface for very large files
- MCP (Model Context Protocol) integration
