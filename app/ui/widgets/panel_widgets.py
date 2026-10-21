"""Widgets for the Home Assistant panel. Labels are centred (the stock
LcarsButton puts them bottom right), and arrows and code dots are drawn: the
LCARS font has no ▲, ▼ or ●."""
import io

import pygame
from pygame.font import Font
from pygame.locals import MOUSEBUTTONDOWN, MOUSEBUTTONUP

from ui import colours
from ui.utils.sound import Sound
from ui.widgets.sprite import LcarsWidget

FONT = "assets/swiss911.ttf"
_fonts = {}
_beep = []


def font(size=1.0):
    px = int(19.0 * size)
    if px not in _fonts:
        _fonts[px] = Font(FONT, px)
    return _fonts[px]


def beep():
    if not _beep:
        _beep.append(Sound("assets/audio/panel/202.wav"))
    _beep[0].play()


def wrap(text, size, width, lines):
    """text in at most lines lines no wider than width; "…" ends it when cut."""
    f, words, out = font(size), str(text).split(), []
    while words and len(out) < lines:
        line = words.pop(0)
        while words and f.size(f"{line} {words[0]}")[0] <= width:
            line += " " + words.pop(0)
        out.append(line)
    if words and out:
        last = out[-1].split()
        while len(last) > 1 and f.size(" ".join(last) + "…")[0] > width:
            last.pop()
        out[-1] = " ".join(last) + "…"
    return out


class LcarsLabel(LcarsWidget):
    """Text anchored at (top, x): its left edge, centre or right edge sits on x.
    Re-renders only when the text or colour changes."""

    def __init__(self, colour, pos, text="", size=1.0, align="left", max_width=None):
        self.colour, self.text, self.align, self.max_width = colour, None, align, max_width
        self.font = font(size)
        self.anchor = pos
        self.image = self.font.render(" ", True, colour)
        LcarsWidget.__init__(self, colour, pos, None)
        self.set(text)

    def set(self, text, colour=None):
        text = str(text)
        colour = colour or self.colour
        if text == self.text and colour == getattr(self, "_drawn_colour", None):
            return
        self.text, self._drawn_colour = text, colour
        shown = text
        if self.max_width:
            # Too long: drop whole words from the end until it fits.
            words = shown.split()
            while len(words) > 1 and self.font.size(" ".join(words))[0] > self.max_width:
                words.pop()
            shown = " ".join(words)
        self.image = self.font.render(shown or " ", True, colour)
        top, x = self.anchor
        rect = self.image.get_rect(top=top)
        if self.align == "center":
            rect.centerx = x
        elif self.align == "right":
            rect.right = x
        else:
            rect.left = x
        self.rect = rect

    def handleEvent(self, event, clock):
        return False


class _Pressable(LcarsWidget):
    """Lights white while pressed; the handler runs on a release inside it.
    A disabled one doesn't light and doesn't run."""

    def __init__(self, colour, pos, size, handler):
        self.colour = colour
        self.image = pygame.Surface(size).convert()
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.enabled = True
        self.disabled_colour = colours.DISABLED
        self.redraw()

    def draw(self, surface, colour):
        raise NotImplementedError

    def redraw(self, pressed=False):
        colour = colours.WHITE if pressed else (self.colour if self.enabled else self.disabled_colour)
        self.image.fill(colours.BLACK)
        self.draw(self.image, colour)

    def set_colour(self, colour):
        if colour != self.colour:
            self.colour = colour
            self.redraw()

    def set_enabled(self, enabled):
        if enabled != self.enabled:
            self.enabled = enabled
            self.redraw()

    def handleEvent(self, event, clock):
        if not self.visible:
            self.focussed = False
            return False
        if event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.focussed = True
            if self.enabled:
                self.redraw(pressed=True)
                beep()
        elif event.type == MOUSEBUTTONUP and self.focussed:
            self.focussed = False
            self.redraw()
            if self.enabled and self.handler and self.rect.collidepoint(event.pos):
                self.handler(self, event, clock)
                return True
        return False


