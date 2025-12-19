# SetVCD

Convert VCD (Value Change Dump) signals to sets of time points based on custom conditions.

## Overview

SetVCD is a Python package for analyzing Verilog VCD files and extracting time points where specific signal conditions are met. It provides a simple, type-safe interface for working with simulation waveforms using set-based operations.

## Installation

```bash
pip install setVCD
```

## Example
This uses the example VCD file that we use for testing.
```python
from setVCD import SetVCD

# Load VCD file
vcd_path = "./tests/fixtures/wave.vcd"
sv = SetVCD(vcd_path, clock="TOP.clk")

# Example: Examine values that our accelerator outputs
## Find VCD signals relating to output
sv.search("output")

## Get rising edges, reset = 0, output valid & ready
rising_edges = sv.get("TOP.clk", lambda tm1, t, tp1: tm1 == "0" and t == "1")
reset0 = sv.get("TOP.reset", lambda tm1, t, tp1: t == "0")
out_valid = sv.get("TOP.Accelerator.io_output_valid", lambda tm1, t, tp1: t == "1")
out_ready = sv.get("TOP.Accelerator.io_output_ready", lambda tm1, t, tp1: t == "1")

## Get their intersection
valid_output_timesteps = rising_edges & reset0 & out_ready & out_valid

## Extract the values at the timesteps when everything else is valid
outputs = sv.get_values("TOP.Accelerator.io_output_payload_fragment_value_0[0:0]", valid_output_timesteps)
print(outputs)
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

- `sm1`: Signal value at time-1 (None at time 0)
- `s`: Signal value at current time
- `sp1`: Signal value at time+1 (None at last time)

Signal values are strings: `'0'`, `'1'`, `'x'`, `'z'`, or multi-bit like `'0101'`.

The callback should return `True` to include that time point in the result set.

### Examples

#### Basic Signal Detection

```python
# Rising edge: 0 -> 1 transition
rising = sv.get("clk", lambda sm1, s, sp1: sm1 == "0" and s == "1")

# Falling edge: 1 -> 0 transition
falling = sv.get("clk", lambda sm1, s, sp1: sm1 == "1" and s == "0")

# Any edge: value changed
edges = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)

# Level high
high = sv.get("enable", lambda sm1, s, sp1: s == "1")

# Level low
low = sv.get("reset", lambda sm1, s, sp1: s == "0")
```

#### Multi-bit Signals

```python
# Specific pattern on a bus
pattern = sv.get("bus[3:0]", lambda sm1, s, sp1: s == "1010")

# Bus is non-zero
active = sv.get("data[7:0]", lambda sm1, s, sp1: s != "00000000")

# Bus transition detection
bus_changed = sv.get("addr[15:0]", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
```

#### Complex Queries with Set Operations

```python
# Rising clock edges when enable is high
clk_rising = sv.get("clk", lambda sm1, s, sp1: sm1 == "0" and s == "1")
enable_high = sv.get("enable", lambda sm1, s, sp1: s == "1")
valid_clocks = clk_rising & enable_high

# Data changes while not in reset
data_changes = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
not_reset = sv.get("reset", lambda sm1, s, sp1: s == "0")
valid_changes = data_changes & not_reset

# Either signal is high
sig1_high = sv.get("sig1", lambda sm1, s, sp1: s == "1")
sig2_high = sv.get("sig2", lambda sm1, s, sp1: s == "1")
either_high = sig1_high | sig2_high

# Exclusive high (one but not both)
exclusive_high = sig1_high ^ sig2_high
```

#### Advanced Pattern Detection

```python
# Detect setup violation: data changes right before clock edge
data_change = sv.get("data", lambda sm1, s, sp1: sm1 is not None and sm1 != s)
clk_about_to_rise = sv.get("clk", lambda sm1, s, sp1: s == "0" and sp1 == "1")
setup_violations = data_change & clk_about_to_rise

# Handshake protocol: valid and ready both high
valid_high = sv.get("valid", lambda sm1, s, sp1: s == "1")
ready_high = sv.get("ready", lambda sm1, s, sp1: s == "1")
handshake_times = valid_high & ready_high

# State machine transitions
state_a = sv.get("state[1:0]", lambda sm1, s, sp1: s == "00")
state_b = sv.get("state[1:0]", lambda sm1, s, sp1: s == "01")
# Times when transitioning from state A to state B
transition = sv.get("state[1:0]", lambda sm1, s, sp1: sm1 == "00" and s == "01")
```
## Future Enhancements

Planned for future versions:

- Fixed-point to Python float translation for multi-bit signals
- Higher-order operations for signal conditions
- Performance optimization for large VCD files
- Streaming interface for very large files
- MCP (Model Context Protocol) integration
