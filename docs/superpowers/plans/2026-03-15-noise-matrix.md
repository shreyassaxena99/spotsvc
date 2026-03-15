# Noise Matrix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static `noise_level` string on each spot with a 2×3 time-aware noise matrix (Weekday/Weekend × Morning/Afternoon/Evening), each cell storing a level and a server-stamped timestamp.

**Architecture:** A new shared module `app/db/noise.py` owns the Pydantic models and two pure helper functions (`noise_matrix_to_db` / `noise_matrix_from_db`). All three service modules (admin, spots, suggestions) import these helpers and swap `noise_level` for `noise_matrix` in their read/write paths. The DB stores the matrix as a JSONB column; the old `noise_level VARCHAR(20)` column is dropped after a backfill migration.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, supabase-py v2 (HTTP client), pytest (new dev dependency)

**Spec:** `docs/superpowers/specs/2026-03-15-noise-matrix-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `app/db/noise.py` | Pydantic input/output models + `noise_matrix_to_db` / `noise_matrix_from_db` helpers |
| **Create** | `requirements-dev.txt` | Dev-only dependencies (pytest) |
| **Create** | `tests/__init__.py` | Makes `tests/` a package |
| **Create** | `tests/test_noise.py` | Unit tests for `noise_matrix_to_db` and `noise_matrix_from_db` |
| **Modify** | `app/admin/schemas.py` | Swap `noise_level` → `noise_matrix` in `CreateSpotRequest`, `UpdateSpotRequest`, `SpotResponse` |
| **Modify** | `app/admin/service.py` | Swap `noise_level` → `noise_matrix` in `create_spot`, `update_spot` (+ fix `exclude_unset`), `_build_spot_response` |
| **Modify** | `app/spots/schemas.py` | Swap `noise_level` → `noise_matrix` in `SpotPin`, `SpotDetail` |
| **Modify** | `app/spots/service.py` | Swap `noise_level` → `noise_matrix` in `_build_spot_pin`, `_build_spot_detail` |
| **Modify** | `app/suggestions/schemas.py` | Swap `noise_level` → `noise_matrix` in `UpdateSuggestionStatusRequest` |
| **Modify** | `app/suggestions/router.py` | Pass `payload.noise_matrix` instead of `payload.noise_level` |
| **Modify** | `app/suggestions/service.py` | Pass `noise_matrix` to `CreateSpotRequest` in `update_suggestion_status` |

---

## Chunk 1: Noise helpers + tests

### Task 1: Add pytest dev dependency

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
pytest==8.3.5
```

- [ ] **Step 2: Install it in the venv**

Run: `.venv/bin/pip install pytest==8.3.5`
Expected: `Successfully installed pytest-8.3.5` (or similar)

- [ ] **Step 3: Verify pytest runs**

Run: `.venv/bin/python -m pytest --version`
Expected: `pytest 8.3.5`

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt
git commit -m "chore: add pytest dev dependency"
```

---

### Task 2: Create `app/db/noise.py` with models and helpers

**Files:**
- Create: `app/db/noise.py`
- Create: `tests/__init__.py`
- Create: `tests/test_noise.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/__init__.py` (empty file), then create `tests/test_noise.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

Run: `.venv/bin/python -m pytest tests/test_noise.py -v`
Expected: `ImportError: cannot import name 'NoiseCellInput' from 'app.db.noise'` (or module not found)

- [ ] **Step 3: Create `app/db/noise.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `.venv/bin/python -m pytest tests/test_noise.py -v`
Expected:
```
tests/test_noise.py::TestNoiseMatrixToDb::test_cell_with_level_emits_both_keys PASSED
tests/test_noise.py::TestNoiseMatrixToDb::test_na_cell_emits_explicit_nulls_for_both_keys PASSED
tests/test_noise.py::TestNoiseMatrixToDb::test_all_six_cells_present PASSED
tests/test_noise.py::TestNoiseMatrixToDb::test_mixed_matrix PASSED
tests/test_noise.py::TestNoiseMatrixFromDb::test_none_input_returns_none PASSED
tests/test_noise.py::TestNoiseMatrixFromDb::test_valid_dict_returns_noise_matrix_output PASSED
tests/test_noise.py::TestNoiseMatrixFromDb::test_null_level_cells_returned_as_none PASSED
tests/test_noise.py::TestNoiseMatrixFromDb::test_missing_period_key_returns_null_cells_not_error PASSED
tests/test_noise.py::TestNoiseMatrixFromDb::test_missing_cell_key_returns_null_cell_not_error PASSED

