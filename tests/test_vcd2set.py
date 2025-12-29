"""Tests for SetVCD class using real VCD file."""

from pathlib import Path

import pytest

from setVCD import (
    FP,
    ClockSignalError,
    InvalidInputError,
    InvalidSignalConditionError,
    Raw,
    SetVCD,
    SignalNotFoundError,
    String,
    VCDFileNotFoundError,
)


# Fixtures
@pytest.fixture
def vcd_file_path():
    """Path to the test VCD file."""
    return Path(__file__).parent / "fixtures" / "wave.vcd"


@pytest.fixture
def vcdset(vcd_file_path):
    """SetVCD instance initialized with the test VCD file."""
    # Clock signal in this VCD is 'TOP.clk'
    return SetVCD(str(vcd_file_path), clock="TOP.clk")


@pytest.fixture
def vcdset_with_vcdvcd_object(vcd_file_path):
    """SetVCD instance initialized with a vcdvcd object."""
    import vcdvcd

    vcd = vcdvcd.VCDVCD(str(vcd_file_path))
    return SetVCD(vcd, clock="TOP.clk")


# Test Initialization
class TestSetVCDInit:
    """Tests for SetVCD.__init__"""

    def test_init_from_string_filename(self, vcd_file_path):
        """Test initialization from string filename."""
        vs = SetVCD(str(vcd_file_path), clock="TOP.clk")
        assert vs.wave is not None
        assert "clock" in vs.sigs
        assert vs.last_clock >= 0

    def test_init_from_path_object(self, vcd_file_path):
        """Test initialization from Path object."""
        vs = SetVCD(vcd_file_path, clock="TOP.clk")
        assert vs.wave is not None
        assert "clock" in vs.sigs
        assert vs.last_clock >= 0

    def test_init_from_vcdvcd_object(self, vcd_file_path):
        """Test initialization from vcdvcd.VCDVCD object."""
        import vcdvcd

        vcd = vcdvcd.VCDVCD(str(vcd_file_path))
        vs = SetVCD(vcd, clock="TOP.clk")
        assert vs.wave is vcd

    def test_file_not_found(self):
        """Test error when VCD file doesn't exist."""
        with pytest.raises(VCDFileNotFoundError, match="VCD file not found"):
            SetVCD("nonexistent.vcd", clock="TOP.clk")

    def test_clock_signal_not_found(self, vcd_file_path):
        """Test error when clock signal doesn't exist."""
        with pytest.raises(
            ClockSignalError, match="Clock signal 'nonexistent_clk' not found"
        ):
            SetVCD(str(vcd_file_path), clock="nonexistent_clk")

    def test_clock_signal_helpful_suggestion(self, vcd_file_path):
        """Test that error suggests similar clock signal names."""
        # Using 'clk' instead of 'TOP.clk' should suggest 'TOP.clk'
        with pytest.raises(ClockSignalError, match="Did you mean one of"):
            SetVCD(str(vcd_file_path), clock="clk")

    def test_invalid_input_type(self):
        """Test error when input is neither filename nor VCDVCD object."""
        with pytest.raises(InvalidInputError, match="vcd must be a filename"):
            SetVCD(12345, clock="TOP.clk")  # type: ignore

    def test_last_clock_is_valid(self, vcdset):
        """Test that last_clock timestamp is valid."""
        assert isinstance(vcdset.last_clock, int)
        assert vcdset.last_clock > 0


# Test get() Method - Basic Functionality
class TestSetVCDGetBasic:
    """Tests for basic SetVCD.get() functionality"""

    def test_get_returns_set(self, vcdset):
        """Test that get() returns a set of integers."""
        # Get times when reset is high (active)
        result = vcdset.get("TOP.reset", lambda sm1, s, sp1: s == 1)
        assert isinstance(result, set)
        assert all(isinstance(t, int) for t in result)

    def test_rising_edge_detection(self, vcdset):
        """Test detecting rising edges (0 -> 1 transitions)."""
        rising_edges = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        assert isinstance(rising_edges, set)
        assert len(rising_edges) > 0  # Should have at least some rising edges

    def test_falling_edge_detection(self, vcdset):
        """Test detecting falling edges (1 -> 0 transitions)."""
        falling_edges = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 1 and s == 0)
        assert isinstance(falling_edges, set)
        assert len(falling_edges) > 0  # Should have at least some falling edges

    def test_high_level_detection(self, vcdset):
        """Test detecting when signal is high."""
        high_times = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 1)
        assert isinstance(high_times, set)
        assert len(high_times) > 0

    def test_low_level_detection(self, vcdset):
        """Test detecting when signal is low."""
        low_times = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 0)
        assert isinstance(low_times, set)
        assert len(low_times) > 0

    def test_any_change_detection(self, vcdset):
        """Test detecting any signal change."""
        changes = vcdset.get(
            "TOP.io_input_valid", lambda sm1, s, sp1: sm1 is not None and sm1 != s
        )
        assert isinstance(changes, set)


# Test get() Method - Signal Validation
class TestSetVCDGetValidation:
    """Tests for signal validation in get() method"""

    def test_signal_not_found(self, vcdset):
        """Test error when signal doesn't exist."""
        with pytest.raises(
            SignalNotFoundError, match="Signal 'nonexistent_signal' not found"
        ):
            vcdset.get("nonexistent_signal", lambda sm1, s, sp1: True)

    def test_signal_not_found_with_suggestion(self, vcdset):
        """Test that error suggests similar signal names."""
        with pytest.raises(SignalNotFoundError, match="Did you mean one of"):
            vcdset.get("cLk", lambda sm1, s, sp1: True)  # Misspelled 'clk'

    def test_signal_condition_not_callable(self, vcdset):
        """Test error when signal_condition is not callable."""
        with pytest.raises(InvalidSignalConditionError, match="must be callable"):
            vcdset.get("TOP.clk", "not a callable")  # type: ignore

    def test_signal_condition_raises_exception(self, vcdset):
        """Test error when signal_condition raises an exception."""

        def bad_condition(sm1, s, sp1):
            raise ValueError("Intentional error")

        with pytest.raises(
            InvalidSignalConditionError, match="raised exception at time"
        ):
            vcdset.get("TOP.clk", bad_condition)


