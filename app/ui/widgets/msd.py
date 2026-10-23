"""A master systems display: the Enterprise-D from above, drawn as LCARS
line art (gold outline, deck rings, coloured sections, the warp core), and
callout lines from labels to named parts of it. Drawn once, in code (no
image), at three times the size and scaled down for smooth edges."""
import random

import pygame

from ui import colours
from ui.widgets.sprite import LcarsWidget

# The ship in metres, x across from the centre line, y aft from the bow:
# its beam and length.
BEAM, LENGTH = 468, 662
# Named parts callouts can point at (metres).
PARTS = {
    "bridge": (0, 150),
    "saucer": (-185, 215),
    "lounge": (-70, 305),
    "deflector": (0, 392),
    "core": (0, 520),
    "nacelle": (-112, 600),
}
SCALE = 3  # drawn this many times larger, then smoothed down
DIM_GOLD = (128, 102, 51)


class LcarsShip(LcarsWidget):
    def __init__(self, pos, size):
        w, h = size
        self.k = min(w / BEAM, h / LENGTH)
        self.offset = ((w - BEAM * self.k) / 2, (h - LENGTH * self.k) / 2)
        big = pygame.Surface((w * SCALE, h * SCALE))
        big.fill(colours.BLACK)
        self.draw(big)
        self.image = pygame.transform.smoothscale(big, size).convert()
        LcarsWidget.__init__(self, colours.BLACK, pos, None)

    def at(self, x, y, scale=1):
        """Metres -> pixels on the widget (times scale)."""
        return ((self.offset[0] + (x + BEAM / 2) * self.k) * scale, (self.offset[1] + y * self.k) * scale)

    def part(self, name):
        """A named part's position on the screen."""
        x, y = self.at(*PARTS[name])
        return round(self.rect.left + x), round(self.rect.top + y)

    def draw(self, s):
        at = lambda x, y: self.at(x, y, SCALE)  # noqa: E731
        k = self.k * SCALE
        line = max(2, round(1.4 * SCALE))

        def poly(points, colour, width=0):
            pygame.draw.polygon(s, colour, [at(x, y) for x, y in points], width)

        def ellipse(cx, cy, rx, ry, colour, width=0):
            x0, y0 = at(cx - rx, cy - ry)
            pygame.draw.ellipse(s, colour, (x0, y0, 2 * rx * k, 2 * ry * k), width)

        def capsule(cx, y0, y1, half, colour, width=0):
            x, y = at(cx - half, y0)
            pygame.draw.rect(s, colour, (x, y, 2 * half * k, (y1 - y0) * k), width, border_radius=round(half * k))

        # Nacelles and pylons first: the hulls overlap them.
        for side in (-1, 1):
            poly([(side * 30, 455), (side * 104, 505), (side * 104, 545), (side * 30, 520)], colours.BLACK)
            poly([(side * 30, 455), (side * 104, 505), (side * 104, 545), (side * 30, 520)], colours.GOLD, line)
            capsule(side * 112, 375, 662, 18, colours.BLACK)
            capsule(side * 112, 375, 662, 18, colours.GOLD, line)
            capsule(side * 112, 380, 425, 13, colours.RED_BROWN)            # the Bussard collector
            capsule(side * 112, 440, 645, 6, colours.BLUE)                   # the warp coils
        # The engineering hull and the neck.
        capsule(0, 330, 640, 50, colours.BLACK)
        capsule(0, 330, 640, 50, colours.GOLD, line)
        ellipse(0, 392, 26, 12, colours.ORANGE)                              # the deflector
        pygame.draw.line(s, colours.ORANGE, at(0, 420), at(0, 600), max(2, round(4 * k)))  # the warp core
        for y in range(445, 620, 22):
            pygame.draw.line(s, DIM_GOLD, at(-38, y), at(-12, y), max(1, SCALE))
            pygame.draw.line(s, DIM_GOLD, at(12, y), at(38, y), max(1, SCALE))
        poly([(-44, 300), (44, 300), (36, 360), (-36, 360)], colours.BLACK)
        # The saucer: rings of decks, a phaser strip, sections, the bridge.
        ellipse(0, 175, 234, 175, colours.BLACK)
        ellipse(0, 175, 234, 175, colours.GOLD, line)
        ellipse(0, 175, 218, 162, colours.ORANGE, max(1, SCALE))
        for f in (0.78, 0.56, 0.34):
            ellipse(0, 175, 234 * f, 175 * f, DIM_GOLD, max(1, SCALE))
        r = random.Random(1701)
        for _ in range(26):
            x, y = r.uniform(-160, 160), r.uniform(50, 300)
            if ((x / 190) ** 2 + ((y - 175) / 140) ** 2) < 1 and abs(x) > 20:
                colour = r.choice((colours.PURPLE, colours.BLUE, colours.GREY_BLUE, colours.PEACH))
                x0, y0 = at(x, y)
                pygame.draw.rect(s, colour, (x0, y0, r.choice((14, 20, 26)) * k, 9 * k))
        ellipse(0, 150, 18, 18, colours.GOLD)                                # the bridge
        poly([(-44, 300), (44, 300), (36, 360), (-36, 360)], colours.GOLD, line)
        pygame.draw.line(s, colours.BLACK, at(-40, 330), at(40, 330), line)  # the neck over the hull's top


class LcarsCallouts(LcarsWidget):
    """Thin lines from points (a label's end) to points (a ship's parts):
    level from the start to bend_x, then straight to the end, with a dot."""

    def __init__(self, rect, lines, colour=colours.GREY_BLUE):
        x0, y0, w, h = rect
        self.image = pygame.Surface((w, h)).convert()
        self.image.fill(colours.BLACK)
        self.image.set_colorkey(colours.BLACK)
        for (sx, sy), bend_x, (ex, ey) in lines:
            points = [(sx - x0, sy - y0), (bend_x - x0, sy - y0), (ex - x0, ey - y0)]
            pygame.draw.lines(self.image, colour, False, points, 1)
            pygame.draw.circle(self.image, colour, points[-1], 3)
        LcarsWidget.__init__(self, colour, (y0, x0), None)

    def handleEvent(self, event, clock):
        return False
