"""Convert raw SRAM upset arrivals into reset-aware state/error metrics.

SPENVIS Long-term SEU outputs describe physical upset arrivals. A write,
scrub, or reset does not change that arrival rate, but it limits how long an
upset remains in the stored state. The helpers below keep those two metrics
separate.

The state formulas assume independent Poisson arrivals and that every SBU
toggles a bit. They are not an MBU, stuck-bit, SEL, or ECC decoder model.
"""

from __future__ import annotations

import math


def _nonnegative_finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def _positive_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or int(value) != value or int(value) <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def cumulative_expected_upset_events(
    rate_per_bit_s: float,
    bits: int,
    duration_s: float,
) -> float:
    """Expected physical SBU arrivals, including those later scrubbed away."""

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    bit_count = _positive_integer(bits, "bits")
    duration = _nonnegative_finite(duration_s, "duration_s")
    return rate * bit_count * duration


def bit_wrong_probability_after_reset(
    rate_per_bit_s: float,
    elapsed_s: float,
) -> float:
    """Probability a bit is wrong at time *elapsed_s* after a known write.

    For a Poisson toggle process, the bit is wrong exactly when the number of
    arrivals is odd, giving ``(1-exp(-2*rate*time))/2``.
    """

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    elapsed = _nonnegative_finite(elapsed_s, "elapsed_s")
    return -0.5 * math.expm1(-2.0 * rate * elapsed)


def bit_wrong_probability_from_initial(
    rate_per_bit_s: float,
    elapsed_s: float,
    initial_wrong_probability: float,
) -> float:
    """Wrong-state probability after radiation toggles from a non-ideal write.

    ``initial_wrong_probability`` describes the stored state immediately after
    the write/scrub operation. Radiation then toggles that same state, so this
    is not an independent-union approximation.
    """

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    elapsed = _nonnegative_finite(elapsed_s, "elapsed_s")
    initial = float(initial_wrong_probability)
    if not math.isfinite(initial) or not 0.0 <= initial <= 1.0:
        raise ValueError("initial_wrong_probability must be finite and in [0, 1]")
    return 0.5 + (initial - 0.5) * math.exp(-2.0 * rate * elapsed)


def mean_bit_wrong_probability_uniform_reads(
    rate_per_bit_s: float,
    reset_interval_s: float,
) -> float:
    """Mean wrong-state probability for reads uniform within a reset interval."""

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    interval = _nonnegative_finite(reset_interval_s, "reset_interval_s")
    x = rate * interval
    if x == 0.0:
        return 0.0
    if x < 1.0e-5:
        # Series of 1/2 + expm1(-2x)/(4x), avoiding cancellation.
        return 0.5 * x - x * x / 3.0 + x * x * x / 6.0
    return 0.5 + math.expm1(-2.0 * x) / (4.0 * x)


def mean_bit_wrong_probability_uniform_reads_from_initial(
    rate_per_bit_s: float,
    reset_interval_s: float,
    initial_wrong_probability: float,
) -> float:
    """Mean stored-state error for uniform reads after a non-ideal write."""

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    interval = _nonnegative_finite(reset_interval_s, "reset_interval_s")
    initial = float(initial_wrong_probability)
    if not math.isfinite(initial) or not 0.0 <= initial <= 1.0:
        raise ValueError("initial_wrong_probability must be finite and in [0, 1]")
    x = rate * interval
    if x == 0.0:
        return initial
    decay_average = -math.expm1(-2.0 * x) / (2.0 * x)
    return 0.5 + (initial - 0.5) * decay_average


def conditional_read_error_probability(
    stored_state_wrong_probability: float,
    read_error_given_correct_state: float,
    read_error_given_wrong_state: float,
) -> float:
    """Use total probability over state for a single electrical read decision."""

    values = (
        stored_state_wrong_probability,
        read_error_given_correct_state,
        read_error_given_wrong_state,
    )
    if any(
        not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
        for value in values
    ):
        raise ValueError("all conditional read probabilities must be finite and in [0, 1]")
    state_wrong, error_if_correct, error_if_wrong = map(float, values)
    return (1.0 - state_wrong) * error_if_correct + state_wrong * error_if_wrong


def mean_joint_read_error_probability_uniform_reads(
    rate_per_bit_s: float,
    reset_interval_s: float,
    initial_wrong_probability: float,
    read_error_given_correct_state: float,
    read_error_given_wrong_state: float,
) -> float:
    """Joint write/radiation/read error for uniform reads in one cycle."""

    mean_state_wrong = mean_bit_wrong_probability_uniform_reads_from_initial(
        rate_per_bit_s,
        reset_interval_s,
        initial_wrong_probability,
    )
    return conditional_read_error_probability(
        mean_state_wrong,
        read_error_given_correct_state,
        read_error_given_wrong_state,
    )


