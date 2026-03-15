from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.noise import (
    NoiseCellInput,
    NoiseCellOutput,
    NoisePeriodInput,
    NoisePeriodOutput,
    NoiseMatrixInput,
    NoiseMatrixOutput,
    noise_matrix_to_db,
    noise_matrix_from_db,
)


# ---------------------------------------------------------------------------
# noise_matrix_to_db
# ---------------------------------------------------------------------------

class TestNoiseMatrixToDb:
    def test_cell_with_level_emits_both_keys(self):
        matrix = NoiseMatrixInput(
            weekday=NoisePeriodInput(
                morning=NoiseCellInput(level="quiet"),
                afternoon=NoiseCellInput(level=None),
                evening=NoiseCellInput(level=None),
            )
        )
        result = noise_matrix_to_db(matrix)
        cell = result["weekday"]["morning"]
        assert cell["level"] == "quiet"
        assert cell["updated_at"] is not None
        # updated_at should be a valid ISO string close to now
        parsed = datetime.fromisoformat(cell["updated_at"])
        assert parsed.tzinfo is not None

    def test_na_cell_emits_explicit_nulls_for_both_keys(self):
        matrix = NoiseMatrixInput()  # all defaults = None
        result = noise_matrix_to_db(matrix)
        cell = result["weekday"]["morning"]
        assert cell["level"] is None
        assert cell["updated_at"] is None
        assert "level" in cell
        assert "updated_at" in cell  # both keys always present

    def test_all_six_cells_present(self):
        result = noise_matrix_to_db(NoiseMatrixInput())
        for day in ("weekday", "weekend"):
            for period in ("morning", "afternoon", "evening"):
                assert day in result
                assert period in result[day]

    def test_mixed_matrix(self):
        matrix = NoiseMatrixInput(
            weekday=NoisePeriodInput(
                morning=NoiseCellInput(level="quiet"),
                afternoon=NoiseCellInput(level="moderate"),
                evening=NoiseCellInput(level="lively"),
            ),
            weekend=NoisePeriodInput(
                morning=NoiseCellInput(level=None),
                afternoon=NoiseCellInput(level="lively"),
                evening=NoiseCellInput(level=None),
            ),
        )
        result = noise_matrix_to_db(matrix)
        assert result["weekday"]["morning"]["level"] == "quiet"
        assert result["weekday"]["afternoon"]["level"] == "moderate"
        assert result["weekday"]["evening"]["level"] == "lively"
        assert result["weekend"]["morning"]["level"] is None
        assert result["weekend"]["morning"]["updated_at"] is None
        assert result["weekend"]["afternoon"]["level"] == "lively"
        assert result["weekend"]["evening"]["level"] is None


# ---------------------------------------------------------------------------
# noise_matrix_from_db
# ---------------------------------------------------------------------------

class TestNoiseMatrixFromDb:
    def test_none_input_returns_none(self):
        assert noise_matrix_from_db(None) is None

    def test_valid_dict_returns_noise_matrix_output(self):
        data = {
            "weekday": {
                "morning":   {"level": "quiet",    "updated_at": "2026-03-15T10:00:00+00:00"},
                "afternoon": {"level": "moderate", "updated_at": "2026-03-15T10:00:00+00:00"},
                "evening":   {"level": "lively",   "updated_at": "2026-03-15T10:00:00+00:00"},
            },
            "weekend": {
                "morning":   {"level": None, "updated_at": None},
                "afternoon": {"level": "moderate", "updated_at": "2026-03-15T10:00:00+00:00"},
                "evening":   {"level": "lively",   "updated_at": "2026-03-15T10:00:00+00:00"},
            },
        }
        result = noise_matrix_from_db(data)
        assert isinstance(result, NoiseMatrixOutput)
        assert result.weekday.morning.level == "quiet"
        assert result.weekday.afternoon.level == "moderate"
        assert result.weekday.evening.level == "lively"
        assert result.weekend.morning.level is None
        assert result.weekend.morning.updated_at is None

    def test_null_level_cells_returned_as_none(self):
        data = {
            "weekday": {
                "morning":   {"level": None, "updated_at": None},
                "afternoon": {"level": None, "updated_at": None},
                "evening":   {"level": None, "updated_at": None},
            },
            "weekend": {
                "morning":   {"level": None, "updated_at": None},
                "afternoon": {"level": None, "updated_at": None},
                "evening":   {"level": None, "updated_at": None},
            },
        }
        result = noise_matrix_from_db(data)
        assert result is not None  # not None — it's a structured output with null cells
        assert result.weekday.morning.level is None

    def test_missing_period_key_returns_null_cells_not_error(self):
        # Malformed JSONB missing 'weekend' key entirely
        data = {
            "weekday": {
                "morning":   {"level": "quiet", "updated_at": "2026-03-15T10:00:00+00:00"},
                "afternoon": {"level": "quiet", "updated_at": "2026-03-15T10:00:00+00:00"},
                "evening":   {"level": "quiet", "updated_at": "2026-03-15T10:00:00+00:00"},
            }
            # 'weekend' key missing
        }
        result = noise_matrix_from_db(data)
        assert result is not None
        assert result.weekend.morning.level is None
        assert result.weekend.morning.updated_at is None

    def test_missing_cell_key_returns_null_cell_not_error(self):
        # Malformed JSONB missing 'evening' under weekday
        data = {
            "weekday": {
                "morning":   {"level": "quiet", "updated_at": "2026-03-15T10:00:00+00:00"},
                "afternoon": {"level": "quiet", "updated_at": "2026-03-15T10:00:00+00:00"},
                # 'evening' missing
            },
            "weekend": {
                "morning":   {"level": None, "updated_at": None},
                "afternoon": {"level": None, "updated_at": None},
                "evening":   {"level": None, "updated_at": None},
            },
        }
        result = noise_matrix_from_db(data)
        assert result is not None
        assert result.weekday.evening.level is None
