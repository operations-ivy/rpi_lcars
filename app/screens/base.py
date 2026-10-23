"""The frame every panel screen shares: the LCARS background, a clock and the
stardate under it in the top corner (both from its left), the title at the top
right with a running block of numbers before it, as LCARS screens have, every
STATUS on the top bar's first long block and a registry on the second,
the other screens down the sidebar, the Home Assistant link along the bottom."""
from datetime import datetime

from datasources.network import get_ip_addresses
from ui import colours
from ui.widgets.background import LcarsBackgroundImage
from ui.widgets.panel_widgets import LcarsBlock, LcarsCascade, LcarsKey, LcarsLabel
from ui.widgets.screen import LcarsScreen

# The frame's open area (x from 125 to 785, y from 100 to 440).
LEFT, RIGHT, TOP, BOTTOM = 140, 775, 105, 435
# The clock and the stardate's left edge, in the top left block.
CORNER = 30
# The top band, above the top bar: the title against its right edge, the
# numbers from TITLE_LEFT up to TITLE_GAP short of the title.
TITLE_RIGHT, TITLE_LEFT, TITLE_GAP, TITLE_SIZE = 783, 135, 24, 2

# Blocks, (top, left) and size, matching lcars_screen_1.png. The top bar's two
# long blocks (both of its rows) hold STATUS and the registry.
TOP_BAR = {
    "status": ((56, 412), (149, 41)),
    "registry": ((56, 563), (179, 41)),
}
SIDEBAR = {
    "upper": ((145, 16), (98, 62)),
    "middle": ((211, 16), (98, 34)),
    "lower": ((249, 16), (98, 147)),
}
# The sidebar's blocks go to the screens in order; the lower block is cut into
# as many as are left, with the background's 4 px black gap between.
GAP = 4
# The top bar's second block: a registry, like the ship on STATUS.
REGISTRY = "NCC-1701-D"
# STATUS on the top bar, larger than the sidebar's text.
STATUS_SIZE = 1.6
CONDITION = {"RED": ("RED ALERT", colours.RED), "YELLOW": ("YELLOW ALERT", colours.GOLD),
             "GREEN": ("ALERTS", colours.BLUE), "UNKNOWN": ("ALERTS", colours.GREY_BLUE)}


