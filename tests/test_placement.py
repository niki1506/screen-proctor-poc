import cv2
import numpy as np

from screenproctor.placement import phone_shaped_obstructions, positioned_phones
from screenproctor.vision import Object


def scene():
    image = np.full((600, 800, 3), 200, np.uint8)
    return image, [Object("laptop", (100, 100, 700, 550), 0.9)]


def test_upright_obstruction_without_wrist_or_person():
    image, laptops = scene()
    cv2.rectangle(image, (230, 160), (320, 370), (40, 40, 40), -1)
    found = phone_shaped_obstructions(image, laptops)
    assert len(found) == 1
    assert found[0].label == "phone_placement_candidate"
    assert found[0].box[0] <= 230 and found[0].box[2] >= 320


def test_desk_accessory_wide_panel_and_keyboard_are_excluded():
    for box in [
        (20, 300, 180, 330),
        (150, 150, 480, 350),
        (300, 450, 360, 535),
        (80, 140, 120, 320),
    ]:
        image, laptops = scene()
        cv2.rectangle(image, box[:2], box[2:], (40, 40, 40), -1)
        assert not phone_shaped_obstructions(image, laptops)


def test_confirmed_phone_must_overlap_display_and_be_portrait():
    _, laptops = scene()
    upright = Object("phone", (230, 160, 320, 370), 0.8)
    assert positioned_phones([upright], laptops) == [upright]
    assert not positioned_phones([Object("phone", (20, 400, 90, 550), 0.8)], laptops)
    assert not positioned_phones([Object("phone", (230, 160, 400, 220), 0.8)], laptops)
