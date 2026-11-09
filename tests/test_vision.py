from screenproctor.vision import (
    Object,
    Tracks,
    interaction,
    confirmed_phones,
    clear_person,
)
import numpy as np


def person(points):
    return Object("person", (0, 0, 200, 400), 0.9, points)


def test_phone_on_desk_does_not_establish_interaction():
    phone = Object("phone", (250, 300, 280, 350), 0.9)
    result = interaction(phone, person({"left_wrist": (50, 180)}))
    assert not result["contact"] and not result["use"]


def test_missing_hands_are_not_assessable():
    assert not interaction(Object("phone", (0, 0, 20, 20), 0.9), person({}))[
        "assessable"
    ]


def test_phone_hand_proximity_is_separate_from_use():
    result = interaction(
        Object("phone", (70, 270, 100, 320), 0.9), person({"left_wrist": (90, 290)})
    )
    assert result["contact"] and not result["use"]


def test_phone_held_near_head_supports_possible_use():
    result = interaction(
        Object("phone", (65, 30, 90, 80), 0.9),
        person({"left_wrist": (75, 60), "nose": (100, 45)}),
    )
    assert result["contact"] and result["use"]


def test_coupled_motion_supports_possible_use():
    old_phone = Object("phone", (60, 270, 90, 320), 0.9)
    phone = Object("phone", (70, 270, 100, 320), 0.9)
    old_person = person({"left_wrist": (80, 290)})
    result = interaction(
        phone, person({"left_wrist": (90, 290)}), old_phone, old_person
    )
    assert result["moves_with_hand"] and result["use"]


def test_tracks_do_not_match_different_classes():
    tracks = Tracks()
    first = tracks.update([Object("person", (0, 0, 100, 100), 0.9)], 0)[0][0]
    second = tracks.update([Object("phone", (0, 0, 100, 100), 0.9)], 0.25)[0][0]
    assert first != second


def test_tracking_expires():
    tracks = Tracks(timeout=1)
    obj = Object("person", (0, 0, 100, 100), 0.9)
    assert tracks.update([obj], 0)[0][0] != tracks.update([obj], 2)[0][0]


def test_camera_translation_does_not_establish_coupled_hand_motion():
    old_phone = Object("phone", (60, 270, 90, 320), 0.9)
    phone = Object("phone", (80, 270, 110, 320), 0.9)
    old_person = person({"left_wrist": (80, 290)})
    new_person = Object("person", (20, 0, 220, 400), 0.9, {"left_wrist": (100, 290)})
    assert not interaction(phone, new_person, old_phone, old_person)["moves_with_hand"]


def test_crop_only_phone_cannot_generate_phone_evidence():
    accessory = Object("phone", (100, 100, 180, 140), 0.95)
    assert confirmed_phones([(accessory, 1)], tiled=True) == []


def test_full_and_crop_phone_need_spatial_agreement():
    full = Object("phone", (100, 100, 180, 140), 0.8)
    crop = Object("phone", (102, 101, 182, 141), 0.75)
    unrelated = Object("phone", (400, 400, 480, 440), 0.95)
    assert confirmed_phones([(full, 0), (unrelated, 1)], True) == []
    assert confirmed_phones([(full, 0), (crop, 1)], True) == [full]


def test_low_contrast_silhouette_remains_ambiguous():
    image = np.full((300, 300, 3), 180, np.uint8)
    image[40:240, 60:150] = 175
    assert not clear_person(image, Object("person", (50, 30, 160, 250), 0.9))
