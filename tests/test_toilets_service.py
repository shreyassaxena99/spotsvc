from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


def _row(**overrides) -> dict:
    row = {
        "id": str(uuid.uuid4()),
        "name": "Test toilet",
        "short_address": None,
        "area_name": "Westminster",
        "latitude": 51.5,
        "longitude": -0.1,
        "accessible": True,
        "baby_change": False,
        "men": True,
        "women": True,
        "all_gender": False,
        "is_free": True,
        "description": "Open all day",
        "formatted_address": "London",
        "children": None,
        "urinal_only": False,
        "attended": False,
        "automatic": False,
        "radar_key_required": False,
        "payment_details": None,
        "regular_hours": None,
        "current_hours": None,
        "source_updated_at": "2026-09-28T00:00:00+00:00",
        "source_verified_at": None,
        "created_at": "2026-09-28T00:00:00+00:00",
        "updated_at": "2026-09-28T00:00:00+00:00",
    }
    row.update(overrides)
    return row


class _Query:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def _chain(self, method, *args):
        self.calls.append((method, args))
        return self

    def eq(self, *args):
        return self._chain("eq", *args)

    def gte(self, *args):
        return self._chain("gte", *args)

    def lte(self, *args):
        return self._chain("lte", *args)

    def select(self, *args):
        return self._chain("select", *args)

    def execute(self):
        return SimpleNamespace(data=self.data)


def test_build_toilet_pin_has_public_map_fields():
    from app.toilets.service import _build_toilet_pin

    pin = _build_toilet_pin(_row())
    assert pin.name == "Test toilet"
    assert pin.area_name == "Westminster"
    assert pin.is_free is True


def test_list_toilets_applies_london_and_active_filters(monkeypatch):
    from app.toilets import service

    toilet_row = _row()
    query = _Query([toilet_row])
    table = MagicMock(return_value=query)
    monkeypatch.setattr(service.supabase, "table", table)

    toilets, total = service.list_toilets()

    table.assert_called_once_with("toilets")
    assert (
        "select",
        ("id,name,short_address,area_name,latitude,longitude,accessible,baby_change,men,women,all_gender,is_free",),
    ) in query.calls
    assert ("eq", ("source", "toilet_map")) in query.calls
    assert ("eq", ("is_active", True)) in query.calls
    assert ("gte", ("latitude", service.LONDON_MIN_LATITUDE)) in query.calls
    assert ("lte", ("longitude", service.LONDON_MAX_LONGITUDE)) in query.calls
    assert total == 1
    assert toilets[0].id == uuid.UUID(toilet_row["id"])


def test_get_toilet_returns_404_for_outside_or_missing_toilet(monkeypatch):
    from app.toilets import service

    query = _Query([])
    monkeypatch.setattr(service.supabase, "table", MagicMock(return_value=query))

    with pytest.raises(HTTPException) as error:
        service.get_toilet(uuid.uuid4())
    assert error.value.status_code == 404