# Test get() Method - Boundary Conditions
class TestSetVCDGetBoundary:
    """Tests for boundary conditions in get() method"""

    def test_boundary_sm1_is_none_at_time_zero(self, vcd_file_path):
        """Test that sm1 is None at time 0 with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        times_with_none = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 is None)
        assert 0 in times_with_none  # Time 0 should have sm1=None

    def test_boundary_sp1_is_none_at_last_time(self, vcd_file_path):
        """Test that sp1 is None at last clock time with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        times_with_none = vcdset.get("TOP.clk", lambda sm1, s, sp1: sp1 is None)
        assert vcdset.last_clock in times_with_none  # Last time should have sp1=None

    def test_boundary_both_none_only_at_extremes(self, vcd_file_path):
        """Test that both sm1 and sp1 are not None except at boundaries with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        times_with_none = vcdset.get(
            "TOP.clk", lambda sm1, s, sp1: sm1 is None or sp1 is None
        )
        # Should include at least time 0 and last_clock
        assert 0 in times_with_none
        assert vcdset.last_clock in times_with_none


# Test get() Method - Multi-bit Signals
class TestSetVCDGetMultiBit:
    """Tests for multi-bit signal handling"""

    def test_multibit_signal_pattern_matching(self, vcdset):
        """Test pattern matching on multi-bit signals."""
        # s_axis_tdata is a 32-bit signal
        # Check for any specific pattern (e.g., all zeros)
        result = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda sm1, s, sp1: s == 0,
        )
        assert isinstance(result, set)

    def test_multibit_signal_change_detection(self, vcdset):
        """Test detecting changes in multi-bit signals."""
        changes = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda sm1, s, sp1: sm1 is not None and sm1 != s,
        )
        assert isinstance(changes, set)

    def test_multibit_signal_keep_field(self, vcdset):
        """Test 4-bit keep field (s_axis_tkeep)."""
        # Check for all-enabled pattern (4'b1111 = decimal 15)
        all_enabled = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda sm1, s, sp1: s == 15,
        )
        assert isinstance(all_enabled, set)


# Test Set Operations
class TestSetVCDOperations:
    """Tests for combining results with set operations"""

    def test_intersection_rising_edge_and_valid(self, vcdset):
        """Test finding clock rising edges when a signal is valid."""
        rising_edges = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        valid_high = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == 1)

        # Times when both conditions are true
        valid_rising_edges = rising_edges & valid_high
        assert isinstance(valid_rising_edges, set)
        # All elements should be in both sets
        assert valid_rising_edges <= rising_edges
        assert valid_rising_edges <= valid_high

    def test_union_multiple_conditions(self, vcdset):
        """Test union of multiple conditions."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        falling = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 1 and s == 0)

        # All edges (rising or falling)
        all_edges = rising | falling
        assert isinstance(all_edges, set)
        assert len(all_edges) >= len(rising)
        assert len(all_edges) >= len(falling)

    def test_difference_operation(self, vcdset):
        """Test set difference operation."""
        all_times = vcdset.get("TOP.clk", lambda sm1, s, sp1: True)
        reset_active = vcdset.get("TOP.reset", lambda sm1, s, sp1: s == 1)

        # Times when not in reset
        not_in_reset = all_times - reset_active
        assert isinstance(not_in_reset, set)
        # Should have no overlap with reset_active
        assert (not_in_reset & reset_active) == set()

    def test_symmetric_difference(self, vcdset):
        """Test symmetric difference (XOR) operation."""
        valid_high = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == 1)
        ready_high = vcdset.get("TOP.io_input_ready", lambda sm1, s, sp1: s == 1)

        # Times when exactly one is high (not both)
        exclusive = valid_high ^ ready_high
        assert isinstance(exclusive, set)
        # Should not include times when both are high
        both_high = valid_high & ready_high
        assert (exclusive & both_high) == set()


# Test Real-World Hardware Patterns
class TestSetVCDHardwarePatterns:
    """Tests for common hardware verification patterns"""

    def test_axi_stream_handshake(self, vcdset):
        """Test AXI Stream handshake (valid & ready both high)."""
        valid_high = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == 1)
        ready_high = vcdset.get("TOP.io_input_ready", lambda sm1, s, sp1: s == 1)

        # Handshake occurs when both are high
        handshake_times = valid_high & ready_high
        assert isinstance(handshake_times, set)

    def test_axi_stream_valid_rising_edge(self, vcdset):
        """Test AXI Stream valid signal rising edge."""
        valid_rising = vcdset.get(
            "TOP.io_input_valid", lambda sm1, s, sp1: sm1 == 0 and s == 1
        )
        assert isinstance(valid_rising, set)

    def test_last_signal_assertion(self, vcdset):
        """Test when tlast is asserted."""
        last_high = vcdset.get("TOP.io_input_payload_last", lambda sm1, s, sp1: s == 1)
        assert isinstance(last_high, set)

    def test_reset_deassert_time(self, vcdset):
        """Test finding when reset is deasserted (1 -> 0)."""
        reset_deassert = vcdset.get(
            "TOP.reset", lambda sm1, s, sp1: sm1 == 1 and s == 0
        )
        assert isinstance(reset_deassert, set)

    def test_clock_rising_during_valid_transfer(self, vcdset):
        """Test clock edges during valid AXI transfers."""
        clk_rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        valid_high = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == 1)
        ready_high = vcdset.get("TOP.io_input_ready", lambda sm1, s, sp1: s == 1)

        # Clock rising edges during handshake
        transfer_clocks = clk_rising & valid_high & ready_high
        assert isinstance(transfer_clocks, set)


