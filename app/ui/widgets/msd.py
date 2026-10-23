"""A master systems display: the Enterprise-D from above, bow up, the way
LCARS draws it: one translucent orange, a bright outline, the saucer gridded
with rings and spokes round its raised centre, a chevron lattice down the
engineering hull, the nacelles wide on swept pylons, a faint blueprint grid
behind; and callout lines from labels to named parts of it. Drawn once, in
code (no image), at three times the size and scaled down for smooth edges."""
import math

import pygame

from ui import colours
from ui.widgets.panel_widgets import font
from ui.widgets.sprite import LcarsWidget

# The ship's beam and length, in units of its own (proportions taken from
# top views: the saucer wider than long, nacelles a quarter of the beam out).
BEAM, LENGTH = 600, 775
# Named parts callouts can point at, top to bottom (ship units).
PARTS = {
    "bow": (0, 30),
    "saucer": (-270, 320),
    "impulse": (-125, 440),
    "pylon": (-95, 540),
    "nacelle": (-153, 730),
}
SCALE = 3  # drawn this many times larger, then smoothed down

LINE = colours.ORANGE           # outlines
FILL = (104, 58, 6)             # the hull: orange, as if translucent on black
GRID = (190, 108, 22)           # deck lines on the hull
DEEP = (62, 34, 4)              # the saucer's raised centre
BRIGHT = colours.GOLD           # the bridge, the Bussard collectors
BLUEPRINT = (24, 28, 44)        # the grid behind


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

    def at(self, x, y):
        """Ship units (x across from the centre line, y aft from the bow) ->
        pixels on the drawing surface."""
        return ((self.offset[0] + (x + BEAM / 2) * self.k) * SCALE, (self.offset[1] + y * self.k) * SCALE)

    def part(self, name):
        """A named part's position on the screen."""
        x, y = self.at(*PARTS[name])
        return round(self.rect.left + x / SCALE), round(self.rect.top + y / SCALE)

    def draw(self, s):
        at, k = self.at, self.k * SCALE
        thick, thin = max(2, round(1.3 * SCALE)), max(1, round(0.6 * SCALE))
        w, h = s.get_size()

        # The blueprint grid behind.
        step = round(18 * SCALE)
        for x in range(0, w, step):
            pygame.draw.line(s, BLUEPRINT, (x, 0), (x, h), thin)
        for y in range(0, h, step):
            pygame.draw.line(s, BLUEPRINT, (0, y), (w, y), thin)

        def shape(points, fill=FILL, line=LINE, width=thick):
            pts = [at(x, y) for x, y in points]
            pygame.draw.polygon(s, fill, pts)
            pygame.draw.polygon(s, line, pts, width)

        def ellipse_points(cx, cy, rx, ry, a0=0, a1=360, n=96):
            return [(cx + rx * math.cos(math.radians(a)), cy + ry * math.sin(math.radians(a)))
                    for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]

        def capsule(cx, y0, y1, half, fill=FILL, line=LINE):
            x, y = at(cx - half, y0)
            rect = (x, y, 2 * half * k, (y1 - y0) * k)
            pygame.draw.rect(s, fill, rect, border_radius=round(half * k))
            pygame.draw.rect(s, line, rect, thick, border_radius=round(half * k))

        # Pylons, swept back from the hull to the nacelles.
        for side in (-1, 1):
            shape([(side * 50, 465), (side * 125, 545), (side * 125, 625), (side * 52, 560)])
        # Nacelles: long, fat, a quarter of the beam out; a domed Bussard
        # collector at the front, two vents, a grille down the inside.
        for side in (-1, 1):
            cx = side * 153
            capsule(cx, 452, 775, 34)
            capsule(cx, 458, 520, 22, fill=BRIGHT, line=LINE)
            for vy in (585, 610):
                pygame.draw.line(s, GRID, at(cx - 14, vy), at(cx + 14, vy), thick)
            pygame.draw.line(s, GRID, at(cx - side * 14, 560), at(cx - side * 14, 755), thin)
        # The engineering hull: swept, widest just aft of the saucer, a
        # chevron lattice either side of its spine.
        hull = [(-52, 330), (52, 330), (76, 455), (70, 560), (40, 690), (18, 718), (-18, 718), (-40, 690),
                (-70, 560), (-76, 455)]
        shape(hull)
        pygame.draw.line(s, GRID, at(0, 340), at(0, 712), thick)
        for y in range(420, 700, 26):
            for side in (-1, 1):
                half = 66 - max(0, y - 560) * 0.3
                pygame.draw.line(s, GRID, at(0, y), at(side * half, y - 46), thin)
        # The saucer's aft block (the impulse deck), under the saucer's edge.
        shape([(-140, 360), (140, 360), (122, 448), (-122, 448)])
        for x in (-90, -45, 45, 90):
            pygame.draw.line(s, GRID, at(x, 392), at(x, 446), thin)
        # The saucer: wider than long, rings and spokes round a raised centre.
        cx, cy, rx, ry = 0, 225, 300, 225
        shape(ellipse_points(cx, cy, rx, ry))
        for f in (0.9, 0.74, 0.58):
            pygame.draw.polygon(s, GRID, [at(*p) for p in ellipse_points(cx, cy, rx * f, ry * f)], thin)
        for a in range(0, 360, 10):
            inner = 0.45 if a % 20 else 0.4
            c, d = math.cos(math.radians(a)), math.sin(math.radians(a))
            pygame.draw.line(s, GRID, at(cx + rx * inner * c, cy + ry * inner * d),
                             at(cx + rx * 0.97 * c, cy + ry * 0.97 * d), thin)
        centre = ellipse_points(cx, cy + 10, 128, 92)
        shape(centre, fill=DEEP, line=LINE)
        pygame.draw.polygon(s, GRID, [at(*p) for p in ellipse_points(cx, cy + 10, 84, 60)], thin)
        x0, y0 = at(-17, cy - 17)
        pygame.draw.ellipse(s, BRIGHT, (x0, y0, 34 * k, 34 * k))                 # the bridge
        # The registry along the saucer's starboard side.
        label = font(0.62 * SCALE * self.k / 0.3).render("NCC-1701-D", True, LINE)
        label = pygame.transform.rotate(label, -90)
        s.blit(label, label.get_rect(center=at(196, cy)))


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
