"""The frame every panel screen sits in, drawn in code at three times the size
and scaled down for smooth edges: a header sweep over a body sweep, the way
LCARS joins two elbows. An elbow's inner radius is half its outer (the R
package lcars's sweep), bars are one thickness, segments sit a black gap
apart and only the last in a run is rounded (joernweissenborn/lcars's bars).
The colours are the ones louh/lcars takes from the show.

Alert mode (LCARdS's idea): under a red or yellow condition the whole frame
turns that colour. Each condition is drawn once and kept."""
import pygame

from ui import colours
from ui.widgets.background import LcarsBackground

SCALE = 3
OUTER, INNER, CAP = 45, 22, 9
LEFT, COLUMN, EDGE = 16, 114, 784    # the left column, and the bars' right end
HEAD, BODY, FOOT = (56, 74), (79, 97), (446, 464)
NAV_TOP, NAV_BOTTOM = 145, 396
# Under the sidebar's keys, with the gaps between them (screens/base.py).
NAV_BLOCKS = ((145, 207), (211, 245), (249, 396))

NORMAL = {"sky": colours.SKY, "blue": colours.DARK_BLUE, "orange": colours.ORANGE, "lilac": colours.PURPLE,
          "plum": colours.PLUM, "rose": colours.RED_BROWN, "gold": colours.GOLD, "peach": colours.PEACH,
          "beige": colours.BEIGE}
_RED = ((255, 85, 85), (153, 34, 34), (255, 120, 90), (204, 102, 102), (120, 30, 30), (255, 153, 153))
_YELLOW = ((255, 204, 102), (153, 102, 0), (255, 153, 0), (255, 221, 136), (120, 80, 0), (255, 238, 170))
# The same roles in a condition's colours.
TINTS = {"RED": _RED, "YELLOW": _YELLOW}
# The ones bright enough to carry a key's black text (screens/base.py).
KEY_TINTS = {name: (tint[0], tint[2], tint[3]) for name, tint in TINTS.items()}
_ROLES = ("sky", "blue", "orange", "lilac", "plum", "beige")
_SAME = {"rose": "sky", "gold": "orange", "peach": "lilac"}
_drawn = {}


def palette(condition):
    tint = TINTS.get(condition)
    if tint is None:
        return NORMAL
    roles = dict(zip(_ROLES, tint))
    return {**roles, **{role: roles[like] for role, like in _SAME.items()}}


def draw(condition):
    p = palette(condition)
    s = pygame.Surface((800 * SCALE, 480 * SCALE))
    s.fill(colours.BLACK)

    def box(role, x0, y0, x1, y1, **radii):
        colour = colours.BLACK if role is None else p[role]
        pygame.draw.rect(s, colour, (x0 * SCALE, y0 * SCALE, (x1 - x0) * SCALE, (y1 - y0) * SCALE),
                         **{k: r * SCALE for k, r in radii.items()})

    def elbow(role, top, bottom, right, bar, up):
        """A column running into a bar: along the top of the block when up,
        else along its bottom."""
        corner = "border_top_left_radius" if up else "border_bottom_left_radius"
        box(role, LEFT, top, right, bottom, **{corner: OUTER})
        box(None, COLUMN, bar[1] if up else top, 800, bottom if up else bar[0], **{corner: INNER})

    elbow("sky", 0, HEAD[1], 250, HEAD, False)
    elbow("lilac", BODY[0], NAV_TOP - 4, 280, BODY, True)
    for top, bottom in NAV_BLOCKS:
        box("lilac", LEFT, top, COLUMN, bottom)
    elbow("gold", NAV_BOTTOM + 4, FOOT[1], 292, FOOT, False)

    def row(y, *segments):
        for role, x0, x1 in segments:
            box(role, x0, y[0], x1, y[1])

    # The header and body bars meet the STATUS and registry keys at x=412.
    row(HEAD, ("blue", 254, 360), ("orange", 364, 408))
    row(BODY, ("plum", 284, 408))
    box("rose", 746, HEAD[0], EDGE, HEAD[1], border_top_right_radius=CAP, border_bottom_right_radius=CAP)
    box("plum", 746, BODY[0], EDGE, BODY[1], border_top_right_radius=CAP, border_bottom_right_radius=CAP)
    row(FOOT, ("orange", 296, 358), ("peach", 362, 456), ("sky", 460, 686))
    box("beige", 690, FOOT[0], EDGE, FOOT[1], border_top_right_radius=CAP, border_bottom_right_radius=CAP)
    return pygame.transform.smoothscale(s, (800, 480)).convert()


class LcarsFrame(LcarsBackground):
    def __init__(self, condition=None):
        self.condition = condition
        self.image = self.drawn(condition)
        LcarsBackground.__init__(self, None, (0, 0), None)

    @staticmethod
    def drawn(condition):
        key = condition if condition in TINTS else None
        if key not in _drawn:
            _drawn[key] = draw(key)
        return _drawn[key]

    def set(self, condition):
        if condition != self.condition:
            self.condition = condition
            self.image = self.drawn(condition)
            self.dirty = 1
