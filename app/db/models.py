from __future__ import annotations

import enum


class SpotCategory(str, enum.Enum):
    cafe = "cafe"
    gym = "gym"
    hotel_lobby = "hotel_lobby"
    coworking = "coworking"
    library = "library"
    restaurant = "restaurant"
    other = "other"


class AccessType(str, enum.Enum):
    free = "free"
    purchase_required = "purchase_required"
    members_only = "members_only"
