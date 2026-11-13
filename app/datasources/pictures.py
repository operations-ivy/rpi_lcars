"""The slideshow's pictures, mirrored from the Presto's photo library (presto's
upload page at presto.brick.nozdormu.cloud, LAN only): what the Presto shows,
the panel shows. A background thread reads the library's manifest.json every
poll and, for each photo, its ~1600 px master (already the right way up and in
sRGB, so no HEIC on the Pi), shrunk to the screen and kept as a JPEG in the
pictures folder as <id>.jpg. A photo hidden or deleted on the upload page goes
from the panel at the next poll.

The folder is kept small three ways: only the panel-sized copy is stored (about
150 KB a photo, never the master), at most MAX photos and MAX_BYTES (the newest
kept, the oldest dropped), and nothing is fetched while the disk has less than
MIN_FREE_BYTES free. Files put in the folder by hand aren't the sync's: they're
shown too, and never deleted or counted.

Nothing about the photos is logged or exported beyond counts and sizes."""
import io
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

# A photo's id in the library: the first 16 hex digits of its original's SHA-256.
PHOTO_ID = re.compile(r"[0-9a-f]{16}")
SYNCED = re.compile(r"([0-9a-f]{16})\.jpg")
# The screen: a copy is never bigger than this.
FIT = (800, 480)
QUALITY = 88
# A master is ~1 MB; anything far past that isn't one.
MAX_DOWNLOAD = 32 << 20


def shrink(data, fit=FIT):
    """JPEG bytes of the picture, the right way up, fitting fit (never enlarged)."""
    with Image.open(io.BytesIO(data)) as im:
        im.draft("RGB", (fit[0] * 2, fit[1] * 2))  # a JPEG decodes at a fraction of its size
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail(fit, Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=QUALITY, optimize=True)
        return out.getvalue()


def write_atomic(path, data):
    """Whole or not at all: the slideshow may read the folder at any moment.
    The temporary file's name starts with a dot, which the slideshow skips."""
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class PictureSync(threading.Thread):
    def __init__(self, url, folder, poll_seconds=600, max_count=200, max_bytes=300 << 20,
                 min_free_bytes=2 << 30, metrics=None, opener=urllib.request.urlopen, timeout=30,
                 disk_free=lambda path: shutil.disk_usage(path).free, fit=FIT, now=time.time):
        super().__init__(name="pictures", daemon=True)
        self.url, self.folder = url.rstrip("/"), Path(folder)
        self.poll_seconds, self.max_count, self.max_bytes = poll_seconds, max_count, max_bytes
        self.min_free_bytes, self.metrics, self.opener = min_free_bytes, metrics, opener
        self.timeout, self.disk_free, self.fit, self.now = timeout, disk_free, fit, now
        self._stop = threading.Event()
        # Sizes of copies made but not kept (past MAX_BYTES), so the same photo
        # isn't fetched again every poll only to be dropped.
        self._sizes = {}
        self.updated = None
        self._warned = False
        if metrics:
            for result in ("ok", "error", "disk_low", "full"):
                metrics.inc("lcars_pictures_syncs_total", 0, result=result)

    def get(self, path):
        req = urllib.request.Request(self.url + path)
        with self.opener(req, timeout=self.timeout) as r:
            data = r.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError(f"over {MAX_DOWNLOAD} bytes")
        return data

    def synced(self):
        """{id: path} of the copies this sync made."""
        out = {}
        for path in self.folder.iterdir():
            m = SYNCED.fullmatch(path.name)
            if m and path.is_file():
                out[m.group(1)] = path
        return out

    def wanted(self, manifest):
        """The library's photo ids, newest first, at most max_count."""
        photos = [p for p in manifest.get("photos", [])
                  if isinstance(p, dict) and PHOTO_ID.fullmatch(str(p.get("id", "")))]
        photos.sort(key=lambda p: p.get("added") or 0, reverse=True)
        return [p["id"] for p in photos[:self.max_count]]

    def poll(self):
        """One pass; the result: "ok", "error", "disk_low" (stopped fetching) or
        "full" (MAX_BYTES reached, older photos dropped)."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            for stale in self.folder.glob(".*.tmp"):
                stale.unlink(missing_ok=True)
            wanted = self.wanted(json.loads(self.get("/manifest.json")))
        except Exception as e:  # noqa: BLE001 - the panel keeps what it has, tried again next poll
            return self._done("error", e)
        have = self.synced()
        removed = 0
        for pid in set(have) - set(wanted):
            have.pop(pid).unlink(missing_ok=True)
            self._sizes.pop(pid, None)
            removed += 1
        result, total, fetched = "ok", 0, 0
        for i, pid in enumerate(wanted):
            if pid in have:
                size = have[pid].stat().st_size
            elif pid in self._sizes:
                size = self._sizes[pid]
            elif self.disk_free(self.folder) < self.min_free_bytes:
                result = "disk_low"
                break
            else:
                try:
                    data = shrink(self.get(f"/master?id={urllib.parse.quote(pid)}"), self.fit)
                except Exception as e:  # noqa: BLE001 - this photo next time; the rest now
                    self._warn("picture", e)
                    continue
                size = self._sizes[pid] = len(data)
                if total + size <= self.max_bytes:
                    write_atomic(self.folder / f"{pid}.jpg", data)
                    have[pid] = self.folder / f"{pid}.jpg"
                    fetched += 1
            if total + size > self.max_bytes:
                # Full: this one and every older one go.
                for old in wanted[i:]:
                    if old in have:
                        have.pop(old).unlink(missing_ok=True)
                        removed += 1
                result = "full"
                break
            total += size
            if pid in have:
                self._sizes.pop(pid, None)
        if fetched or removed:
            log.info("pictures: %d fetched, %d removed, %d kept (%d KB)", fetched, removed, len(have), total >> 10)
        if self.metrics:
            self.metrics.set("lcars_pictures_synced", len(have))
            self.metrics.set("lcars_pictures_bytes", total)
        return self._done(result)

    def _warn(self, what, e):
        if not self._warned:  # once, not every poll while it's down
            log.warning("pictures: %s: %s", what, e)
            self._warned = True

    def _done(self, result, error=None):
        if error is not None:
            self._warn("library", error)
        else:
            self.updated, self._warned = self.now(), False
        if self.metrics:
            self.metrics.set("lcars_pictures_sync_up", 0 if result == "error" else 1)
            self.metrics.inc("lcars_pictures_syncs_total", result=result)
        return result

    def run(self):
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(self.poll_seconds)

    def stop(self):
        self._stop.set()