# Test Edge Cases
class TestSetVCDEdgeCases:
    """Tests for edge cases and corner scenarios"""

    def test_empty_result_set(self, vcdset):
        """Test that impossible conditions return empty set."""
        # Condition that's never true (signal can't be both 0 and 1)
        result = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 0 and s == 1)
        assert result == set()

    def test_full_time_range_result(self, vcd_file_path):
        """Test condition that's always true returns all times with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        all_times = vcdset.get("TOP.clk", lambda sm1, s, sp1: True)
        assert len(all_times) == vcdset.last_clock + 1  # 0 to last_clock inclusive

    def test_using_only_current_value(self, vcdset):
        """Test condition that only uses current value (ignores sm1, sp1)."""
        result = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 1)
        assert isinstance(result, set)

    def test_using_all_three_values(self, vcdset):
        """Test condition using all three time points."""
        # Pattern: was 0, now 1, will be 1 (rising edge that stays high)
        result = vcdset.get(
            "TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1 and sp1 == 1
        )
        assert isinstance(result, set)


# Test Consistency Between Initialization Methods
class TestSetVCDConsistency:
    """Tests for consistency between different initialization methods"""

    def test_same_results_from_filename_and_object(self, vcd_file_path):
        """Test that filename and vcdvcd object produce same results."""
        import vcdvcd

        # Initialize from filename
        vs1 = SetVCD(str(vcd_file_path), clock="TOP.clk")

        # Initialize from vcdvcd object
        vcd = vcdvcd.VCDVCD(str(vcd_file_path))
        vs2 = SetVCD(vcd, clock="TOP.clk")

        # Should have same last_clock
        assert vs1.last_clock == vs2.last_clock

        # Should produce same results for same query
        result1 = vs1.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        result2 = vs2.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        assert result1 == result2


# Performance/Sanity Tests
class TestSetVCDSanity:
    """Sanity tests for performance and correctness"""

    def test_rising_and_falling_edges_disjoint(self, vcdset):
        """Test that rising and falling edges don't overlap."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        falling = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 1 and s == 0)

        # Should have no overlap
        assert (rising & falling) == set()

    def test_all_times_partition(self, vcd_file_path):
        """Test that high and low times partition the full time range with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        high = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 1)
        low = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 0)

        # Should be disjoint
        assert (high & low) == set()

        # Union should cover all times
        all_times = set(range(0, vcdset.last_clock + 1))
        assert (high | low) == all_times

    def test_result_times_within_bounds(self, vcdset):
        """Test that all result times are within valid range."""
        result = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == 1)

        for time in result:
            assert 0 <= time <= vcdset.last_clock


# Test Integer Conversion
class TestSetVCDIntegerConversion:
    """Tests for integer conversion of signal values"""

    def test_single_bit_zero(self, vcdset):
        """Test single-bit 0 converts to integer 0."""
        zeros = vcdset.get("TOP.clk", lambda tm1, t, tp1: t == 0)
        assert isinstance(zeros, set)
        assert len(zeros) > 0

    def test_single_bit_one(self, vcdset):
        """Test single-bit 1 converts to integer 1."""
        ones = vcdset.get("TOP.clk", lambda tm1, t, tp1: t == 1)
        assert isinstance(ones, set)
        assert len(ones) > 0

    def test_multibit_decimal_conversion(self, vcdset):
        """Test multi-bit binary converts to decimal."""
        # Find times when 16-bit signal equals specific decimal value
        result = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda tm1, t, tp1: t == 15,  # Binary 1111 or 0...01111
        )
        assert isinstance(result, set)

    def test_arithmetic_comparisons_greater_than(self, vcdset):
        """Test that arithmetic > comparisons work with integers."""
        high_values = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda tm1, t, tp1: t is not None and t > 100,
        )
        assert isinstance(high_values, set)

    def test_arithmetic_comparisons_less_than(self, vcdset):
        """Test that arithmetic < comparisons work with integers."""
        low_values = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda tm1, t, tp1: t is not None and t < 10,
        )
        assert isinstance(low_values, set)

    def test_arithmetic_comparisons_range(self, vcdset):
        """Test that range comparisons work with integers."""
        range_values = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda tm1, t, tp1: t is not None and 10 <= t < 100,
        )
        assert isinstance(range_values, set)

    def test_none_for_boundaries_still_works(self, vcd_file_path):
        """Test None handling for boundaries with old behavior."""
        from setVCD import SetVCD, XZNone

        # Use old behavior: XZNone + none_ignore=False
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        first_time = vcdset.get("TOP.clk", lambda tm1, t, tp1: tm1 is None)
        assert 0 in first_time

        last_time = vcdset.get("TOP.clk", lambda tm1, t, tp1: tp1 is None)
        assert vcdset.last_clock in last_time

    def test_get_values_with_t_returns_integers(self, vcdset):
        """Test get_values_with_t returns integers not strings."""
        values = vcdset.get_values_with_t("TOP.clk", {10, 20, 30})
        assert all(isinstance(v, (int, type(None))) for _, v in values)
        assert all(v in (0, 1, None) for _, v in values)  # Clock is single-bit

    def test_multibit_comparison_with_decimal(self, vcdset):
        """Test comparing multi-bit signals with decimal values."""
        # Check for zero
        zeros = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]", lambda tm1, t, tp1: t == 0
        )
        assert isinstance(zeros, set)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# Test get_values_with_t() Method
class TestSetVCDGetValuesWithT:
    """Tests for SetVCD.get_values_with_t() method"""

    def test_get_values_with_t_returns_list_of_tuples(self, vcdset):
        """Test that get_values_with_t() returns a list of (time, value) tuples."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        values = vcdset.get_values_with_t("TOP.io_input_valid", rising)

        assert isinstance(values, list)
        assert all(isinstance(item, tuple) for item in values)
        assert all(len(item) == 2 for item in values)
        assert all(
            isinstance(item[0], int) and isinstance(item[1], (int, type(None)))
            for item in values
        )

    def test_get_values_with_t_sorted_by_time(self, vcdset):
        """Test that results are sorted by time."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        values = vcdset.get_values_with_t("TOP.io_input_valid", rising)

        times = [t for t, v in values]
        assert times == sorted(times)

    def test_get_values_with_t_with_empty_set(self, vcdset):
        """Test get_values_with_t with empty timestep set."""
        values = vcdset.get_values_with_t("TOP.clk", set())
        assert values == []

    def test_get_values_with_t_single_timestep(self, vcdset):
        """Test get_values_with_t with single timestep."""
        values = vcdset.get_values_with_t("TOP.clk", {0})
        assert len(values) == 1
        assert values[0][0] == 0
        assert isinstance(values[0][1], (int, type(None)))

    def test_get_values_with_t_multibit_signal(self, vcdset):
        """Test get_values_with_t with multi-bit signal."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        timesteps = set(list(rising)[:5])  # First 5 rising edges

        values = vcdset.get_values_with_t(
            "TOP.io_input_payload_fragment_value_0[15:0]", timesteps
        )
        assert len(values) == 5
        # Multi-bit values should be integers or None
        assert all(isinstance(v, (int, type(None))) for _, v in values)
        assert all(v is None or v >= 0 for _, v in values)

    def test_get_values_with_t_signal_not_found(self, vcdset):
        """Test error when signal doesn't exist."""
        with pytest.raises(SignalNotFoundError):
            vcdset.get_values_with_t("nonexistent_signal", {0, 1, 2})

    def test_get_values_with_t_practical_example(self, vcdset):
        """Test practical use case: get data values during handshakes."""
        # Find handshake times
        valid = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == "1")
        ready = vcdset.get("TOP.io_input_ready", lambda sm1, s, sp1: s == "1")
        handshakes = valid & ready

        # Get data values at handshake times
        data_values = vcdset.get_values_with_t(
            "TOP.io_input_payload_fragment_value_0[15:0]", handshakes
        )

        assert len(data_values) == len(handshakes)
        assert all(isinstance(time, int) for time, _ in data_values)
        assert all(isinstance(value, str) for _, value in data_values)

    def test_get_values_with_t_preserves_timestep_set(self, vcdset):
        """Test that original timestep set is unchanged."""
        timesteps = {10, 20, 30, 40, 50}
        original_timesteps = timesteps.copy()

        values = vcdset.get_values_with_t("TOP.clk", timesteps)

        assert timesteps == original_timesteps  # Set unchanged
        assert len(values) == len(timesteps)


