def test_distance_meters_is_zero_for_same_coordinate():
    from app.geo import distance_meters

    assert distance_meters(51.5, -0.1, 51.5, -0.1) == 0
