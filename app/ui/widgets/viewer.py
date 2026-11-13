"""The slideshow's two frames (rpi_lcars#21), drawn in code like the panel's
own (ui/widgets/frame.py: three times the size, scaled down for smooth edges),
after the layouts of the show's display panels; nothing is copied from
anywhere. Each leaves a window for the photo, and blocks for the animation
(ui/widgets/panel_widgets.py's cascade, runner and blinkers) to sit on.

    "column"      one tall column on the left, elbows into a bar at the top and
                  the bottom; the photo to the right.
    "viewscreen"  a column each side, both elbowed top and bottom; the photo
                  centred between them, like the bridge's viewscreen.

A yellow condition tints the frame (a red one ends the slideshow). Each frame
is drawn once per condition and kept."""
import pygame

from ui import colours
from ui.widgets.frame import palette

SCALE = 3
KINDS = ("column", "viewscreen")
OUTER, INNER, CAP = 40, 18, 7
TOP_BAR, BOTTOM_BAR = (24, 38), (442, 456)
GAP = 4


class Layout:
    """Where things go on one frame: the photo's window, and the animation's
    places, each (left, top, width, height); the title and the counter are
    (top, right edge, colour)."""

    def __init__(self, window, cascade, runner, blinkers, title, counter):
        self.window, self.cascade, self.runner = window, cascade, runner
        self.blinkers, self.title, self.counter = blinkers, title, counter


LAYOUTS = {
    "column": Layout(window=(116, 46, 676, 390), cascade=(272, 0, 330, 22), runner=(272, 460, 120, 16),
                     blinkers=((14, 160, 80, 30), (14, 302, 80, 30)),
                     title=(0, 790, colours.ORANGE), counter=(459, 790, colours.BEIGE)),
    "viewscreen": Layout(window=(96, 46, 608, 390), cascade=(212, 0, 210, 22), runner=(212, 460, 120, 16),
                         blinkers=((14, 200, 64, 26), (722, 200, 64, 26), (722, 330, 64, 26)),
                         title=(0, 712, colours.ORANGE), counter=(459, 586, colours.BEIGE)),
}


def draw(kind, condition=None):
    p = palette(condition)
    s = pygame.Surface((800 * SCALE, 480 * SCALE))
    s.fill(colours.BLACK)

    def box(role, x0, y0, x1, y1, **radii):
        colour = colours.BLACK if role is None else p[role]
        pygame.draw.rect(s, colour, (x0 * SCALE, y0 * SCALE, (x1 - x0) * SCALE, (y1 - y0) * SCALE),
                         **{k: r * SCALE for k, r in radii.items()})

    def elbow(role, x0, x1, y0, y1, bar, inner_x, top, left):
        """A column (x0 to inner_x) turning into a bar (bar's rows) at the
        frame's top or bottom, towards the middle; the block runs x0..x1."""
        v, h = ("top" if top else "bottom"), ("left" if left else "right")
        box(role, x0, y0, x1, y1, **{f"border_{v}_{h}_radius": OUTER})
        cx0, cx1 = (inner_x, x1) if left else (x0, inner_x)
        cy0, cy1 = (bar[1], y1) if top else (y0, bar[0])
        box(None, cx0, cy0, cx1, cy1, **{f"border_{v}_{h}_radius": INNER})

    def bar(y, *segments, cap=None):
        for role, x0, x1 in segments:
            box(role, x0, y[0], x1, y[1])
        if cap:
            role, x0, x1 = cap
            box(role, x0, y[0], x1, y[1], border_top_right_radius=CAP, border_bottom_right_radius=CAP)

    def column(x0, x1, y0, y1, roles):
        """Blocks down a column, a gap apart, split as roles' weights say."""
        total = sum(w for _, w in roles)
        height = y1 - y0 - GAP * (len(roles) - 1)
        y = y0
        for i, (role, w) in enumerate(roles):
            h = round(height * w / total) if i < len(roles) - 1 else y1 - y
            box(role, x0, y, x1, y + h)
            y += h + GAP

    if kind == "column":
        elbow("sky", 8, 266, 0, 38, TOP_BAR, 98, top=False, left=True)
        elbow("gold", 8, 266, 442, 480, BOTTOM_BAR, 98, top=True, left=True)
        column(8, 98, 42, 438, (("lilac", 3), ("plum", 1), ("blue", 4), ("orange", 2)))
        bar(TOP_BAR, ("blue", 270, 520), ("orange", 524, 700), cap=("rose", 704, 792))
        bar(BOTTOM_BAR, ("orange", 270, 400), ("peach", 404, 640), cap=("beige", 644, 792))
    else:
        elbow("sky", 8, 206, 0, 38, TOP_BAR, 82, top=False, left=True)
        elbow("gold", 8, 206, 442, 480, BOTTOM_BAR, 82, top=True, left=True)
        elbow("lilac", 594, 792, 0, 38, TOP_BAR, 718, top=False, left=False)
        elbow("orange", 594, 792, 442, 480, BOTTOM_BAR, 718, top=True, left=False)
        column(8, 82, 42, 438, (("plum", 2), ("blue", 3), ("rose", 1), ("lilac", 3)))
        column(718, 792, 42, 438, (("orange", 3), ("beige", 1), ("plum", 3), ("sky", 2)))
        bar(TOP_BAR, ("blue", 210, 400), ("peach", 404, 590))
        bar(BOTTOM_BAR, ("orange", 210, 330), ("peach", 334, 590))
    return pygame.transform.smoothscale(s, (800, 480)).convert()


_drawn = {}


def frame(kind, condition=None):
    key = (kind, condition if condition == "YELLOW" else None)
    if key not in _drawn:
        _drawn[key] = draw(*key)
    return _drawn[key]