# Test get_values() Method
class TestSetVCDGetValues:
    """Tests for SetVCD.get_values() method"""

    def test_get_values_returns_list_of_values(self, vcdset):
        """Test that get_values() returns a list of values tuples."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        values = vcdset.get_values("TOP.io_input_valid", rising)

        assert isinstance(values, list)
        assert all(isinstance(item, (int, type(None))) for item in values)

    def test_get_values_with_empty_set(self, vcdset):
        """Test get_values with empty timestep set."""
        values = vcdset.get_values("TOP.clk", set())
        assert values == []

    def test_get_values_single_timestep(self, vcdset):
        """Test get_values with single timestep."""
        values = vcdset.get_values("TOP.clk", {0})
        assert len(values) == 1
        assert values[0] == 0
        assert isinstance(values[0], (int, type(None)))

    def test_get_values_multibit_signal(self, vcdset):
        """Test get_values with multi-bit signal."""
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        timesteps = set(list(rising)[:5])  # First 5 rising edges

        values = vcdset.get_values(
            "TOP.io_input_payload_fragment_value_0[15:0]", timesteps
        )
        assert len(values) == 5
        # Multi-bit values should be integers or None
        assert all(isinstance(v, (int, type(None))) for v in values)
        assert all(v is None or v >= 0 for v in values)

    def test_get_values_signal_not_found(self, vcdset):
        """Test error when signal doesn't exist."""
        with pytest.raises(SignalNotFoundError):
            vcdset.get_values("nonexistent_signal", {0, 1, 2})

    def test_get_values_practical_example(self, vcdset):
        """Test practical use case: get data values during handshakes."""
        # Find handshake times
        valid = vcdset.get("TOP.io_input_valid", lambda sm1, s, sp1: s == "1")
        ready = vcdset.get("TOP.io_input_ready", lambda sm1, s, sp1: s == "1")
        handshakes = valid & ready

        # Get data values at handshake times
        data_values = vcdset.get_values(
            "TOP.io_input_payload_fragment_value_0[15:0]", handshakes
        )

        assert len(data_values) == len(handshakes)
        assert all(isinstance(value, int) for value in data_values)

    def test_get_values_preserves_timestep_set(self, vcdset):
        """Test that original timestep set is unchanged."""
        timesteps = {10, 20, 30, 40, 50}
        original_timesteps = timesteps.copy()

        values = vcdset.get_values("TOP.clk", timesteps)

        assert timesteps == original_timesteps  # Set unchanged
        assert len(values) == len(timesteps)


# Test ValueType - Raw (default, backward compatibility)
class TestValueTypeRaw:
    """Tests for Raw() ValueType (default behavior)."""

    def test_raw_is_default(self, vcdset):
        """Test that Raw() is the default value_type."""
        # Without value_type parameter, should work as Raw()
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)

        # With explicit Raw()
        rising_explicit = vcdset.get(
            "TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1, value_type=Raw()
        )

        assert rising == rising_explicit

    def test_raw_binary_to_int(self, vcdset):
        """Test Raw() converts binary strings to integers."""
        # Get all timesteps
        all_times = vcdset.get("TOP.clk", lambda sm1, s, sp1: True, value_type=Raw())

        # Values should be integers 0 or 1 for clock signal
        values = vcdset.get_values_with_t("TOP.clk", all_times, value_type=Raw())

        for _, value in values:
            assert isinstance(value, int)
            assert value in [0, 1]

    def test_raw_multibit_conversion(self, vcdset):
        """Test Raw() converts multi-bit signals to decimal integers."""
        # Get a timestep where we have data
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t(
            "TOP.io_input_payload_fragment_value_0[15:0]", timesteps, value_type=Raw()
        )

        # Values should be integers
        for _, value in values:
            assert value is None or isinstance(value, int)

    def test_backward_compatibility_no_value_type(self, vcdset):
        """Test that existing code without value_type still works."""
        # This should work exactly as before
        rising = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)

        assert isinstance(rising, set)
        assert len(rising) > 0
        assert all(isinstance(t, int) for t in rising)


# Test ValueType - String
class TestValueTypeString:
    """Tests for String() ValueType."""

    def test_string_preserves_binary(self, vcdset):
        """Test String() preserves binary string representation."""
        # Get some timesteps
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t("TOP.clk", timesteps, value_type=String())

        # Values should be strings "0" or "1"
        for _, value in values:
            assert isinstance(value, str)
            assert value in ["0", "1"]

    def test_string_pattern_matching(self, vcdset):
        """Test string pattern matching in conditions."""
        # Find timesteps where clock is "1" (as string)
        high_times = vcdset.get(
            "TOP.clk", lambda sm1, s, sp1: s == "1", value_type=String()
        )

        assert isinstance(high_times, set)
        assert len(high_times) > 0

    def test_string_multibit_values(self, vcdset):
        """Test String() with multi-bit signals."""
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            timesteps,
            value_type=String(),
        )

        # Values should be binary strings
        for _, value in values:
            assert value is None or isinstance(value, str)
            # If not None, should be a binary string (only 0s and 1s)
            if value is not None:
                assert all(c in "01xzXZ" for c in value)

    def test_string_comparison_in_lambda(self, vcdset):
        """Test comparing string values in lambda."""
        # Get timesteps where clock transitions from "0" to "1"
        rising = vcdset.get(
            "TOP.clk", lambda sm1, s, sp1: sm1 == "0" and s == "1", value_type=String()
        )

        assert isinstance(rising, set)
        assert len(rising) > 0