class LcarsKey(_Pressable):
    """A flat block with its label centred, or bottom right like the stock
    sidebar blocks (align="corner")."""

    def __init__(self, colour, pos, size, text, handler=None, text_size=1.0, align="center"):
        self.text, self.font, self.align = text, font(text_size), align
        _Pressable.__init__(self, colour, pos, size, handler)

    def draw(self, surface, colour):
        surface.fill(colour)
        w, h = surface.get_size()
        text = self.text
        if self.align == "left":
            # A rounded bar with the text from its left end, cut to fit.
            surface.fill(colours.BLACK)
            pygame.draw.rect(surface, colour, (0, 0, w, h), border_radius=h // 2)
            if self.font.size(text)[0] > w - h:
                while len(text) > 1 and self.font.size(text + "...")[0] > w - h:
                    text = text[:-1]
                text = text.rstrip() + "..."
        label = self.font.render(text, True, colours.BLACK)
        if self.align == "corner":
            rect = label.get_rect(bottomright=(w - 8, h - 2))
        elif self.align == "left":
            rect = label.get_rect(midleft=(h // 2, h // 2))
        else:
            rect = label.get_rect(center=(w // 2, h // 2))
        surface.blit(label, rect)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.redraw()


class LcarsBlock(LcarsWidget):
    """A plain rectangle: the gaps cut into the background's sidebar."""

    def __init__(self, colour, pos, size):
        self.image = None
        LcarsWidget.__init__(self, colour, pos, size)

    def handleEvent(self, event, clock):
        return False


class LcarsPicture(LcarsWidget):
    """Image bytes (JPEG or PNG) scaled to fit a box, centred in it; empty
    when there are none or they won't decode."""

    def __init__(self, pos, size):
        self.box = size
        self.image = pygame.Surface(size).convert()
        self.image.fill(colours.BLACK)
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        self.data = None

    def set(self, data):
        if data is self.data:
            return
        self.data = data
        self.image.fill(colours.BLACK)
        if not data:
            return
        try:
            picture = pygame.image.load(io.BytesIO(data))
        except pygame.error:
            return
        w, h = picture.get_size()
        scale = min(self.box[0] / w, self.box[1] / h)
        picture = pygame.transform.smoothscale(picture.convert(), (max(1, int(w * scale)), max(1, int(h * scale))))
        self.image.blit(picture, picture.get_rect(center=(self.box[0] // 2, self.box[1] // 2)))

    def handleEvent(self, event, clock):
        return False


class LcarsArrow(_Pressable):
    """A rounded block with a drawn triangle, pointing up or down."""

    def __init__(self, colour, pos, size, up, handler=None):
        self.up = up
        _Pressable.__init__(self, colour, pos, size, handler)

    def draw(self, surface, colour):
        w, h = surface.get_size()
        pygame.draw.rect(surface, colour, (0, 0, w, h), border_radius=h // 3)
        cx, cy, half = w // 2, h // 2, min(w, h) // 3
        tip, base = (cy - half, cy + half * 2 // 3) if self.up else (cy + half, cy - half * 2 // 3)
        pygame.draw.polygon(surface, colours.BLACK, [(cx, tip), (cx - half, base), (cx + half, base)])


class LcarsDots(LcarsWidget):
    """How many digits are in: a row of drawn dots, one hollow slot per
    digit still allowed."""

    def __init__(self, colour, pos, slots=8, radius=10, gap=12):
        self.colour, self.slots, self.radius, self.gap = colour, slots, radius, gap
        self.image = pygame.Surface((slots * (2 * radius + gap), 2 * radius + 2)).convert()
        LcarsWidget.__init__(self, colour, pos, None)
        self.count = None
        self.set(0)

    def set(self, count, colour=None):
        colour = colour or self.colour
        if (count, colour) == (self.count, getattr(self, "_drawn", None)):
            return
        self.count, self._drawn = count, colour
        self.image.fill(colours.BLACK)
        r = self.radius
        for i in range(self.slots):
            centre = (r + i * (2 * r + self.gap), r + 1)
            pygame.draw.circle(self.image, colour, centre, r, 0 if i < count else 2)

    def handleEvent(self, event, clock):
        return False