class PanelScreen(LcarsScreen):
    name = "panel"
    title = ""

    def __init__(self, panel):
        LcarsScreen.__init__(self)
        self.panel = panel

    def setup(self, all_sprites):
        self.sprites = all_sprites
        all_sprites.add(LcarsBackgroundImage("assets/lcars_screen_1.png"), layer=0)
        self.clock = self.add(LcarsLabel(colours.BLACK, (13, CORNER), "", 1.5))
        title = self.add(LcarsLabel(colours.ORANGE, (0, TITLE_RIGHT), self.title, TITLE_SIZE, "right"))
        width = title.rect.left - TITLE_GAP - TITLE_LEFT
        self.cascade = self.add(LcarsCascade((4, TITLE_LEFT), (width, 40))) if width > 60 else None
        # The first address only: the bar fits one.
        self.add(LcarsLabel(colours.BLACK, (444, 470), next(iter(get_ip_addresses()), "")))
        self.stardate = self.add(LcarsLabel(colours.BLACK, (46, CORNER), "", 0.7))
        self.link = self.add(LcarsLabel(colours.BLUE, (BOTTOM - 25, RIGHT), "", 1.2, "right"))
        self.build()
        self.refresh()

    def add(self, sprite, layer=1):
        self.sprites.add(sprite, layer=layer)
        return sprite

    def sidebar(self, slot, colour, text, handler=None):
        pos, size = SIDEBAR[slot] if isinstance(slot, str) else slot
        return self.add(LcarsKey(colour, pos, size, text, handler, align="corner"), layer=2)

    def screens(self, action=None):
        """The sidebar's blocks, in order: (name, colour, text, handler), and
        last the screen's own action (the thermostat's UNLOCK or SECURE)."""
        cfg = self.panel.cfg
        out = [("thermostat", colours.ORANGE, "THERMOSTAT", self.go_thermostat)]
        if cfg.PROMETHEUS_URL or cfg.OVERWATCH_URL:
            out.append(("alerts", colours.BLUE, "ALERTS", self.go_alerts))
        if cfg.WIGLE_URL:
            out.append(("wigle", colours.GOLD, "WIGLE", self.go_wigle))
        if cfg.CALENDARS:
            out.append(("calendar", colours.BLUE, "CALENDAR", self.go_calendar))
        if cfg.SHOPPING_LIST:
            out.append(("shopping", colours.PURPLE, "SHOPPING", self.go_shopping))
        if cfg.MEDIA_PLAYER and cfg.MEDIA_BUTTON:
            out.append(("media", colours.RED_BROWN, "PS5", self.go_media))
        if action:
            text, handler, colour = action
            out.append(("action", colour, text, handler))
        return out

    def nav(self, action=None):
        """STATUS and the registry on the top bar, the other screens down the
        sidebar (screens()). The current screen's block does nothing. The
        ALERTS block names the alert condition in its colour."""
        here = self.name
        pos, size = TOP_BAR["status"]
        self.nav_keys = {"status": self.add(LcarsKey(colours.BEIGE, pos, size, "STATUS",
                                                     None if here == "status" else self.go_status,
                                                     text_size=STATUS_SIZE, align="corner"), layer=2)}
        self.add(LcarsKey(colours.ORANGE, *TOP_BAR["registry"], REGISTRY, align="corner"), layer=2)
        # The background splits only the bar's upper row there: black the
        # whole gap between the two.
        (top, left), (width, height) = TOP_BAR["status"]
        gap = TOP_BAR["registry"][0][1] - (left + width)
        self.add(LcarsBlock(colours.BLACK, (top, left + width), (gap, height)), layer=2)
        blocks = self.screens(action)
        slots = [SIDEBAR["upper"], SIDEBAR["middle"]][:len(blocks)]
        rest = len(blocks) - len(slots)
        if rest:
            (top, left), (width, height) = SIDEBAR["lower"]
            each = (height - GAP * (rest - 1)) // rest
            for i in range(rest):
                h = each if i < rest - 1 else height - (each + GAP) * (rest - 1)
                slots.append(((top, left), (width, h)))
                if i < rest - 1:
                    self.add(LcarsBlock(colours.BLACK, (top + h, left), (width, GAP)), layer=2)
                top += h + GAP
        for slot, (name, colour, text, handler) in zip(slots, blocks):
            self.nav_keys[name] = self.sidebar(slot, colour, text, None if here == name else handler)
        return self.nav_keys.get("action")

    def show_condition(self):
        key = self.nav_keys.get("alerts") if hasattr(self, "nav_keys") else None
        if key is not None:
            text, colour = CONDITION[self.panel.alerts()["condition"]]
            key.set_text(text)
            key.set_colour(colour)

    def link_text(self):
        """(ok, text) for the bottom right line."""
        ok, text = self.panel.link()
        return ok, f"HOME ASSISTANT LINK: {text}"

    def build(self):
        """Add this screen's widgets."""

    def refresh(self):
        """Bring the widgets up to date; called every frame."""

    def update(self, screenSurface, fpsClock):
        now = datetime.now()
        self.clock.set(f"{now:%H:%M}")
        self.stardate.set(f"STARDATE {now:%Y.%j}")
        ok, text = self.link_text()
        self.link.set(text, colours.BLUE if ok else colours.RED)
        self.show_condition()
        if self.cascade is not None:
            self.cascade.tick(self.panel.clock())
        if self.panel.night.dark and self.name != "status":
            self.go_status()
        else:
            self.refresh()

    # Navigation (imports are late: the screens import each other).

    def go_status(self, *_):
        from screens.status import ScreenStatus
        self.leave()
        self.loadScreen(ScreenStatus(self.panel))

    def go_thermostat(self, *_):
        from screens.thermostat import ScreenThermostat
        self.leave()
        self.loadScreen(ScreenThermostat(self.panel))

    def go_shopping(self, *_):
        from screens.shopping import ScreenShopping
        self.leave()
        self.loadScreen(ScreenShopping(self.panel))

    def go_media(self, *_):
        from screens.media import ScreenMedia
        self.leave()
        self.loadScreen(ScreenMedia(self.panel))

    def go_alerts(self, *_):
        from screens.alerts import ScreenAlerts
        self.leave()
        self.loadScreen(ScreenAlerts(self.panel))

    def go_calendar(self, *_):
        from screens.calendar import ScreenCalendar
        self.leave()
        self.loadScreen(ScreenCalendar(self.panel))

    def go_wigle(self, *_):
        from screens.wigle import ScreenWigle
        self.leave()
        self.loadScreen(ScreenWigle(self.panel))

    def go_authorize(self, *_):
        """The keypad, or the thermostat if it's open already."""
        if self.panel.read_only or self.panel.lock.can_change:
            self.go_thermostat()
            return
        from screens.authorize import ScreenAuthorize
        self.leave()
        self.loadScreen(ScreenAuthorize(self.panel))

    def leave(self):
        """Called before switching away."""
