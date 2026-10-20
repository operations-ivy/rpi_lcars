"""Home Assistant's shopping list (a to-do list): what's still needed, then
what's been ticked off. A tap ticks an item off, or back on. Open to anyone:
it isn't the thermostat."""
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsKey, LcarsLabel

COLUMNS, ROWS = 2, 7
ROW_TOP, ROW_HEIGHT, ROW_STEP, COLUMN_GAP = TOP + 50, 30, 36, 25
COLUMN_WIDTH = (RIGHT - LEFT - COLUMN_GAP) // COLUMNS


class ScreenShopping(PanelScreen):
    name = "shopping"
    title = "SUPPLY MANIFEST"

    def build(self):
        self.nav()
        self.heading = self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "", 1.5))
        self.more = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 15, RIGHT), "", 1.1, "right"))
        self.rows = []
        for column in range(COLUMNS):
            for row in range(ROWS):
                pos = (ROW_TOP + row * ROW_STEP, LEFT + column * (COLUMN_WIDTH + COLUMN_GAP))
                key = self.add(LcarsKey(colours.BLUE, pos, (COLUMN_WIDTH, ROW_HEIGHT), "", self.tap_item,
                                        align="left"), layer=2)
                key.item = None
                self.rows.append(key)
        self.empty = self.add(LcarsLabel(colours.GREY_BLUE, (ROW_TOP, LEFT), "", 1.2, max_width=RIGHT - LEFT))

    def tap_item(self, key, *_):
        if key.item:
            key.item["status"] = self.panel.tick_item(key.item)
            self.refresh()

    def refresh(self):
        items = self.panel.shopping()
        if items is None:
            items, self.heading_text = [], "SHOPPING LIST UNAVAILABLE"
        else:
            needed = sum(1 for i in items if i.get("status") != "completed")
            self.heading_text = f"{needed} ITEM{'' if needed == 1 else 'S'} NEEDED" if needed else "NOTHING NEEDED"
        self.heading.set(self.heading_text)
        shown = items[:len(self.rows)]
        self.more.set(f"+{len(items) - len(shown)} MORE" if len(items) > len(shown) else "")
        for key, item in zip(self.rows, shown + [None] * (len(self.rows) - len(shown))):
            key.item = item
            key.visible = item is not None
            if item:
                key.set_text(item.get("summary", "").upper())
                key.set_colour(colours.DISABLED if item.get("status") == "completed" else colours.BLUE)
        self.empty.set("" if items else "ADD ITEMS FROM THE HOME ASSISTANT APP")