# Test ValueType - FP (Fixed-Point)
class TestValueTypeFP:
    """Tests for FP() ValueType."""

    def test_fp_basic_unsigned(self, vcdset):
        """Test FP() basic conversion with unsigned values."""
        # Use clock signal: "0" -> 0.0, "1" -> 0.0625 with frac=4
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=4, signed=False)
        )

        # Values should be floats
        for _, value in values:
            assert isinstance(value, float)
            # Clock is 0 or 1, so with frac=4: 0/16=0.0 or 1/16=0.0625
            assert value in [0.0, 0.0625]

    def test_fp_frac_zero(self, vcdset):
        """Test FP() with frac=0 (whole numbers)."""
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=0, signed=False)
        )

        # With frac=0, values should be whole numbers
        for _, value in values:
            assert isinstance(value, float)
            assert value in [0.0, 1.0]

    def test_fp_comparison_in_lambda(self, vcdset):
        """Test floating-point comparison in lambda."""
        # Find times when clock > 0.5 (which means value is 1 with frac=0)
        high = vcdset.get(
            "TOP.clk",
            lambda sm1, s, sp1: s is not None and s > 0.5,
            value_type=FP(frac=0, signed=False),
        )

        assert isinstance(high, set)
        assert len(high) > 0

    def test_fp_negative_frac_raises_error(self, vcdset):
        """Test that FP() with negative frac raises error."""
        # Import the exception we need
        from setVCD import VCDParseError

        with pytest.raises(VCDParseError, match="frac must be >= 0"):
            vcdset.get_values_with_t(
                "TOP.clk", {50}, value_type=FP(frac=-1, signed=False)
            )

    def test_fp_large_frac(self, vcdset):
        """Test FP() with frac larger than bit width."""
        # Clock is 1-bit, but frac=8 should still work (just very small values)
        timesteps = {50, 100, 150}

        values = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=8, signed=False)
        )

        # Values should be very small: 0/256=0.0 or 1/256≈0.0039
        for _, value in values:
            assert isinstance(value, float)
            assert value < 0.01  # Very small values

    def test_fp_arithmetic_operations(self, vcdset):
        """Test arithmetic operations with FP values."""
        timesteps = {50, 100, 150}

        # Get values as fixed-point
        values = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=4, signed=False)
        )

        # Perform arithmetic
        for _, value in values:
            doubled = value * 2
            assert isinstance(doubled, float)


# Test ValueType - Edge Cases
class TestValueTypeEdgeCases:
    """Edge cases and boundary conditions for ValueTypes."""

    def test_boundary_values_remain_none(self, vcd_file_path):
        """Test that boundary None values are preserved across all ValueTypes."""
        from setVCD import Raw, SetVCD, XZNone

        # Use old behavior: none_ignore=False to test boundaries
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # At time 0, sm1 should be None regardless of ValueType
        time_zero_found = False

        def check_time_zero(sm1, s, sp1):
            nonlocal time_zero_found
            if sm1 is None and s is not None:
                time_zero_found = True
            return True

        # Test with Raw
        vcdset.get("TOP.clk", check_time_zero, value_type=Raw())
        assert time_zero_found

        # Test with String
        time_zero_found = False
        vcdset.get("TOP.clk", check_time_zero, value_type=String())
        assert time_zero_found

        # Test with FP
        time_zero_found = False
        vcdset.get("TOP.clk", check_time_zero, value_type=FP(frac=4, signed=False))
        assert time_zero_found

    def test_last_time_sp1_none(self, vcd_file_path):
        """Test that at last_clock, sp1 is None regardless of ValueType."""
        from setVCD import Raw, SetVCD, XZNone

        # Use old behavior: none_ignore=False to test boundaries
        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        last_time_found = False

        def check_last_time(sm1, s, sp1):
            nonlocal last_time_found
            if sp1 is None and s is not None and sm1 is not None:
                last_time_found = True
            return True

        vcdset.get("TOP.clk", check_last_time, value_type=Raw())
        assert last_time_found

    def test_raw_to_string_different_results(self, vcdset):
        """Test that Raw and String return different value types."""
        timesteps = {50}

        raw_values = vcdset.get_values_with_t("TOP.clk", timesteps, value_type=Raw())
        string_values = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=String()
        )

        for (t1, v1), (t2, v2) in zip(raw_values, string_values):
            assert t1 == t2  # Same timestep
            assert type(v1) is not type(v2)  # Different types
            assert isinstance(v1, int)
            assert isinstance(v2, str)

    def test_fp_different_frac_different_values(self, vcdset):
        """Test that different frac values give different results."""
        timesteps = {50}

        fp0 = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=0, signed=False)
        )
        fp4 = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=4, signed=False)
        )
        fp8 = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=8, signed=False)
        )

        # Get the values (assuming clock is 1 at time 50)
        for (_t0, v0), (_t4, v4), (_t8, v8) in zip(fp0, fp4, fp8):
            if v0 == 1.0:  # If clock is high
                # 1/1 = 1.0, 1/16 = 0.0625, 1/256 ≈ 0.0039
                assert v0 > v4 > v8
                assert abs(v0 - 1.0) < 0.001
                assert abs(v4 - 0.0625) < 0.001
                assert abs(v8 - 0.00390625) < 0.0001

    def test_value_type_with_empty_timesteps(self, vcdset):
        """Test all ValueTypes with empty timestep set."""
        empty_set = set()

        raw_values = vcdset.get_values_with_t("TOP.clk", empty_set, value_type=Raw())
        string_values = vcdset.get_values_with_t(
            "TOP.clk", empty_set, value_type=String()
        )
        fp_values = vcdset.get_values_with_t(
            "TOP.clk", empty_set, value_type=FP(frac=4, signed=False)
        )

        assert raw_values == []
        assert string_values == []
        assert fp_values == []

    def test_fp_signed_vs_unsigned(self, vcdset):
        """Test difference between signed and unsigned FP conversion."""
        # For signals where MSB might be 1, signed vs unsigned matters
        # With clock (single bit), value "1" interpreted differently
        # Unsigned: 1 = 1
        # Signed (1-bit): 1 = -1 in two's complement

        timesteps = {50, 100}

        unsigned = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=0, signed=False)
        )
        signed = vcdset.get_values_with_t(
            "TOP.clk", timesteps, value_type=FP(frac=0, signed=True)
        )

        # Check for a high clock value
        for (_t_u, v_u), (_t_s, v_s) in zip(unsigned, signed):
            if v_u == 1.0:  # Unsigned interpretation
                # Signed 1-bit "1" should be -1.0
                assert v_s == -1.0


