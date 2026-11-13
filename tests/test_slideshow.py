"""The slideshow (rpi_lcars#21) and its pictures, mirrored from the Presto's
library: the idle timer, night and a red condition taking over, a touch that
only wakes, the pictures' order, decoding, and the mirror's limits."""
import io
import json
import random

import pygame
import pytest
from PIL import Image

from datasources.pictures import PictureSync, shrink
from panel.slideshow import Deck, decode
from test_screens import NOW, PROM, WATCH, Rig, quiet_web
from ui.widgets.panel_widgets import LcarsPhoto
from ui.widgets.viewer import KINDS

IDLE = 15 * 60


def jpeg(size=(400, 300), colour=(200, 40, 40), orientation=None):
    im = Image.new("RGB", size, colour)
    out = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    im.save(out, "JPEG", exif=exif.tobytes())
    return out.getvalue()


class NowLoader:
    """The Loader's interface, decoding at once (no thread in the tests)."""

    def __init__(self):
        self._done = None
        self.asked = []

    def request(self, path, box):
        self.asked.append(path)
        try:
            pixels, size = decode(path, box)
        except Exception:  # noqa: BLE001 - as the Loader does
            pixels = size = None
        self._done = (path, pixels, size)

    def take(self):
        done, self._done = self._done, None
        return done


class Feed:
    def __init__(self, data):
        self.data, self.updated = data, NOW - 5

    def age(self):
        return NOW - self.updated

    def set(self, data):
        self.data, self.updated = data, self.updated + 1


CALM = {"status": "success", "data": {"alerts": []}}
CALM_WATCH = {"feeds": []}


def show(tmp_path, count=3, hour=12, feeds=None):
    folder = tmp_path / "pictures"
    folder.mkdir(exist_ok=True)
    for i in range(count):
        (folder / f"p{i}.jpg").write_bytes(jpeg(colour=(40 * i, 90, 200)))
    rig = Rig(hour=hour, web=quiet_web(), now=lambda: NOW, pictures=Deck(folder, rng=random.Random(1)),
              loader=NowLoader(), feeds=feeds or {"prometheus": Feed(CALM), "overwatch": Feed(CALM_WATCH)})
    return rig, folder


def idle(rig, seconds=IDLE):
    rig.clock.t += seconds
    rig.tick(3)


def test_starts_after_the_idle_minutes_by_day(tmp_path):
    rig, _ = show(tmp_path)
    idle(rig, IDLE - 1)
    assert rig.screen == "status"
    idle(rig, 1)
    assert rig.screen == "slideshow"
    assert rig.metrics.get("lcars_slideshow_active") == 1
    assert rig.metrics.get("lcars_slideshow_pictures_total", result="shown") == 1
    rig.clock.t += LcarsPhoto.REVEAL
    rig.shot("30-slideshow-column")


def test_a_touch_only_wakes_it(tmp_path):
    rig, _ = show(tmp_path)
    idle(rig)
    assert rig.screen == "slideshow"
    rig.tap((737, 463))                     # where STATUS has its UNLOCK key
    assert rig.screen == "status"           # back, and the keypad didn't open
    assert rig.metrics.get("lcars_taps_total", woke="true") == 1
    idle(rig, IDLE - 1)
    assert rig.screen == "status"           # the wait starts again from the touch


def test_not_at_night_and_night_ends_it(tmp_path):
    rig, _ = show(tmp_path, hour=23)
    idle(rig)
    assert rig.screen == "status"
    day, _ = show(tmp_path)
    idle(day)
    assert day.screen == "slideshow"
    day.hour = 22
    day.tick(3)
    assert day.screen == "status"