9 passed
```

- [ ] **Step 5: Commit**

```bash
git add app/db/noise.py tests/__init__.py tests/test_noise.py
git commit -m "feat: add noise matrix models and helpers with tests"
```

---

## Chunk 2: Admin schemas + service

### Task 3: Update `app/admin/schemas.py`

**Files:**
- Modify: `app/admin/schemas.py`

- [ ] **Step 1: Replace `noise_level` import and field in `CreateSpotRequest`**

In `app/admin/schemas.py`, make these changes:

1. Add import for noise models after the existing imports:
```python
from app.db.noise import NoiseMatrixInput, NoiseMatrixOutput
```

2. In `CreateSpotRequest`, replace:
```python
noise_level: Optional[Literal["quiet", "moderate", "lively"]] = None
```
with:
```python
noise_matrix: Optional[NoiseMatrixInput] = None
```

3. In `UpdateSpotRequest`, replace:
```python
noise_level: Optional[Literal["quiet", "moderate", "lively"]] = None
```
with:
```python
noise_matrix: Optional[NoiseMatrixInput] = None
```

4. In `SpotResponse`, replace:
```python
noise_level: Optional[str]
```
with:
```python
noise_matrix: Optional[NoiseMatrixOutput]
```

5. Remove `Literal` from the `typing` import if it is no longer used elsewhere in the file. Check: `Literal` is still used in `ValidateResponse`? No — check the full file. After removing `noise_level`, `Literal` is no longer used in this file, so remove it from the import line:
```python
from typing import Any, Optional
```

- [ ] **Step 2: Verify the app imports cleanly**

Run: `.venv/bin/python -c "from app.admin.schemas import CreateSpotRequest, UpdateSpotRequest, SpotResponse; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/admin/schemas.py
git commit -m "feat: swap noise_level for noise_matrix in admin schemas"
```

---

### Task 4: Update `app/admin/service.py`

**Files:**
- Modify: `app/admin/service.py`

- [ ] **Step 1: Add noise helper imports**

At the top of `app/admin/service.py`, add after the existing imports:
```python
from app.db.noise import NoiseMatrixInput, noise_matrix_from_db, noise_matrix_to_db
```

- [ ] **Step 2: Update `_build_spot_response`**

Replace:
```python
noise_level=data.get("noise_level"),
```
with:
```python
noise_matrix=noise_matrix_from_db(data.get("noise_matrix")),
```

- [ ] **Step 3: Update `create_spot` — replace `noise_level` key**

In the `spot_data` dict in `create_spot`, remove:
```python
"noise_level": payload.noise_level,
```

Then, after the `spot_data` dict is defined but **before** the `{k: v ... if v is not None}` filter line, add the conditional guard:
```python
if payload.noise_matrix is not None:
    spot_data["noise_matrix"] = noise_matrix_to_db(payload.noise_matrix)
```

- [ ] **Step 4: Update `update_spot` — fix `exclude_unset` and replace `noise_level`**

Replace:
```python
updates: dict = {k: v for k, v in payload.model_dump().items() if v is not None}
```
with:
```python
updates: dict = payload.model_dump(exclude_unset=True)
```

Then, after that line, add a guard to convert `noise_matrix` from a dict (model_dump output) to a DB dict:
```python
if "noise_matrix" in updates and updates["noise_matrix"] is not None:
    updates["noise_matrix"] = noise_matrix_to_db(NoiseMatrixInput.model_validate(updates["noise_matrix"]))
elif "noise_matrix" in updates:
    # explicit null sent by caller — remove key to avoid overwriting with None
    del updates["noise_matrix"]