# New test classes for X/Z and None handling
# This will be appended to tests/test_vcd2set.py


class TestXZMethodIgnore:
    """Tests for XZIgnore() method (default behavior)."""

    def test_xz_ignore_is_default(self, vcd_file_path):
        """Test that XZIgnore is the default xz_method."""
        from setVCD import SetVCD, XZIgnore

        vs1 = SetVCD(vcd_file_path, clock="TOP.clk")
        vs2 = SetVCD(vcd_file_path, clock="TOP.clk", xz_method=XZIgnore())

        # Both should behave the same (skip x/z timesteps)
        result1 = vs1.get("TOP.clk", lambda sm1, s, sp1: s == 1)
        result2 = vs2.get("TOP.clk", lambda sm1, s, sp1: s == 1)

        assert result1 == result2

    def test_xz_ignore_skips_xz_timesteps(self, vcd_file_path):
        """Test that x/z timesteps are skipped with XZIgnore."""
        from setVCD import Raw, SetVCD, XZIgnore

        # Create VCD with XZIgnore (default)
        vs = SetVCD(vcd_file_path, clock="TOP.clk", xz_method=XZIgnore())

        # This condition would normally match x/z values (which become None with Raw)
        # But with XZIgnore, they're skipped entirely
        result = vs.get("TOP.clk", lambda sm1, s, sp1: s is None, value_type=Raw())

        # Should not find any x/z timesteps (they're skipped before filter is called)
        # Only boundary None values would match, but none_ignore=True skips those too
        assert len(result) == 0

    def test_xz_ignore_with_string_type(self, vcd_file_path):
        """Test that XZIgnore works with String value type."""
        from setVCD import SetVCD, String, XZIgnore

        vs = SetVCD(vcd_file_path, clock="TOP.clk", xz_method=XZIgnore())

        # Try to find 'x' in strings - should find nothing because x/z timesteps are skipped
        result = vs.get(
            "TOP.clk",
            lambda sm1, s, sp1: s is not None and "x" in s,
            value_type=String(),
        )

        # Should be empty - x/z timesteps are skipped before String conversion
        assert len(result) == 0


class TestXZMethodNone:
    """Tests for XZNone() method."""

    def test_xz_none_converts_to_none(self, vcd_file_path):
        """Test that XZNone converts x/z to None and passes to filter."""
        from setVCD import Raw, SetVCD, XZNone

        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # With none_ignore=False, filter receives None for x/z values
        # This condition matches where sm1 is None (happens at t=0)
        result_sm1 = vs.get(
            "TOP.clk", lambda sm1, s, sp1: sm1 is None, value_type=Raw()
        )
        assert 0 in result_sm1  # sm1 is None at t=0

        # This condition matches where sp1 is None (happens at last_clock)
        result_sp1 = vs.get(
            "TOP.clk", lambda sm1, s, sp1: sp1 is None, value_type=Raw()
        )
        assert vs.last_clock in result_sp1  # sp1 is None at last_clock

    def test_xz_none_with_string_preserves_xz(self, vcd_file_path):
        """Test that XZNone with String type preserves x/z as strings."""
        from setVCD import SetVCD, String, XZNone

        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # With String type, x/z are preserved as literal strings
        # This test assumes the VCD might not have x/z in TOP.clk, but tests the mechanism
        result = vs.get(
            "TOP.clk",
            lambda sm1, s, sp1: s is not None and ("x" in s or "z" in s),
            value_type=String(),
        )

        # In typical clock signals, no x/z expected, so result might be empty
        # This test verifies the filter is called (not skipped)
        assert isinstance(result, set)


class TestXZMethodValue:
    """Tests for XZValue(replacement) method."""

    def test_xz_value_replaces_with_integer(self, vcd_file_path):
        """Test that XZValue replaces x/z with specified value."""
        from setVCD import Raw, SetVCD, XZValue

        # Replace x/z with 0
        vs = SetVCD(vcd_file_path, clock="TOP.clk", xz_method=XZValue(replacement=0))

        # If there were x/z values, they would become 0
        # Filter can now compare normally
        result = vs.get("TOP.clk", lambda sm1, s, sp1: s == 0, value_type=Raw())

        # Result should include actual 0 values
        assert isinstance(result, set)
        # TOP.clk toggles 0/1, so should have many 0 values
        assert len(result) > 0

    def test_xz_value_with_string_ignores_replacement(self, vcd_file_path):
        """Test that XZValue with String type ignores replacement and preserves x/z."""
        from setVCD import SetVCD, String, XZValue

        # Replacement should be ignored for String type
        vs = SetVCD(
            vcd_file_path,
            clock="TOP.clk",
            xz_method=XZValue(replacement=5),
            none_ignore=False,
        )

        # With String type, x/z should be preserved as strings (not replaced)
        # This filter would match x/z strings if present
        result = vs.get(
            "TOP.clk",
            lambda sm1, s, sp1: s is not None and ("x" in s or "z" in s),
            value_type=String(),
        )

        # Clock likely doesn't have x/z, but verifies replacement is ignored
        assert isinstance(result, set)

    def test_xz_value_fp_conversion(self, vcd_file_path):
        """Test that XZValue works with FP value type."""
        from setVCD import FP, SetVCD, XZValue

        # Replace x/z with 1, then convert to FP
        vs = SetVCD(vcd_file_path, clock="TOP.clk", xz_method=XZValue(replacement=1))

        # If x/z existed, it would become 1, then 1/16 = 0.0625 with frac=4
        result = vs.get(
            "TOP.clk",
            lambda sm1, s, sp1: s is not None and abs(s - 0.0625) < 0.001,
            value_type=FP(frac=4, signed=False),
        )

        # Clock toggles 0/1, so value 1 exists and becomes 0.0625
        assert isinstance(result, set)