def test_a_red_condition_keeps_it_off_and_ends_it(tmp_path):
    prometheus, overwatch = Feed(PROM), Feed(WATCH)
    rig, _ = show(tmp_path, feeds={"prometheus": prometheus, "overwatch": overwatch})
    idle(rig)
    assert rig.screen == "status"           # red: alerts aren't hidden behind a photo
    prometheus.set(CALM)
    overwatch.set(CALM_WATCH)
    rig.clock.t += 1
    rig.tick(3)
    assert rig.screen == "slideshow"
    prometheus.set(PROM)
    rig.tick(3)
    assert rig.screen == "status"


def test_no_pictures_no_slideshow(tmp_path):
    rig, _ = show(tmp_path, count=0)
    idle(rig)
    assert rig.screen == "status"


def test_pictures_change_and_the_frames_take_turns(tmp_path):
    rig, _ = show(tmp_path)
    idle(rig)
    first = rig.ui.screen
    assert first.kind == KINDS[0]
    loader = rig.panel.loader
    shown = len(loader.asked)
    rig.clock.t += rig.panel.cfg.SLIDESHOW_SECONDS
    rig.tick(3)
    assert len(loader.asked) > shown
    assert rig.metrics.get("lcars_slideshow_pictures_total", result="shown") == 2
    rig.tap((400, 240))
    idle(rig)
    assert rig.ui.screen.kind == KINDS[1]
    rig.clock.t += LcarsPhoto.REVEAL / 2
    rig.shot("31-slideshow-viewscreen")


def test_an_undecodable_picture_is_skipped(tmp_path):
    rig, folder = show(tmp_path, count=1)
    (folder / "broken.jpg").write_bytes(b"not a picture")
    rig.panel.pictures.rng = random.Random(0)
    idle(rig)
    assert rig.screen == "slideshow"
    rig.clock.t += rig.panel.cfg.SLIDESHOW_SECONDS
    rig.tick(4)
    assert rig.metrics.get("lcars_slideshow_pictures_total", result="failed") == 1
    assert rig.screen == "slideshow"
    assert rig.panel.pictures.count() == 1


def test_only_bad_pictures_end_it(tmp_path):
    rig, folder = show(tmp_path, count=0)
    (folder / "broken.jpg").write_bytes(b"not a picture")
    idle(rig)
    rig.tick(3)
    assert rig.screen == "status"


def test_decode_turns_the_photo_by_its_exif_and_fits_the_window(tmp_path):
    path = tmp_path / "portrait.jpg"
    path.write_bytes(jpeg((400, 300), orientation=6))        # a phone held upright: 90° clockwise
    _, size = decode(path, (676, 390))
    assert size == (292, 390)                                # tall now, fitted to the height
    _, size = decode(tmp_path / "portrait.jpg", (100, 100))
    assert size == (75, 100)


def test_decode_raises_on_a_bad_file(tmp_path):
    path = tmp_path / "x.jpg"
    path.write_bytes(b"nope")
    with pytest.raises(Exception):
        decode(path, (100, 100))


def test_the_deck_deals_each_once_before_repeats(tmp_path):
    for i in range(5):
        (tmp_path / f"{i}.jpg").write_bytes(b"x")
    (tmp_path / ".partial.jpg.tmp").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    deck = Deck(tmp_path, rng=random.Random(3))
    first = [deck.deal().name for _ in range(5)]
    assert sorted(first) == [f"{i}.jpg" for i in range(5)]
    second = [deck.deal().name for _ in range(5)]
    assert sorted(second) == sorted(first) and second[0] != first[-1]
    assert deck.count() == 5


def test_the_photo_scans_in():
    pygame.display.init()
    pygame.display.set_mode((800, 480))
    photo = LcarsPhoto((0, 0), (100, 50))
    photo.set(bytes([255, 0, 0]) * 100 * 50, (100, 50), now=0.0)
    surface = pygame.Surface((100, 50))
    photo.tick(LcarsPhoto.REVEAL / 2)
    photo.update(surface)
    assert surface.get_at((50, 5))[:3] == (255, 0, 0) and surface.get_at((50, 45))[:3] == (0, 0, 0)
    photo.tick(LcarsPhoto.REVEAL)
    photo.update(surface)
    assert surface.get_at((50, 45))[:3] == (255, 0, 0)


