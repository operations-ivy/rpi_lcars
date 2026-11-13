"""The slideshow's side of the pictures (rpi_lcars#21): which one is next, and
decoding it off the drawing thread.

The pictures are the files in LCARS_PICTURES_DIR, outside the repo so a deploy
never touches them: the Presto library's copies (datasources/pictures.py) and
any put there by hand. They're shown in a shuffled order, each once before any
repeats. Decoding a 12 MP photo takes the Pi a second or more, so a Loader
thread does it, with its rotation (EXIF) applied and scaled to fit the frame's
window, and the screen only turns the finished pixels into a surface."""
import logging
import random
import threading
import time
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic", ".heif"}
# Upscaled at most this much: a small picture stays sharp-ish rather than filling the window.
MAX_ENLARGE = 2.0

try:  # iPhone photos copied by hand, if pillow-heif is installed; otherwise skipped
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def pictures(folder):
    """The picture files in folder, sorted; none when it doesn't exist. Names
    starting with a dot (the sync's partial files) are skipped."""
    try:
        return sorted(p for p in Path(folder).iterdir()
                      if p.suffix.lower() in SUFFIXES and not p.name.startswith(".") and p.is_file())
    except OSError:
        return []


def decode(path, box):
    """(RGB bytes, (w, h)): the picture the right way up, fitting box with its
    aspect ratio kept and nothing cropped. Raises on a file it can't read."""
    with Image.open(path) as im:
        im.draft("RGB", box)  # JPEGs decode at a fraction of full size: much faster
        im = ImageOps.exif_transpose(im).convert("RGB")
        scale = min(box[0] / im.width, box[1] / im.height, MAX_ENLARGE)
        size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
        if size != im.size:
            im = im.resize(size, Image.LANCZOS)
        return im.tobytes(), im.size


class Deck:
    """The pictures in a shuffled order, each dealt once before any repeats.
    The folder is read again for each new round, so new pictures join and
    deleted ones go without a restart."""

    def __init__(self, folder, rng=None, clock=time.monotonic, recheck_seconds=60):
        self.folder = Path(folder)
        self.rng = rng or random.Random()
        self.clock, self.recheck_seconds = clock, recheck_seconds
        self._order = []
        self._last = None
        self._count, self._counted = 0, None
        self.bad = set()  # files that wouldn't decode, until they change

    def count(self):
        """How many there are, read at most every recheck_seconds (it's asked
        every frame)."""
        now = self.clock()
        if self._counted is None or now - self._counted >= self.recheck_seconds:
            self._count = len([p for p in pictures(self.folder) if self._key(p) not in self.bad])
            self._counted = now
        return self._count

    def _key(self, path):
        try:
            return (path, path.stat().st_mtime_ns)
        except OSError:
            return (path, None)

    def deal(self):
        """The next picture's path, or None when there are none."""
        for _ in range(2):
            while self._order:
                path = self._order.pop()
                if path.exists() and self._key(path) not in self.bad:
                    self._last = path
                    return path
            found = [p for p in pictures(self.folder) if self._key(p) not in self.bad]
            self._count, self._counted = len(found), self.clock()
            self.rng.shuffle(found)
            # Not the same one twice in a row across rounds.
            if len(found) > 1 and found[-1] == self._last:
                found[0], found[-1] = found[-1], found[0]
            self._order = found
        return None

    def failed(self, path):
        self.bad.add(self._key(path))
        self._counted = None


class Loader(threading.Thread):
    """Decodes one picture at a time, off the drawing thread. request() asks
    for one; take() returns (path, pixels, size) once it's done, or (path,
    None, None) when it couldn't be read."""

    def __init__(self, decode=decode):
        super().__init__(name="pictures-loader", daemon=True)
        self.decode = decode
        self._wanted = None
        self._done = None
        self._cv = threading.Condition()
        self._stopped = False

    @property
    def busy(self):
        with self._cv:
            return self._wanted is not None

    def request(self, path, box):
        with self._cv:
            self._wanted, self._done = (path, box), None
            self._cv.notify()

    def take(self):
        with self._cv:
            done, self._done = self._done, None
            return done

    def run(self):
        while True:
            with self._cv:
                while self._wanted is None and not self._stopped:
                    self._cv.wait()
                if self._stopped:
                    return
                path, box = self._wanted
            try:
                pixels, size = self.decode(path, box)
            except Exception as e:  # noqa: BLE001 - a bad file is skipped, not fatal
                log.warning("slideshow: a picture wouldn't decode (%s)", type(e).__name__)
                pixels = size = None
            with self._cv:
                if self._wanted == (path, box):  # not replaced by a newer request meanwhile
                    self._wanted, self._done = None, (path, pixels, size)

    def stop(self):
        with self._cv:
            self._stopped = True
            self._cv.notify()