```

- [ ] **Step 5: Verify the app imports cleanly**

Run: `.venv/bin/python -c "from app.admin.service import create_spot, update_spot; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add app/admin/service.py
git commit -m "feat: swap noise_level for noise_matrix in admin service"
```

---

## Chunk 3: Spots + Suggestions

### Task 5: Update `app/spots/schemas.py` and `app/spots/service.py`

**Files:**
- Modify: `app/spots/schemas.py`
- Modify: `app/spots/service.py`

- [ ] **Step 1: Update `app/spots/schemas.py`**

1. Add import after existing imports:
```python
from app.db.noise import NoiseMatrixOutput
```

2. In `SpotPin`, replace:
```python
noise_level: Optional[str]
```
with:
```python
noise_matrix: Optional[NoiseMatrixOutput]
```

3. In `SpotDetail`, replace:
```python
noise_level: Optional[str]
```
with:
```python
noise_matrix: Optional[NoiseMatrixOutput]
```

Note: `Optional` is still required in this file (`Any` and `Optional` are used on other fields) — do not change the `typing` import line.

- [ ] **Step 2: Update `app/spots/service.py`**

1. Add import after existing imports:
```python
from app.db.noise import noise_matrix_from_db
```

2. In `_build_spot_pin`, replace:
```python
noise_level=row.get("noise_level"),
```
with:
```python
noise_matrix=noise_matrix_from_db(row.get("noise_matrix")),
```

3. In `_build_spot_detail`, replace:
```python
noise_level=row.get("noise_level"),
```
with:
```python
noise_matrix=noise_matrix_from_db(row.get("noise_matrix")),
```

- [ ] **Step 3: Verify clean imports**

Run: `.venv/bin/python -c "from app.spots.schemas import SpotPin, SpotDetail; from app.spots.service import _build_spot_pin, _build_spot_detail; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/spots/schemas.py app/spots/service.py
git commit -m "feat: swap noise_level for noise_matrix in spots schemas and service"
```

---

### Task 6: Update suggestions schemas, router, and service

**Files:**
- Modify: `app/suggestions/schemas.py`
- Modify: `app/suggestions/router.py`
- Modify: `app/suggestions/service.py`

- [ ] **Step 1: Update `app/suggestions/schemas.py`**

1. Add import after existing imports:
```python
from app.db.noise import NoiseMatrixInput
```

2. In `UpdateSuggestionStatusRequest`, replace:
```python
noise_level: Optional[Literal["quiet", "moderate", "lively"]] = None
```
with:
```python
noise_matrix: Optional[NoiseMatrixInput] = None
```

3. Remove `Literal` from the `typing` import if no longer used. After this change, check the full file — `Literal` is used in the `status` field (`Literal["approved", "rejected"]`), so it must stay.

- [ ] **Step 2: Update `app/suggestions/router.py`**

In the `update_suggestion` endpoint, the call to `update_suggestion_status(...)` passes arguments positionally. Locate the line:
```python
payload.noise_level,
```
and replace it with:
```python
payload.noise_matrix,
```
This is the 6th argument in the call and must stay in the same position — only the value changes, not the call structure.

- [ ] **Step 3: Update `app/suggestions/service.py`**

1. Add import at the top of the file after the existing imports:
```python
from app.db.noise import NoiseMatrixInput
```

2. In the `update_suggestion_status` function signature, replace the parameter in one step:
```python
noise_level: Optional[str] = None,
```
with:
```python
noise_matrix: Optional[NoiseMatrixInput] = None,
```

3. In the `CreateSpotRequest` construction inside `update_suggestion_status`, replace:
```python
noise_level=noise_level,
```
with:
```python
noise_matrix=noise_matrix,
```

   **Important:** After this replacement, confirm there is no remaining `noise_level=` keyword argument in the `CreateSpotRequest(...)` call — `CreateSpotRequest` no longer accepts `noise_level` after Task 3 (Chunk 2). A leftover reference will cause a `TypeError` at runtime.

- [ ] **Step 4: Verify clean imports**

Run: `.venv/bin/python -c "from app.suggestions.schemas import UpdateSuggestionStatusRequest; from app.suggestions.service import update_suggestion_status; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Run full test suite**

**Requires Chunks 1 and 2 to have been applied first** (test infrastructure and `app/db/noise.py` must exist).

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all 9 tests pass, no errors

- [ ] **Step 6: Commit**

```bash
git add app/suggestions/schemas.py app/suggestions/router.py app/suggestions/service.py
git commit -m "feat: swap noise_level for noise_matrix in suggestions flow"
```

---

## Chunk 4: DB migration + frontend prompts

### Task 7: DB migration (manual — run in Supabase SQL Editor)

