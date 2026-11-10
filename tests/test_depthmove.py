from engine import depthmove as d

W, H, PIC_W = 1080, 1920, 1280          # a Short's frame, and the width of its 2:3 picture once it fills the height


def test_every_camera_path_moves_clearly_and_never_shows_an_edge():
    """10 Nov 2026: the first setting moved 34 px across a whole scene and read as a still picture."""
    for path in d.PATHS:
        (z0, x0, y0), (z1, x1, y1) = d.camera(path, 0.0), d.camera(path, 1.0)
        travel = abs(x1 - x0) + abs(y1 - y0) + abs(z1 - z0) * W / 2
        assert travel >= 120, (path, travel)                          # at least three times the first setting
        for e in (0.0, 0.25, 0.5, 0.75, 1.0):
            z, x, y = d.camera(path, e)
            assert 1.10 <= z <= d.MARGIN + 0.04, (path, z)
            near = 1 + d.PARALLAX * 0.5                               # the nearest parts move furthest
            spare_x = (PIC_W * d.MARGIN - W * d.MARGIN / z) / 2      # picture left outside the frame on each side, in drawn pixels
            spare_y = H * d.MARGIN * (1 - 1 / z) / 2
            assert abs(x) * near <= spare_x and abs(y) * near <= spare_y, (path, e, x, y, spare_x, spare_y)
    assert d.camera("glide", 1.0, -1)[1] == -d.camera("glide", 1.0, 1)[1]
