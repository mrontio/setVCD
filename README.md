# SetVCD
Programmatically inspect hardware VCD signals using a high-level functional interface.

Higher-order programming constructs and set operations are a natural fit for inspecting VCD signals, and this Python library allows you to easily specify, in text, what simulation timesteps matter to functional correctness.

## Motivating Example
Say you are debugging a streaming interface, you often only care about the values of the data at timesteps meeting the following condition:

$\text{Rising edge} \land \text{Reset is 0} \land \text{ready} \land \text{valid}$

![img/gtkwave.png](img/gtkwave.png "GTKWave screenshot of streaming interface we want to debug.")

You can filter through an individual signal with a filter function of this signature:

$(\text{Bits}, \text{Bits}, \text{Bits}) \rightarrow \text{Bool}$

with the left-hand tuple representing *values* at timestep $t$: $(t-1, t, t+1)$. 

We then define our `get` method, which takes the name of the signal (as a String), a function with the above signature, and returns a set of *timesteps*:

$\texttt{get}: (\text{String}, ((\text{Bits}, \text{Bits}, \text{Bits}) \rightarrow \text{Bool})) \rightarrow \text{Set(Timestep)}$

As what is returned is a set, you can then use [set operations](https://en.wikipedia.org/wiki/Set_(mathematics)#Basic_operations) to manipulate them as needed, and finally extract the values from your desired signal using our `get_value` function:

$\texttt{get-value}: (\text{String}, \text{Set(Timestep)}) \rightarrow \text{List((Timestep, Bits))}$

Here's an example of finding the rising edges of the clock signal `TOP.clk` of our test wavefile `wave.vcd`:
```python
from setVCD import SetVCD

# Load VCD file
vcd_path = "./tests/fixtures/wave.vcd"
sv = SetVCD(vcd_path, clock="TOP.clk")

rising_edges = sv.get("TOP.clk", lambda tm1, t, tp1: tm1 == 0 and t == 1)
print(rising_edges)
# {34, 36, 38, 40, 42, 44, ...}
```

Because `rising_edges` is returned as a set, we can use set operations to combine it with other signals:
```python
# Get times when the reset signal is 0
reset_is_0 = sv.get("TOP.reset", lambda tm1, t, tp1: t == 0)
# Use set intersection to get valid clock updates.
clock_update = rising_edges & reset_is_0
```

Finally, you can search the wavefile with a regex (e.g. "output"), and apply the same operations to it:
```python
# Find VCD signals relating to keyword "output"
sv.search("output")

# Get times when output_valid and output_ready are asserted.
out_valid = sv.get("TOP.Accelerator.io_output_valid", lambda tm1, t, tp1: t == 1)
out_ready = sv.get("TOP.Accelerator.io_output_ready", lambda tm1, t, tp1: t == 1)

# Get timesteps of valid outputs
valid_output_timesteps = rising_edges & reset0 & out_ready & out_valid

# Get the values of the Stream `value` signal (the data) at timesteps when it is valid
outputs = sv.get_values("TOP.Accelerator.io_output_payload_fragment_value_0[0:0]", valid_output_timesteps)
print(outputs)
# [(52, 0), (62, 0), (72, 1), ...]  # Integer values
```

## Overview

SetVCD is a Python package for analyzing Verilog VCD files and extracting time points where specific signal conditions are met. It provides a simple, type-safe interface for working with simulation waveforms using set-based operations.

## Installation
Whilst we are in pre-release, please install the package in a local venv:
```bash
python -m venv ./vcd-venv
source vcd-venv/bin/activate
git clone https://github.com/mrontio/setVCD.git
cd setVCD
pip install .
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
## Future Enhancements

Planned for future versions:

- Fixed-point to Python float translation for multi-bit signals
- Higher-order operations for signal conditions
- Performance optimization for large VCD files
- Streaming interface for very large files
- MCP (Model Context Protocol) integration