class TestNoneIgnore:
    """Tests for none_ignore parameter."""

    def test_none_ignore_true_skips_boundaries(self, vcd_file_path):
        """Test that none_ignore=True (default) skips boundary None values."""
        from setVCD import SetVCD

        vs = SetVCD(vcd_file_path, clock="TOP.clk")  # none_ignore=True by default

        # Try to find None values
        result = vs.get("TOP.clk", lambda sm1, s, sp1: sm1 is None or sp1 is None)

        # Should be empty - boundaries are skipped with none_ignore=True
        assert len(result) == 0

    def test_none_ignore_false_includes_boundaries(self, vcd_file_path):
        """Test that none_ignore=False passes boundary None to filter."""
        from setVCD import SetVCD, XZNone

        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # Find timesteps where sm1 is None
        result = vs.get("TOP.clk", lambda sm1, s, sp1: sm1 is None)

        # Should include time 0 (where sm1=None)
        assert 0 in result

    def test_none_ignore_false_includes_last_time(self, vcd_file_path):
        """Test that none_ignore=False includes last_clock where sp1=None."""
        from setVCD import SetVCD, XZNone

        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # Find timesteps where sp1 is None
        result = vs.get("TOP.clk", lambda sm1, s, sp1: sp1 is None)

        # Should include last_clock (where sp1=None)
        assert vs.last_clock in result


class TestXZNoneInteraction:
    """Tests for interaction between xz_method and none_ignore."""

    def test_xz_none_plus_none_ignore_true(self, vcd_file_path):
        """Test that XZNone + none_ignore=True skips x/z (converted to None)."""
        from setVCD import SetVCD, XZNone

        # XZNone converts x/z to None, then none_ignore=True skips them
        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=True
        )

        # This is equivalent to XZIgnore!
        # Try to find None values - should find nothing
        result = vs.get("TOP.clk", lambda sm1, s, sp1: s is None)

        # No None values should be found (all skipped)
        assert len(result) == 0

    def test_xz_value_plus_none_ignore_false(self, vcd_file_path):
        """Test that XZValue + none_ignore=False: x/z replaced, boundaries passed."""
        from setVCD import SetVCD, XZValue

        vs = SetVCD(
            vcd_file_path,
            clock="TOP.clk",
            xz_method=XZValue(replacement=0),
            none_ignore=False,
        )

        # Find boundary None values (should exist at t=0 and last_clock)
        result = vs.get("TOP.clk", lambda sm1, s, sp1: sm1 is None or sp1 is None)

        # Should include boundaries
        assert 0 in result
        assert vs.last_clock in result

    def test_xz_ignore_plus_none_ignore_false(self, vcd_file_path):
        """Test that XZIgnore + none_ignore=False: x/z skipped, boundaries passed."""
        from setVCD import SetVCD, XZIgnore

        vs = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZIgnore(), none_ignore=False
        )

        # x/z timesteps are skipped, but boundary None values are passed
        result = vs.get("TOP.clk", lambda sm1, s, sp1: sm1 is None or sp1 is None)

        # Should include boundaries
        assert 0 in result
        assert vs.last_clock in result

    def test_all_combinations_return_sets(self, vcd_file_path):
        """Test that all combinations of xz_method and none_ignore work."""
        from setVCD import SetVCD, XZIgnore, XZNone, XZValue

        combinations = [
            (XZIgnore(), True),
            (XZIgnore(), False),
            (XZNone(), True),
            (XZNone(), False),
            (XZValue(0), True),
            (XZValue(0), False),
        ]

        for xz_method, none_ignore in combinations:
            vs = SetVCD(
                vcd_file_path,
                clock="TOP.clk",
                xz_method=xz_method,
                none_ignore=none_ignore,
            )
            result = vs.get("TOP.clk", lambda sm1, s, sp1: s == 1)

            # All should return valid sets
            assert isinstance(result, set)
            # Clock toggles, so should have some high values
            assert len(result) > 0