This task has no code changes. It documents the SQL steps to run in order in the Supabase SQL Editor. **Run these before deploying the updated FastAPI service** — the column add and backfill are additive and safe to apply to the live schema while the old service is still running.

- [ ] **Step 1: Add the `noise_matrix` column**

Run in Supabase SQL Editor:
```sql
ALTER TABLE spots ADD COLUMN noise_matrix JSONB;
```
Expected: command succeeds with no error.

- [ ] **Step 2: Backfill all existing rows**

Run in Supabase SQL Editor:
```sql
UPDATE spots
SET noise_matrix = jsonb_build_object(
  'weekday', jsonb_build_object(
    'morning',   jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END),
    'afternoon', jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END),
    'evening',   jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END)
  ),
  'weekend', jsonb_build_object(
    'morning',   jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END),
    'afternoon', jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END),
    'evening',   jsonb_build_object('level', noise_level, 'updated_at', CASE WHEN noise_level IS NULL THEN NULL ELSE NOW() END)
  )
);
```
Expected: `UPDATE <N>` where N is the number of rows in the `spots` table.

Note: rows where `noise_level` was NULL produce an all-null-level matrix with `updated_at: null` — consistent with how `noise_matrix_to_db` writes N/A cells.

- [ ] **Step 3: Verify the backfill**

Run in Supabase SQL Editor:
```sql
SELECT id, noise_level, noise_matrix FROM spots LIMIT 5;
```
Expected: `noise_matrix` column is populated for all rows. Each row has the correct shape with `weekday` and `weekend` keys.

- [ ] **Step 4: Drop the old column**

Run in Supabase SQL Editor:
```sql
ALTER TABLE spots DROP COLUMN noise_level;
```
Expected: command succeeds with no error.

- [ ] **Step 5: Verify the drop**

Run in Supabase SQL Editor:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'spots' AND column_name IN ('noise_level', 'noise_matrix');
```
Expected: only `noise_matrix` appears in the result — `noise_level` is gone.

---

### Task 8: Frontend Lovable prompts

This task has no code changes. Copy the prompts below and submit them to Lovable for the respective web apps.

- [ ] **Step 1: Submit the admin web app prompt to Lovable**

```
We're replacing the single "Noise Level" dropdown on the add/edit spot form with a 2×3 noise matrix grid. The grid has two rows (Weekday, Weekend) and three columns (Morning 6–11am, Afternoon 11am–4pm, Evening 4pm+). Each cell contains a dropdown with four options: N/A, Quiet, Moderate, Lively. The default value for all cells is N/A.

The API field is changing from `noise_level: string` to `noise_matrix` with this shape:
{
  "weekday": { "morning": { "level": "quiet" }, "afternoon": { "level": null }, "evening": { "level": "moderate" } },
  "weekend": { "morning": { "level": null }, "afternoon": { "level": "lively" }, "evening": { "level": null } }
}
`null` means N/A. `updated_at` per cell comes back in responses but is read-only — do not send it.

Replace the noise level dropdown with this grid in both the Add Spot form and the Edit Spot form. The grid should be visually compact — a simple table layout with the day types as row headers and time periods as column headers. Also update any spot list/detail views in the admin panel that currently display a single noise level string to instead show the full 2×3 grid.
```

- [ ] **Step 2: Submit the public-facing web app prompt to Lovable**

```
We're replacing the static "Noise Level" field on spot cards and detail pages with a contextual label that reflects the current time and day.

The API now returns a `noise_matrix` object instead of `noise_level`:
{
  "weekday": { "morning": { "level": "quiet", "updated_at": "..." }, "afternoon": { "level": "moderate", "updated_at": "..." }, "evening": { "level": null, "updated_at": null } },
  "weekend": { "morning": { "level": null, "updated_at": null }, "afternoon": { "level": "lively", "updated_at": "..." }, "evening": { "level": "lively", "updated_at": "..." } }
}

Client-side logic to determine which cell to show:
- Day type: if today is Saturday or Sunday → `weekend`, otherwise → `weekday`
- Time of day: current local time 6am–10:59am → `morning`, 11am–3:59pm → `afternoon`, all other hours (4pm–5:59am next day) → `evening`
- If the selected cell's `level` is `null`, hide the noise label entirely

Apply this everywhere a noise level is currently shown — spot cards on the map/list and the spot detail page.
```