def mean_joint_secded_uncorrectable_probability_uniform_reads(
    rate_per_bit_s: float,
    reset_interval_s: float,
    codeword_bits: int,
    initial_wrong_probability: float,
    read_error_given_correct_state: float,
    read_error_given_wrong_state: float,
    *,
    integration_steps: int = 512,
) -> float:
    """Independent-bit SECDED baseline for the joint state/read model."""

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    interval = _nonnegative_finite(reset_interval_s, "reset_interval_s")
    n = _positive_integer(codeword_bits, "codeword_bits")
    steps = int(integration_steps)
    if steps < 2 or steps % 2:
        raise ValueError("integration_steps must be an even integer >= 2")
    if interval == 0.0:
        p = conditional_read_error_probability(
            initial_wrong_probability,
            read_error_given_correct_state,
            read_error_given_wrong_state,
        )
        return secded_uncorrectable_probability_independent(n, p)
    spacing = interval / steps
    weighted = 0.0
    for index in range(steps + 1):
        elapsed = index * spacing
        p_state = bit_wrong_probability_from_initial(
            rate, elapsed, initial_wrong_probability
        )
        p_read = conditional_read_error_probability(
            p_state,
            read_error_given_correct_state,
            read_error_given_wrong_state,
        )
        value = secded_uncorrectable_probability_independent(n, p_read)
        weight = 1.0 if index in (0, steps) else (4.0 if index % 2 else 2.0)
        weighted += weight * value
    return weighted / (3.0 * steps)


def expected_wrong_bits_after_reset(
    rate_per_bit_s: float,
    bits: int,
    elapsed_s: float,
) -> float:
    """Expected number of bits currently wrong after the last known write."""

    return _positive_integer(bits, "bits") * bit_wrong_probability_after_reset(
        rate_per_bit_s, elapsed_s
    )


def secded_uncorrectable_probability_independent(
    codeword_bits: int,
    bit_wrong_probability: float,
) -> float:
    """Probability of >=2 wrong bits in one SECDED word.

    This binomial result is only the independent-bit baseline. Correlated
    multiple-bit upsets require an empirical MBU multiplicity/layout model.
    """

    n = _positive_integer(codeword_bits, "codeword_bits")
    p = float(bit_wrong_probability)
    if not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise ValueError("bit_wrong_probability must be finite and in [0, 1]")
    if n < 2 or p == 0.0:
        return 0.0
    if p == 1.0:
        return 1.0
    # Direct subtraction loses every significant digit for the orbital-rate
    # probabilities used by this project.  Sum the binomial tail from k=2
    # when p is small; use the compact complement when cancellation is safe.
    if p < 1.0e-3:
        term = n * (n - 1) * 0.5 * p * p * (1.0 - p) ** (n - 2)
        total = term
        for k in range(2, n):
            term *= (n - k) / (k + 1) * p / (1.0 - p)
            total += term
        return min(1.0, total)
    return 1.0 - (1.0 - p) ** n - n * p * (1.0 - p) ** (n - 1)


def mean_secded_uncorrectable_probability_uniform_reads(
    rate_per_bit_s: float,
    reset_interval_s: float,
    codeword_bits: int,
    *,
    integration_steps: int = 512,
) -> float:
    """Mean SECDED DUE probability for reads uniform between resets.

    This is the independent-SBU baseline.  The time average is performed on
    the codeword failure probability itself; applying SECDED to the mean bit
    probability is not mathematically equivalent.
    """

    rate = _nonnegative_finite(rate_per_bit_s, "rate_per_bit_s")
    interval = _nonnegative_finite(reset_interval_s, "reset_interval_s")
    n = _positive_integer(codeword_bits, "codeword_bits")
    if rate == 0.0 or interval == 0.0 or n < 2:
        return 0.0
    steps = int(integration_steps)
    if steps < 2 or steps % 2:
        raise ValueError("integration_steps must be an even integer >= 2")
    spacing = interval / steps
    weighted = 0.0
    for index in range(steps + 1):
        elapsed = index * spacing
        p_bit = bit_wrong_probability_after_reset(rate, elapsed)
        value = secded_uncorrectable_probability_independent(n, p_bit)
        weight = 1.0 if index in (0, steps) else (4.0 if index % 2 else 2.0)
        weighted += weight * value
    return weighted / (3.0 * steps)


def mean_persistent_event_probability_uniform_reads(
    event_rate_per_codeword_s: float,
    reset_interval_s: float,
) -> float:
    """Mean probability of >=1 persistent event before a uniform-time read."""

    rate = _nonnegative_finite(event_rate_per_codeword_s, "event_rate_per_codeword_s")
    interval = _nonnegative_finite(reset_interval_s, "reset_interval_s")
    x = rate * interval
    if x == 0.0:
        return 0.0
    if x < 1.0e-5:
        return 0.5 * x - x * x / 6.0 + x * x * x / 24.0
    return 1.0 + math.expm1(-x) / x


def union_probability(first: float, second: float) -> float:
    """Union of two explicitly independent failure channels."""

    a = float(first)
    b = float(second)
    if not math.isfinite(a) or not 0.0 <= a <= 1.0:
        raise ValueError("first probability must be finite and in [0, 1]")
    if not math.isfinite(b) or not 0.0 <= b <= 1.0:
        raise ValueError("second probability must be finite and in [0, 1]")
    return a + b - a * b
