"""Printer profile: the measured reality of one printer + material + slicer.

Every clearance in this toolkit is derived from a profile rather than hard-coded,
because the same STL fits on one machine and binds on another. Print the
calibration coupon (`hwkit.calibrate`), measure it, and write the numbers here.

Until the coupon is measured, `DEFAULT` holds conservative FDM/PLA values that
are usually close enough for a first article but should not be trusted for a
press fit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parent.parent / "printer_profile.json"


@dataclass
class PrinterProfile:
    name: str = "generic-fdm-pla"
    process: str = "fdm"  # fdm | sla

    # --- machine ---
    nozzle: float = 0.4
    layer_height: float = 0.2
    build_volume: tuple[float, float, float] = (220.0, 220.0, 250.0)

    # --- measured error, from the calibration coupon ---
    # Holes come out undersized on FDM (inner perimeters overshoot inward).
    # hole_compensation is ADDED to every through/blind hole diameter.
    hole_compensation: float = 0.15
    # Pegs/bosses come out oversized; this is SUBTRACTED from outer features
    # that must enter a mating hole.
    peg_compensation: float = 0.10
    # First layer squish widens the footprint. Chamfer the bottom edge instead
    # of fighting it; this is the width of that chamfer.
    elephant_foot: float = 0.3

    # --- fit clearances (diametral, applied on top of compensation) ---
    fit_press: float = 0.00  # bearing outer race, dowel: needs force
    fit_snug: float = 0.10  # located but removable by hand
    fit_slide: float = 0.25  # shaft in a plain bore, lid in a groove
    fit_free: float = 0.45  # screw shank through a plate, no binding wanted

    # --- structural minimums ---
    min_wall: float = 1.2  # 3 perimeters at 0.4 nozzle
    min_hole_dia: float = 2.0  # smaller holes close up / need drilling
    max_overhang: float = 50.0  # degrees from vertical before support is needed
    max_bridge: float = 25.0  # unsupported span, mm

    notes: str = ""
    calibrated: bool = False

    # ---- derived helpers -------------------------------------------------

    def hole(self, nominal: float, fit: str = "free") -> float:
        """Diameter to model for a hole that must accept `nominal`."""
        return nominal + self.hole_compensation + self._fit(fit)

    def bore(self, nominal: float, fit: str = "press") -> float:
        """Diameter to model for a pocket that receives a bearing/dowel OD."""
        return nominal + self.hole_compensation + self._fit(fit)

    def peg(self, nominal: float, fit: str = "snug") -> float:
        """Diameter to model for a peg that must enter a `nominal` hole."""
        return nominal - self.peg_compensation - self._fit(fit)

    def gap(self, fit: str = "slide") -> float:
        """One-sided gap for a slot/groove/lid (linear, not diametral)."""
        return (self.hole_compensation + self._fit(fit)) / 2

    def _fit(self, fit: str) -> float:
        try:
            return getattr(self, f"fit_{fit}")
        except AttributeError as exc:
            raise ValueError(
                f"unknown fit {fit!r}; use press | snug | slide | free"
            ) from exc

    # ---- io --------------------------------------------------------------

    def save(self, path: Path = PROFILE_PATH) -> Path:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")
        return path


def load(path: Path = PROFILE_PATH) -> PrinterProfile:
    if not path.exists():
        return PrinterProfile()
    data = json.loads(path.read_text())
    data["build_volume"] = tuple(data["build_volume"])
    return PrinterProfile(**data)


DEFAULT = PrinterProfile()
