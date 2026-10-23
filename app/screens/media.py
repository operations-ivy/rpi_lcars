"""The PS5: whether it's on, what's playing, and the game's art (the game
last played while it's off), from Home Assistant's PlayStation Network
integration. Read-only, open to anyone."""
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsHeader, LcarsLabel, LcarsPicture

PICTURE = 280  # the art's square box
TEXT_X = LEFT + PICTURE + 30
STATES = {"playing": "PLAYING", "on": "ONLINE", "idle": "IDLE", "paused": "PAUSED",
          "standby": "STANDBY", "off": "OFFLINE"}


class ScreenMedia(PanelScreen):
    name = "media"
    title = "RECREATION DECK"

    def build(self):
        self.nav()
        self.picture = self.add(LcarsPicture((TOP + 10, LEFT), (PICTURE, PICTURE)))
        self.add(LcarsHeader(colours.ORANGE, (TOP + 10, TEXT_X), RIGHT - TEXT_X, "PLAYSTATION 5", 1.5))
        self.state = self.add(LcarsLabel(colours.BEIGE, (TOP + 45, TEXT_X), "--", 3))
        self.caption = self.add(LcarsLabel(colours.PURPLE, (TOP + 130, TEXT_X), "", 1.2))
        self.game = self.add(LcarsLabel(colours.BLUE, (TOP + 160, TEXT_X), "", 1.4, max_width=RIGHT - TEXT_X))

    def refresh(self):
        media = self.panel.media()
        state = media["state"]
        playing = state in ("playing", "paused")
        self.state.set(STATES.get(state, "NO SIGNAL" if state is None else state.upper()),
                       colours.GOLD if playing else colours.BEIGE)
        self.picture.set(media["picture"])
        if media["title"]:
            self.caption.set("NOW PLAYING" if playing else "ACTIVITY")
            self.game.set(media["title"].upper())
        else:
            self.caption.set("LAST PLAYED" if media["picture"] else "")
            self.game.set("")
