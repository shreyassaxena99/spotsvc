from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel

_NULL_CELL = {"level": None, "updated_at": None}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NoiseCellInput(BaseModel):
    level: Optional[Literal["quiet", "moderate", "lively"]] = None  # None = N/A


class NoisePeriodInput(BaseModel):
    morning: NoiseCellInput = NoiseCellInput()
    afternoon: NoiseCellInput = NoiseCellInput()
    evening: NoiseCellInput = NoiseCellInput()


class NoiseMatrixInput(BaseModel):
    weekday: NoisePeriodInput = NoisePeriodInput()
    weekend: NoisePeriodInput = NoisePeriodInput()


class NoiseCellOutput(BaseModel):
    level: Optional[Literal["quiet", "moderate", "lively"]]  # None = N/A
    updated_at: Optional[datetime]


class NoisePeriodOutput(BaseModel):
    morning: NoiseCellOutput
    afternoon: NoiseCellOutput
    evening: NoiseCellOutput


class NoiseMatrixOutput(BaseModel):
    weekday: NoisePeriodOutput
    weekend: NoisePeriodOutput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell_to_db(cell: NoiseCellInput) -> dict:
    """Convert one input cell to its JSONB dict. Both keys always present."""
    if cell.level is None:
        return {"level": None, "updated_at": None}
    return {
        "level": cell.level,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _period_to_db(period: NoisePeriodInput) -> dict:
    return {
        "morning": _cell_to_db(period.morning),
        "afternoon": _cell_to_db(period.afternoon),
        "evening": _cell_to_db(period.evening),
    }


def noise_matrix_to_db(matrix: NoiseMatrixInput) -> dict:
    """Convert a NoiseMatrixInput to a JSONB-ready dict for the DB."""
    return {
        "weekday": _period_to_db(matrix.weekday),
        "weekend": _period_to_db(matrix.weekend),
    }


def _cell_from_db(data: dict | None) -> NoiseCellOutput:
    """Parse one cell dict from DB. Returns null cell on missing/malformed data."""
    if not data:
        return NoiseCellOutput(level=None, updated_at=None)
    raw_updated_at = data.get("updated_at")
    parsed_updated_at: Optional[datetime] = None
    if raw_updated_at:
        try:
            parsed_updated_at = datetime.fromisoformat(raw_updated_at)
        except (ValueError, TypeError):
            parsed_updated_at = None
    return NoiseCellOutput(level=data.get("level"), updated_at=parsed_updated_at)


def _period_from_db(data: dict | None) -> NoisePeriodOutput:
    """Parse one period dict from DB. Returns null cells on missing/malformed data."""
    if not data:
        return NoisePeriodOutput(
            morning=NoiseCellOutput(level=None, updated_at=None),
            afternoon=NoiseCellOutput(level=None, updated_at=None),
            evening=NoiseCellOutput(level=None, updated_at=None),
        )
    return NoisePeriodOutput(
        morning=_cell_from_db(data.get("morning")),
        afternoon=_cell_from_db(data.get("afternoon")),
        evening=_cell_from_db(data.get("evening")),
    )


def noise_matrix_from_db(data: dict | None) -> NoiseMatrixOutput | None:
    """Parse raw JSONB from DB into NoiseMatrixOutput.

    Returns None if data is None (SQL NULL — matrix never set).
    Returns a structured NoiseMatrixOutput with null cells for missing/malformed keys.
    """
    if data is None:
        return None
    return NoiseMatrixOutput(
        weekday=_period_from_db(data.get("weekday")),
        weekend=_period_from_db(data.get("weekend")),
    )
