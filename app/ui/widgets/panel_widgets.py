"""Widgets for the Home Assistant panel. Labels are centred (the stock
LcarsButton puts them bottom right), and arrows and code dots are drawn: the
LCARS font has no ▲, ▼ or ●. Rounded shapes are drawn large and scaled down:
pygame's own curves are jagged."""
import io
import unicodedata
from functools import lru_cache

import pygame
from pygame.font import Font
from pygame.locals import MOUSEBUTTONDOWN, MOUSEBUTTONUP

from ui import colours
from ui.utils.sound import Sound
from ui.widgets.sprite import LcarsWidget

FONT = "assets/swiss911.ttf"
_fonts = {}
_beep = []


SMOOTH = 3


@lru_cache(maxsize=256)
def rounded(size, colour, left=0, right=0):
    """A block on black, its left and right ends rounded to those radii."""
    w, h = size
    big = pygame.Surface((w * SMOOTH, h * SMOOTH))
    pygame.draw.rect(big, colour, (0, 0, w * SMOOTH, h * SMOOTH),
                     border_top_left_radius=left * SMOOTH, border_bottom_left_radius=left * SMOOTH,
                     border_top_right_radius=right * SMOOTH, border_bottom_right_radius=right * SMOOTH)
    return pygame.transform.smoothscale(big, size)


def font(size=1.0):
    px = int(19.0 * size)
    if px not in _fonts:
        _fonts[px] = Font(FONT, px)
    return _fonts[px]


def beep():
    if not _beep:
        _beep.append(Sound("assets/audio/panel/202.wav"))
    _beep[0].play()


def drawable(text, size=1.0):
    """text the LCARS font can draw: accents folded (É -> E), anything else
    it has no glyph for (emoji, most symbols) dropped, spaces tidied."""
    f = font(size)
    folded = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    kept = "".join(c for c in folded if c == " " or (f.metrics(c) or [None])[0] is not None)
    return " ".join(kept.split())


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


def clip(text, size, width):
    """text cut to width, "…" at the end when it is."""
    f, text = font(size), str(text)
    if f.size(text)[0] <= width:
        return text
    while text and f.size(text.rstrip() + "…")[0] > width:
        text = text[:-1]
    return text.rstrip() + "…"


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


