"""The picture frame (rpi_lcars#21): after LCARS_SLIDESHOW_IDLE_MINUTES without
a touch by day, the panel shows the pictures inside an animated LCARS frame
until someone touches it. Each slideshow takes the next of the two frames
(ui/widgets/viewer.py) and a picture changes every LCARS_SLIDESHOW_SECONDS.

A touch only wakes the panel back to STATUS (panel.tap swallows it, so nothing
under the finger is pressed), and night, a red condition or running out of
pictures end it too: alerts are never hidden behind a photo. The pictures are
decoded off the drawing thread (panel/slideshow.py's Loader)."""
from datetime import datetime

from screens.base import CODES
from ui import colours
from ui.widgets import viewer
from ui.widgets.background import LcarsBackground
from ui.widgets.panel_widgets import LcarsBlinker, LcarsCascade, LcarsLabel, LcarsPhoto, LcarsRunner
from ui.widgets.screen import LcarsScreen

TITLE = "VISUAL RECORD"
BLINKS = ((colours.ORANGE, colours.PLUM), (colours.BLUE, colours.BLACK, colours.BLUE),
          (colours.GOLD, colours.RED_BROWN))


class LcarsViewerFrame(LcarsBackground):
    def __init__(self, kind, condition):
        self.kind, self.condition = kind, None
        self.image = viewer.frame(kind, condition)
        LcarsBackground.__init__(self, None, (0, 0), None)

    def set(self, condition):
        if condition != self.condition:
            self.condition = condition
            self.image = viewer.frame(self.kind, condition)
            self.dirty = 1


class ScreenSlideshow(LcarsScreen):
    name = "slideshow"

    def __init__(self, panel):
        LcarsScreen.__init__(self)
        self.panel = panel
        self.shown = None      # when the picture on screen arrived (panel clock)
        self.asked = None      # the path being decoded
        self.ready = None      # the next picture's pixels and size, decoded
        self.count = 0

    def setup(self, all_sprites):
        panel = self.panel
        self.sprites = all_sprites
        self.kind = panel.slideshow_frame()
        layout = viewer.LAYOUTS[self.kind]
        condition = panel.alerts()["condition"]
        self.frame = LcarsViewerFrame(self.kind, condition)
        all_sprites.add(self.frame, layer=0)
        left, top, w, h = layout.window
        self.window = (w, h)
        self.photo = self.add(LcarsPhoto((top, left), (w, h)))
        x, y, w, h = layout.cascade
        self.cascade = self.add(LcarsCascade((y, x), (w, h), rows=1, interval=0.5, seed=1982))
        x, y, w, h = layout.runner
        self.runner = self.add(LcarsRunner((y, x), (w, h), interval=0.4))
        self.blinkers = [self.add(LcarsBlinker((y, x), (w, h), BLINKS[i % len(BLINKS)], interval=0.6 + 0.3 * i,
                                               phase=i))
                         for i, (x, y, w, h) in enumerate(layout.blinkers)]
        top, right, colour = layout.title
        self.add(LcarsLabel(colour, (top, right), TITLE, 1.1, "right"))
        top, right, colour = layout.counter
        self.counter = self.add(LcarsLabel(colour, (top, right), "", 0.7, "right"))
        self.clock = self.add(LcarsLabel(colours.BLACK, (4, 20), "", 1.1))
        self.add(LcarsLabel(colours.BLACK, (458, 20), CODES["registry"], 0.7))
        panel.slideshow_started()
        self.ask()

    def add(self, sprite, layer=1):
        self.sprites.add(sprite, layer=layer)
        return sprite

    def ask(self):
        """Start decoding the next picture; False when there are none."""
        path = self.panel.pictures.deal()
        self.asked = path
        if path is not None:
            self.panel.loader.request(path, self.window)
        return path is not None

    def pre_update(self, screenSurface, fpsClock):
        """Before the widgets draw: they draw this frame's time."""
        now = self.panel.clock()
        for widget in (self.cascade, self.runner, self.photo, *self.blinkers):
            widget.tick(now)

    def update(self, screenSurface, fpsClock):
        panel = self.panel
        if panel.slideshow_over():
            return self.end()
        now = panel.clock()
        self.frame.set(panel.alerts()["condition"])
        self.clock.set(f"{datetime.now():%H:%M}")
        done = panel.loader.take()
        if done is not None:
            path, pixels, size = done
            if pixels is None:
                panel.pictures.failed(path)
                panel.metrics.inc("lcars_slideshow_pictures_total", result="failed")
                self.asked = None
            else:
                self.ready = (pixels, size)
        due = self.shown is None or now - self.shown >= panel.cfg.SLIDESHOW_SECONDS
        if due and self.ready:
            pixels, size = self.ready
            self.ready = None
            self.photo.set(pixels, size, now)
            self.shown = now
            self.count += 1
            panel.metrics.inc("lcars_slideshow_pictures_total", result="shown")
            self.counter.set(f"{self.count:03d} OF {panel.pictures.count():03d}")
            self.asked = None
        if self.asked is None and not self.ready:
            if not self.ask() and self.shown is None:
                return self.end()  # nothing at all to show

    def end(self):
        from screens.status import ScreenStatus  # late, as in screens/base.py: the screens import each other
        self.panel.slideshow_ended()
        self.loadScreen(ScreenStatus(self.panel))