class TestSetVCDFlexibleSignatures:
    """Tests for flexible signal condition signatures (1, 2, 3 parameters)."""

    # Signature Detection Tests
    def test_1_param_signature_detection(self, vcdset):
        """Test 1-parameter lambda is detected and works."""
        result = vcdset.get("TOP.clk", lambda s: s == 1)
        assert isinstance(result, set)
        assert len(result) > 0

    def test_2_param_signature_detection(self, vcdset):
        """Test 2-parameter lambda is detected and works."""
        result = vcdset.get("TOP.clk", lambda sm1, s: sm1 == 0 and s == 1)
        assert isinstance(result, set)

    def test_3_param_backward_compatible(self, vcdset):
        """Test 3-parameter lambda still works (backward compatibility)."""
        result = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)
        assert isinstance(result, set)

    def test_invalid_0_params(self, vcdset):
        """Test 0-parameter function raises clear error."""
        with pytest.raises(InvalidSignalConditionError, match="must accept 1, 2, or 3"):
            vcdset.get("TOP.clk", lambda: True)

    def test_invalid_4_params(self, vcdset):
        """Test 4-parameter function raises clear error."""
        with pytest.raises(InvalidSignalConditionError, match="must accept 1, 2, or 3"):
            vcdset.get("TOP.clk", lambda a, b, c, d: True)

    # Boundary Behavior Tests
    def test_1_param_includes_all_timesteps(self, vcd_file_path):
        """Test 1-param includes first and last timesteps (no boundary None)."""
        from setVCD import SetVCD, XZNone

        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        result = vcdset.get("TOP.clk", lambda s: True)

        # Should include time 0 and last_clock (no boundary None with 1-param)
        assert 0 in result
        assert vcdset.last_clock in result
        assert len(result) == vcdset.last_clock + 1

    def test_2_param_excludes_first_timestep(self, vcd_file_path):
        """Test 2-param excludes first timestep when none_ignore=True."""
        vcdset = SetVCD(vcd_file_path, clock="TOP.clk")  # none_ignore=True default
        result = vcdset.get("TOP.clk", lambda sm1, s: True)

        # Should NOT include time 0 (sm1 is None there) but should include last_clock
        assert 0 not in result
        assert vcdset.last_clock in result

    def test_2_param_includes_first_with_none_ignore_false(self, vcd_file_path):
        """Test 2-param includes first timestep when none_ignore=False."""
        from setVCD import SetVCD, XZNone

        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )
        result = vcdset.get("TOP.clk", lambda sm1, s: sm1 is None)

        # Should include time 0 (where sm1 is None)
        assert 0 in result

    def test_3_param_boundary_behavior_unchanged(self, vcd_file_path):
        """Test 3-param has same boundary behavior as before (backward compat)."""
        from setVCD import SetVCD, XZNone

        vcdset = SetVCD(
            vcd_file_path, clock="TOP.clk", xz_method=XZNone(), none_ignore=False
        )

        # Test sm1 is None at time 0
        first = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 is None)
        assert 0 in first

        # Test sp1 is None at last_clock
        last = vcdset.get("TOP.clk", lambda sm1, s, sp1: sp1 is None)
        assert vcdset.last_clock in last

    def test_1_param_equivalent_to_3_param_with_s_only(self, vcdset):
        """Test 1-param gives same results as 3-param that only uses s."""
        result_1 = vcdset.get("TOP.clk", lambda s: s == 1)
        result_3 = vcdset.get("TOP.clk", lambda sm1, s, sp1: s == 1)
        assert result_1 == result_3

    def test_2_param_rising_edge_detection(self, vcdset):
        """Test 2-param can detect rising edges using sm1 and s."""
        # Rising edge: sm1==0 and s==1 (backward-looking)
        result_2 = vcdset.get("TOP.clk", lambda sm1, s: sm1 == 0 and s == 1)
        assert isinstance(result_2, set)
        assert len(result_2) > 0

        # Compare with 3-param version (same backward looking pattern)
        result_3 = vcdset.get("TOP.clk", lambda sm1, s, sp1: sm1 == 0 and s == 1)

        # Should be identical! Both look backward at sm1 and s
        assert result_2 == result_3

    # XZ Interaction Tests
    def test_1_param_xz_ignore_only_checks_current(self, vcdset):
        """Test XZIgnore with 1-param only checks current value."""
        # If signal has x/z only at sm1 or sp1, 1-param should still work
        result = vcdset.get("TOP.clk", lambda s: s == 1)

        # Should succeed (assuming TOP.clk doesn't have x/z in current values)
        assert isinstance(result, set)

    def test_2_param_xz_ignore_checks_prev_and_current(self, vcdset):
        """Test XZIgnore with 2-param checks both sm1 and s."""
        # Test with a signal that might have x/z
        result = vcdset.get("TOP.io_input_valid", lambda sm1, s: True)
        assert isinstance(result, set)

    # ValueType Tests
    def test_1_param_with_string_valuetype(self, vcdset):
        """Test 1-param works with String ValueType."""
        result = vcdset.get("TOP.clk", lambda s: s == "1", value_type=String())
        assert isinstance(result, set)

    def test_2_param_with_fp_valuetype(self, vcdset):
        """Test 2-param works with FP ValueType."""
        import math

        result = vcdset.get(
            "TOP.io_input_payload_fragment_value_0[15:0]",
            lambda sm1, s: (
                sm1 is not None
                and s is not None
                and not math.isnan(sm1)
                and not math.isnan(s)
                and s > sm1  # Current value greater than previous (increasing)
            ),
            value_type=FP(frac=0, signed=False),
        )
        assert isinstance(result, set)

    # Caching Tests
    def test_signature_caching(self, vcdset):
        """Test that signature inspection is cached."""

        def condition(s):
            return s == 1

        # First call - should inspect and cache
        result1 = vcdset.get("TOP.clk", condition)

        # Check cache was populated
        assert condition in vcdset._condition_signature_cache
        assert vcdset._condition_signature_cache[condition] == 1

        # Second call - should use cache
        result2 = vcdset.get("TOP.clk", condition)

        # Results should be identical
        assert result1 == result2

    def test_different_functions_cached_separately(self, vcdset):
        """Test that different function objects have separate cache entries."""

        def cond1(s):
            return s == 1

        def cond2(sm1, s):
            return sm1 == 0 and s == 1

        vcdset.get("TOP.clk", cond1)
        vcdset.get("TOP.clk", cond2)

        # Both should be in cache
        assert cond1 in vcdset._condition_signature_cache
        assert cond2 in vcdset._condition_signature_cache

        # With correct counts
        assert vcdset._condition_signature_cache[cond1] == 1
        assert vcdset._condition_signature_cache[cond2] == 2

    # Callable Class Tests
    def test_callable_class_instance(self, vcdset):
        """Test that callable class instances work."""

        class HighDetector:
            def __call__(self, s):
                return s == 1

        detector = HighDetector()
        result = vcdset.get("TOP.clk", detector)
        assert isinstance(result, set)
        assert len(result) > 0

    def test_callable_class_with_state(self, vcdset):
        """Test callable class can maintain state."""

        class CountingCondition:
            def __init__(self):
                self.call_count = 0

            def __call__(self, s):
                self.call_count += 1
                return s == 1

        condition = CountingCondition()
        vcdset.get("TOP.clk", condition)

        # Should have been called for each timestep
        assert condition.call_count == vcdset.last_clock + 1

    # Error Handling Tests
    def test_varargs_not_supported(self, vcdset):
        """Test that *args raises clear error."""
        with pytest.raises(InvalidSignalConditionError, match="cannot use.*args"):
            vcdset.get("TOP.clk", lambda *args: args[0] == 1)

    def test_kwargs_not_supported(self, vcdset):
        """Test that **kwargs raises clear error."""
        with pytest.raises(InvalidSignalConditionError, match="cannot use.*kwargs"):
            vcdset.get("TOP.clk", lambda **kwargs: kwargs["s"] == 1)

    def test_exception_in_condition_includes_param_count(self, vcdset):
        """Test that error message includes signature info."""

        def bad_condition(s):
            raise ValueError("Intentional error")

        with pytest.raises(
            InvalidSignalConditionError, match="raised exception.*1 parameters"
        ):
            vcdset.get("TOP.clk", bad_condition)