CODE_SIZE, CODE_MIN_HEIGHT = 0.6, 30


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
    sidebar blocks (align="corner"); pill=True rounds both ends. A code, as
    LCARS numbers its blocks, goes in the top left of one tall enough."""

    def __init__(self, colour, pos, size, text, handler=None, text_size=1.0, align="center", pill=False, code=""):
        self.text, self.font, self.align, self.pill, self.code = text, font(text_size), align, pill, code
        _Pressable.__init__(self, colour, pos, size, handler)

    def draw(self, surface, colour):
        w, h = surface.get_size()
        if self.pill or self.align == "left":
            surface.blit(rounded((w, h), colour, h // 2, h // 2), (0, 0))
        else:
            surface.fill(colour)
        text = self.text
        if self.align == "left":
            # A rounded bar with the text from its left end, cut to fit.
            if self.font.size(text)[0] > w - h:
                while len(text) > 1 and self.font.size(text + "...")[0] > w - h:
                    text = text[:-1]
                text = text.rstrip() + "..."
        label = self.font.render(text, True, colours.BLACK)
        if self.align == "corner":
            rect = label.get_rect(bottomright=(w - (h // 2 if self.pill else 8), h - 2))
        elif self.align == "left":
            rect = label.get_rect(midleft=(h // 2, h // 2))
        else:
            rect = label.get_rect(center=(w // 2, h // 2))
        surface.blit(label, rect)
        if self.code and h >= CODE_MIN_HEIGHT:
            surface.blit(font(CODE_SIZE).render(self.code, True, colours.BLACK), (6, 3))

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.redraw()


class LcarsCell(_Pressable):
    """A box of short lines, each (text, colour, size) and cut to fit, with
    an outline round it when it has a colour: a day on the month grid. Only
    pressable with a handler."""

    def __init__(self, pos, size):
        self.lines, self.outline = (), None
        _Pressable.__init__(self, colours.BLACK, pos, size, None)
        self.enabled = False

    def set(self, lines, outline=None, handler=None):
        lines = tuple(lines)
        self.handler = handler
        self.enabled = handler is not None
        if (lines, outline) != (self.lines, self.outline):
            self.lines, self.outline = lines, outline
            self.redraw()

    def draw(self, surface, colour):
        w, h = surface.get_size()
        outline = colours.WHITE if colour == colours.WHITE else self.outline
        if outline:
            pygame.draw.rect(surface, outline, (0, 0, w, h), width=2, border_radius=6)
        y = 2
        for text, c, size in self.lines:
            f = font(size)
            if y + f.get_ascent() > h:
                break
            surface.blit(f.render(clip(text, size, w - 10), True, c), (5, y))
            y += f.get_ascent() + 1


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
        big = rounded((w, h), colour, h // 2, h // 2).copy()
        big = pygame.transform.scale(big, (w * SMOOTH, h * SMOOTH))
        cx, cy, half = w * SMOOTH // 2, h * SMOOTH // 2, min(w, h) * SMOOTH // 3
        tip, base = (cy - half, cy + half * 2 // 3) if self.up else (cy + half, cy - half * 2 // 3)
        pygame.draw.polygon(big, colours.BLACK, [(cx, tip), (cx - half, base), (cx + half, base)])
        surface.blit(pygame.transform.smoothscale(big, (w, h)), (0, 0))


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


class LcarsHeader(LcarsWidget):
    """A section's name set into a bar as tall as its capitals: a rounded cap,
    the name, the bar, a short block in a second colour rounded at the far
    end. How louh/lcars heads a group."""

    GAP, END = 5, 3  # the black gaps, and the end block's length in bar heights

    def __init__(self, colour, pos, width, text="", size=1.0, bar_colour=None, end_colour=colours.PURPLE):
        self.colour, self.bar_colour, self.end_colour, self.width = colour, bar_colour, end_colour, width
        self.font, self.text = font(size), None
        self.image = pygame.Surface((width, self.font.get_height())).convert()
        LcarsWidget.__init__(self, colour, pos, None)
        self.set(text)

    def set(self, text, colour=None):
        colour = colour or self.colour
        if (text, colour) == (self.text, getattr(self, "_drawn", None)):
            return
        self.text, self._drawn = text, colour
        f, w, gap, bar_colour = self.font, self.width, self.GAP, self.bar_colour or colour
        caps = f.render("H", True, colours.WHITE).get_bounding_rect()
        top, bar, r = caps.top, caps.height, caps.height // 2
        self.image.fill(colours.BLACK)
        self.image.blit(rounded((bar, bar), bar_colour, r, 0), (0, top))
        x = bar + gap
        if text:
            label = f.render(text, True, colour)
            self.image.blit(label, (x, 0))
            x += label.get_width() + gap
        end = self.END * bar
        if w - x > end + gap + bar:
            self.image.blit(rounded((w - x - end - gap, bar), bar_colour), (x, top))
            self.image.blit(rounded((end, bar), self.end_colour, 0, r), (w - end, top))
        elif w - x > bar:
            self.image.blit(rounded((w - x, bar), bar_colour, 0, r), (x, top))

    def handleEvent(self, event, clock):
        return False


class LcarsCascade(LcarsWidget):
    """The running block of numbers LCARS fills its spare corners with: a few
    rows of columns of digits, a new row arriving every interval and the top
    one leaving. Decoration only; seeded, so a screenshot is repeatable."""

    COLOURS = (colours.ORANGE, colours.ORANGE, colours.BEIGE, colours.GOLD, colours.WHITE)

    def __init__(self, pos, size, rows=3, text_size=0.7, interval=1.0, seed=1701):
        import random
        self.random = random.Random(seed)
        self.font, self.rows, self.interval = font(text_size), rows, interval
        w, h = size
        digit = self.font.size("0")[0]
        # Columns of 2 to 7 digits, a space apart, as many as fit.
        self.widths, x = [], 0
        while True:
            n = self.random.choice((2, 4, 4, 4, 3, 7))
            if x + n * digit > w:
                break
            self.widths.append(n)
            x += (n + 1) * digit
        self.digit = digit
        self.lines = [self.row() for _ in range(rows)]
        self.image = pygame.Surface(size).convert()
        self.last = None
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        self.redraw()

    def row(self):
        r = self.random
        cells = []
        for n in self.widths:
            shown = r.randint(1, n) if r.random() < 0.3 else n  # some columns short, right-aligned
            cells.append(("".join(str(r.randint(0, 9)) for _ in range(shown)), r.choice(self.COLOURS)))
        return cells

    def redraw(self):
        self.image.fill(colours.BLACK)
        step = self.font.get_ascent() + 2
        for y, cells in enumerate(self.lines):
            x = 0
            for n, (text, colour) in zip(self.widths, cells):
                label = self.font.render(text, True, colour)
                self.image.blit(label, (x + n * self.digit - label.get_width(), y * step))
                x += (n + 1) * self.digit

    def tick(self, now):
        """Move on a row when interval has passed since the last."""
        if self.last is None:
            self.last = now
        elif now - self.last >= self.interval:
            self.last = now
            self.lines = self.lines[1:] + [self.row()]
            self.redraw()

    def handleEvent(self, event, clock):
        return False


class LcarsRunner(LcarsWidget):
    """A row of small blocks with one lit, the light stepping along every
    interval: the idle tick of an LCARS panel. Decoration only."""

    def __init__(self, pos, size, cells=5, gap=3, interval=1.0, colour=colours.ORANGE, dim=colours.PLUM):
        self.cells, self.gap, self.interval, self.colour, self.dim = cells, gap, interval, colour, dim
        self.image = pygame.Surface(size).convert()
        self.at, self.last = 0, None
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        self.redraw()

    def redraw(self):
        w, h = self.image.get_size()
        each = (w - self.gap * (self.cells - 1)) // self.cells
        self.image.fill(colours.BLACK)
        for i in range(self.cells):
            self.image.fill(self.colour if i == self.at else self.dim, (i * (each + self.gap), 0, each, h))

    def tick(self, now):
        if self.last is None:
            self.last = now
        elif now - self.last >= self.interval:
            self.last = now
            self.at = (self.at + 1) % self.cells
            self.redraw()

    def handleEvent(self, event, clock):
        return False


class LcarsGauge(LcarsWidget):
    """A vertical scale in a bracket, like LCARS's: whole degrees from two
    below the low guardrail to two above the high, the guardrails' range
    lit gold, a bar across it at each setpoint (orange heat, blue cool) and
    an oval at the current reading."""

    def __init__(self, pos, size):
        self.image = pygame.Surface(size).convert()
        self.drawn = None
        LcarsWidget.__init__(self, colours.BLACK, pos, None)
        self.set(None, None, None, ())

    def set(self, lo, hi, current, marks):
        """marks: (value, colour) for each setpoint."""
        key = (lo, hi, current, tuple(marks))
        if key == self.drawn:
            return
        self.drawn = key
        s = self.image
        s.fill(colours.BLACK)
        w, h = s.get_size()
        arm, pad = 12, 16
        # The bracket: a bar down the left, arms along the top and bottom.
        pygame.draw.rect(s, colours.PEACH, (0, 0, arm, h), border_top_left_radius=arm, border_bottom_left_radius=arm)
        pygame.draw.rect(s, colours.PEACH, (0, 0, 44, 8), border_top_left_radius=arm, border_top_right_radius=4)
        pygame.draw.rect(s, colours.PEACH, (0, h - 8, 44, 8), border_bottom_left_radius=arm,
                         border_bottom_right_radius=4)
        if lo is None or hi is None:
            return
        vmin, vmax = int(lo) - 2, int(hi) + 2

        def y(v):
            return round(pad + (vmax - v) / (vmax - vmin) * (h - 2 * pad))
        f = font(0.85)
        for v in range(vmin, vmax + 1):
            inside = lo <= v <= hi
            top = y(v + 0.5) if v < vmax else y(v)
            bottom = y(v - 0.5) if v > vmin else y(v)
            pygame.draw.rect(s, colours.GOLD if inside else colours.RED_BROWN, (18, top + 1, 10, bottom - top - 1))
            long = v % 2 == 0
            pygame.draw.line(s, colours.ORANGE, (31, y(v)), (31 + (10 if long else 5), y(v)), 2)
            if long:
                label = f.render(str(v), True, colours.BLUE)
                s.blit(label, label.get_rect(midleft=(46, y(v))))
        for value, colour in marks:
            if value is not None and vmin <= value <= vmax:
                pygame.draw.rect(s, colour, (14, y(value) - 3, 30, 6), border_radius=3)
        if current is not None:
            yc = y(min(max(current, vmin), vmax))
            pygame.draw.ellipse(s, colours.BEIGE, (w - 30, yc - 7, 26, 14))

    def handleEvent(self, event, clock):
        return False
