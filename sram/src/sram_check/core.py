from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


SECONDS_PER_DAY = 86400.0


def trapezoid(y: Sequence[float], x: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("x and y must have the same length >= 2")
    return sum(
        0.5 * (float(y[i]) + float(y[i + 1])) * (float(x[i + 1]) - float(x[i]))
        for i in range(len(x) - 1)
    )


def _strictly_increasing(values: Sequence[float], name: str) -> None:
    if len(values) < 2:
        raise ValueError(f"{name} must contain at least two points")
    if any(not math.isfinite(float(v)) for v in values):
        raise ValueError(f"{name} contains non-finite values")
    if any(float(b) <= float(a) for a, b in zip(values, values[1:])):
        raise ValueError(f"{name} must be strictly increasing")


@dataclass(frozen=True)
class DifferentialSpectrum:
    x: tuple[float, ...]
    differential_flux: tuple[float, ...]
    variable: str
    x_unit: str
    flux_unit: str
    source: str
    normalization: str
    integral_flux_reference: float | None = None

    def __post_init__(self) -> None:
        _strictly_increasing(self.x, "spectrum x")
        if len(self.x) != len(self.differential_flux):
            raise ValueError("spectrum x and differential_flux lengths differ")
        if any((not math.isfinite(v)) or v < 0.0 for v in self.differential_flux):
            raise ValueError("differential flux must be finite and non-negative")

    @property
    def integrated_flux(self) -> float:
        return trapezoid(self.differential_flux, self.x)


@dataclass(frozen=True)
class CrossSectionModel:
    kind: str
    variable: str
    normalization: str
    source: str
    x: tuple[float, ...] = ()
    sigma: tuple[float, ...] = ()
    sigma_low: tuple[float, ...] | None = None
    sigma_high: tuple[float, ...] | None = None
    below_range: str = "zero"
    above_range: str = "hold"
    sigma_sat: float | None = None
    threshold: float | None = None
    width: float | None = None
    shape: float | None = None

    def __post_init__(self) -> None:
        if self.normalization not in {"per_bit", "per_device"}:
            raise ValueError("cross-section normalization must be per_bit or per_device")
        if self.kind == "table":
            _strictly_increasing(self.x, "cross-section x")
            if len(self.x) != len(self.sigma):
                raise ValueError("cross-section x and sigma lengths differ")
            if any((not math.isfinite(v)) or v < 0.0 for v in self.sigma):
                raise ValueError("cross sections must be finite and non-negative")
            for optional in (self.sigma_low, self.sigma_high):
                if optional is not None and len(optional) != len(self.x):
                    raise ValueError("cross-section uncertainty column length differs")
        elif self.kind == "weibull":
            values = (self.sigma_sat, self.threshold, self.width, self.shape)
            if any(v is None or not math.isfinite(float(v)) for v in values):
                raise ValueError("Weibull requires finite sigma_sat, threshold, width, shape")
            if self.sigma_sat < 0.0 or self.threshold < 0.0 or self.width <= 0.0 or self.shape <= 0.0:
                raise ValueError("invalid Weibull parameter")
        else:
            raise ValueError(f"unsupported cross-section kind: {self.kind}")

    def _interpolate(self, value: float, values: Sequence[float]) -> float:
        if value < self.x[0]:
            return 0.0 if self.below_range == "zero" else float(values[0])
        if value >= self.x[-1]:
            if self.above_range == "hold":
                return float(values[-1])
            if self.above_range == "zero":
                return 0.0
            raise ValueError(f"unsupported above_range policy: {self.above_range}")
        lo = 0
        hi = len(self.x) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.x[mid] <= value:
                lo = mid
            else:
                hi = mid
        fraction = (value - self.x[lo]) / (self.x[hi] - self.x[lo])
        return float(values[lo]) + fraction * (float(values[hi]) - float(values[lo]))

    def evaluate(self, value: float, bound: str = "nominal") -> float:
        if self.kind == "weibull":
            if value <= float(self.threshold):
                return 0.0
            z = (value - float(self.threshold)) / float(self.width)
            return float(self.sigma_sat) * (1.0 - math.exp(-(z ** float(self.shape))))
        values: Sequence[float]
        if bound == "low" and self.sigma_low is not None:
            values = self.sigma_low
        elif bound == "high" and self.sigma_high is not None:
            values = self.sigma_high
        else:
            values = self.sigma
        return self._interpolate(value, values)


@dataclass(frozen=True)
class IntegratedRate:
    rate_per_normalization_s: float
    rate_low_per_normalization_s: float | None
    rate_high_per_normalization_s: float | None
    spectrum_integrated_flux_cm2_s: float


def integrate_spectrum_cross_section(
    spectrum: DifferentialSpectrum,
    response: CrossSectionModel,
) -> IntegratedRate:
    if spectrum.variable != response.variable:
        raise ValueError(
            f"spectrum variable {spectrum.variable!r} does not match response {response.variable!r}"
        )
    nominal = [
        flux * response.evaluate(x, "nominal")
        for x, flux in zip(spectrum.x, spectrum.differential_flux)
    ]
    rate = trapezoid(nominal, spectrum.x)
    low = high = None
    if response.sigma_low is not None:
        low = trapezoid(
            [flux * response.evaluate(x, "low") for x, flux in zip(spectrum.x, spectrum.differential_flux)],
            spectrum.x,
        )
    if response.sigma_high is not None:
        high = trapezoid(
            [flux * response.evaluate(x, "high") for x, flux in zip(spectrum.x, spectrum.differential_flux)],
            spectrum.x,
        )
    return IntegratedRate(rate, low, high, spectrum.integrated_flux)