# The mirror.

class Library:
    """The Presto's upload page: manifest.json and the masters."""

    def __init__(self, photos):
        self.photos = photos  # {id: (added, bytes)}
        self.fetched = []

    def __call__(self, req, timeout):
        url = req.full_url
        if url.endswith("/manifest.json"):
            body = json.dumps({"version": 1, "photos": [
                {"id": pid, "added": added} for pid, (added, _) in self.photos.items()]}).encode()
        else:
            pid = url.split("id=")[1]
            self.fetched.append(pid)
            body = self.photos[pid][1]
        return io.BytesIO(body)


def ids(n):
    return [f"{i:016x}" for i in range(1, n + 1)]


def library(n, size=(1600, 1200)):
    return Library({pid: (1000 + i, jpeg(size)) for i, pid in enumerate(ids(n))})


def sync(tmp_path, lib, **kw):
    return PictureSync("http://presto", tmp_path, opener=lib, disk_free=kw.pop("disk_free", lambda _: 10 << 30), **kw)


def names(folder):
    return sorted(p.name for p in folder.iterdir())


def test_mirror_keeps_panel_sized_copies(tmp_path):
    lib = library(3)
    assert sync(tmp_path, lib).poll() == "ok"
    assert names(tmp_path) == [f"{pid}.jpg" for pid in ids(3)]
    with Image.open(tmp_path / f"{ids(1)[0]}.jpg") as im:
        assert im.size == (640, 480)                         # fits 800x480, aspect kept
    assert sync(tmp_path, lib).poll() == "ok" and len(lib.fetched) == 3   # nothing fetched twice


def test_mirror_drops_what_the_library_drops_and_keeps_hand_added(tmp_path):
    lib = library(3)
    s = sync(tmp_path, lib)
    s.poll()
    (tmp_path / "beach.jpg").write_bytes(jpeg())
    del lib.photos[ids(3)[1]]                                  # hidden or deleted on the upload page
    s.poll()
    assert names(tmp_path) == [f"{ids(3)[0]}.jpg", f"{ids(3)[2]}.jpg", "beach.jpg"]


def test_mirror_keeps_the_newest_max(tmp_path):
    lib = library(5)
    sync(tmp_path, lib, max_count=2).poll()
    assert names(tmp_path) == [f"{pid}.jpg" for pid in ids(5)[3:]]


def test_mirror_stops_at_max_bytes_dropping_the_oldest(tmp_path):
    lib = library(4)
    one = len(shrink(lib.photos[ids(1)[0]][1]))
    s = sync(tmp_path, lib, max_bytes=one * 2 + one // 2)
    assert s.poll() == "full"
    assert names(tmp_path) == [f"{pid}.jpg" for pid in ids(4)[2:]]
    fetched = len(lib.fetched)
    assert s.poll() == "full" and len(lib.fetched) == fetched   # the one that didn't fit isn't fetched again


def test_mirror_fetches_nothing_on_a_nearly_full_disk(tmp_path):
    lib = library(2)
    s = sync(tmp_path, lib, min_free_bytes=2 << 30, disk_free=lambda _: 1 << 30)
    assert s.poll() == "disk_low"
    assert names(tmp_path) == [] and lib.fetched == []


def test_mirror_ignores_bad_ids_and_survives_the_library_being_down(tmp_path):
    lib = library(1)
    lib.photos["../../etc/passwd"] = (1, b"x")
    s = sync(tmp_path, lib)
    assert s.poll() == "ok"
    assert names(tmp_path) == [f"{ids(1)[0]}.jpg"]

    def down(req, timeout):
        raise OSError("no route")
    s.opener = down
    assert s.poll() == "error"
    assert names(tmp_path) == [f"{ids(1)[0]}.jpg"]                # keeps what it has
