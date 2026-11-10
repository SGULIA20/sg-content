import numpy as np

from engine import cutout


def test_the_prop_in_his_hands_stays_and_the_screen_beside_him_goes():
    person = np.zeros((10, 12), np.uint8); person[:, 5:9] = 255            # his body: columns 5-8
    person[4:6, 2:5] = 255                                                  # his arm reaching left on rows 4-5
    general = np.zeros((10, 12), np.uint8)
    general[4:6, 3:5] = 255                                                 # the photo he holds, inside his width on those rows
    general[1:3, 0:3] = 255                                                 # the floating screen, outside his width on its rows
    a = cutout.combine(person, general)
    assert a[4, 3] == 255 and a[1, 1] == 0 and a[0, 6] == 255


def test_a_notch_cut_into_his_body_by_the_see_through_screen_is_filled():
    person = np.zeros((10, 6), np.uint8); person[:, 2:5] = 255
    person[3:6, 2] = 0                                                      # the screen overlapped his left side on rows 3-5
    general = np.zeros((10, 6), np.uint8); general[3:6, 2] = 60            # the general model saw a faint object there
    a = cutout.combine(person, general)
    assert (a[3:6, 2] == 255).all()
    general[:] = 0                                                          # nothing seen there: a real gap (beside the neck) stays open
    assert (cutout.combine(person, general)[3:6, 2] == 0).all()
