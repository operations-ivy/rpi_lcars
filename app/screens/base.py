"""The frame every panel screen shares: the LCARS background, a title in the
top bar, the sidebar's three blocks, the stardate and the Home Assistant link
along the bottom."""
from datetime import datetime

from datasources.network import get_ip_addresses
from ui import colours
from ui.widgets.background import LcarsBackgroundImage
from ui.widgets.panel_widgets import LcarsKey, LcarsLabel
from ui.widgets.screen import LcarsScreen

# The frame's open area (x from 125 to 785, y from 100 to 440).
LEFT, RIGHT, TOP, BOTTOM = 140, 775, 105, 435

# Sidebar blocks, (top, left) and size, matching lcars_screen_1.png.
SIDEBAR = {
    "upper": ((145, 16), (98, 62)),
    "middle": ((211, 16), (98, 34)),
    "lower": ((249, 16), (98, 147)),
}


class PanelScreen(LcarsScreen):
    name = "panel"
    title = ""

    def __init__(self, panel):
        LcarsScreen.__init__(self)
        self.panel = panel

    def setup(self, all_sprites):
        self.sprites = all_sprites
        all_sprites.add(LcarsBackgroundImage("assets/lcars_screen_1.png"), layer=0)
        self.add(LcarsLabel(colours.BLACK, (15, 44), "BRICK 1982"))
        self.add(LcarsLabel(colours.ORANGE, (0, 135), self.title, 2))
        # The first address only: the bar fits one.
        self.add(LcarsLabel(colours.BLACK, (444, 470), next(iter(get_ip_addresses()), "")))
        self.stardate = self.add(LcarsLabel(colours.BLUE, (BOTTOM - 25, LEFT), "", 1.2))
        self.link = self.add(LcarsLabel(colours.BLUE, (BOTTOM - 25, RIGHT), "", 1.2, "right"))
        self.build()
        self.refresh()

    def add(self, sprite, layer=1):
        self.sprites.add(sprite, layer=layer)
        return sprite

    def sidebar(self, slot, colour, text, handler=None):
        pos, size = SIDEBAR[slot]
        return self.add(LcarsKey(colour, pos, size, text, handler, align="corner"), layer=2)

    def nav(self, lower_text, lower_handler=None, lower_colour=colours.PEACH):
        """The sidebar every screen has: STATUS, WEATHER, and the climate block
        (MONITOR ONLY, without a handler, when read-only). The current screen's
        block does nothing."""
        here = self.name
        self.sidebar("upper", colours.BEIGE, "STATUS", None if here == "status" else self.go_status)
        self.sidebar("middle", colours.ORANGE, "WEATHER", None if here == "weather" else self.go_weather)
        if self.panel.read_only:
            return self.sidebar("lower", colours.GREY_BLUE, "MONITOR ONLY")
        return self.sidebar("lower", lower_colour, lower_text, lower_handler)

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
        self.stardate.set(f"STARDATE {now:%Y.%j}  {now:%H:%M}")
        ok, text = self.link_text()
        self.link.set(text, colours.BLUE if ok else colours.RED)
        if self.panel.night.dark and self.name != "status":
            self.go_status()
        else:
            self.refresh()

    # Navigation (imports are late: the screens import each other).

    def go_status(self, *_):
        from screens.status import ScreenStatus
        self.leave()
        self.loadScreen(ScreenStatus(self.panel))

    def go_weather(self, *_):
        from screens.weather import ScreenWeather
        self.leave()
        self.loadScreen(ScreenWeather(self.panel))

    def go_climate(self, *_):
        """Climate control if the lock allows it, else the keypad; nothing
        when read-only."""
        if self.panel.read_only:
            self.go_status()
            return
        self.leave()
        if self.panel.lock.can_change:
            from screens.climate import ScreenClimate
            self.loadScreen(ScreenClimate(self.panel))
        else:
            from screens.authorize import ScreenAuthorize
            self.loadScreen(ScreenAuthorize(self.panel))

    def leave(self):
        """Called before switching away."""
