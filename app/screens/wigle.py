"""Wardriving: wigle-sync's runs (last, next, the Pi home or away, what went
up in the last day) and the WiGLE account (rank and totals), from
wigle-console's /api/status. Read-only, open to anyone."""
from panel.infra import ago, number, size, until
from screens.base import LEFT, RIGHT, TOP, PanelScreen
from ui import colours
from ui.widgets.panel_widgets import LcarsLabel

RIGHT_X, VALUE_X = 470, 610
ACCOUNT_ROWS = ("WI-FI", "BLUETOOTH", "LOCATIONS", "THIS MONTH")
SYNC_ROWS = ("LAST RUN", "NEXT RUN", "PI", "UPLOADED 24H", "PROCESSING", "FAILED 24H")
ROW_HEIGHT = 27


class ScreenWigle(PanelScreen):
    name = "wigle"
    title = "WARDRIVING OPERATIONS"

    def build(self):
        self.nav()
        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, LEFT), "WIGLE RANK", 1.5))
        self.rank = self.add(LcarsLabel(colours.BEIGE, (TOP + 32, LEFT), "--", 4))
        self.month_rank = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 112, LEFT), "", 1.1))
        self.account = {}
        for i, row in enumerate(ACCOUNT_ROWS):
            top = TOP + 145 + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, LEFT), row, 1.1))
            self.account[row] = self.add(LcarsLabel(colours.BLUE, (top, LEFT + 130), "--", 1.1))

        self.add(LcarsLabel(colours.ORANGE, (TOP + 10, RIGHT_X), "SYNC", 1.5))
        self.sync = {}
        for i, row in enumerate(SYNC_ROWS):
            top = TOP + 45 + i * ROW_HEIGHT
            self.add(LcarsLabel(colours.PURPLE, (top, RIGHT_X), row, 1.1))
            self.sync[row] = self.add(LcarsLabel(colours.BLUE, (top, VALUE_X), "--", 1.1,
                                                 max_width=RIGHT - VALUE_X))
        self.error = self.add(LcarsLabel(colours.GREY_BLUE, (TOP + 262, LEFT), "", 1.0, max_width=RIGHT - LEFT))

    def link_text(self):
        age = self.panel.feed_age("wigle")
        if age is None:
            return False, "WIGLE CONSOLE OFFLINE"
        return not self.panel.feed_stale("wigle"), f"WIGLE CONSOLE - {ago(age)}"

    def refresh(self):
        w = self.panel.wigle()
        if w is None:
            self.rank.set("--", colours.GREY_BLUE)
            self.error.set("WIGLE CONSOLE NOT ANSWERING", colours.ORANGE)
            return
        stale = self.panel.feed_stale("wigle")
        self.rank.set(number(w["rank"]), colours.GREY_BLUE if stale else colours.BEIGE)
        self.month_rank.set(f"MONTH RANK {number(w['month_rank'])}" if w["month_rank"] else "")
        self.account["WI-FI"].set(number(w["wifi"]))
        self.account["BLUETOOTH"].set(number(w["bt"]))
        self.account["LOCATIONS"].set(number(w["locations"]))
        self.account["THIS MONTH"].set(f"{number(w['month_events'])} EVENTS" if w["month_events"] is not None else "--")

        now = self.panel.now()
        last = w["last_run"]
        self.sync["LAST RUN"].set(f"{ago(None if last is None else now - last)}{'' if w['last_ok'] else ' FAILED'}",
                                  colours.BLUE if w["last_ok"] else colours.RED)
        if w["suspended"]:
            self.sync["NEXT RUN"].set("SUSPENDED", colours.ORANGE)
        elif w["running"]:
            self.sync["NEXT RUN"].set("RUNNING NOW", colours.GOLD)
        else:
            self.sync["NEXT RUN"].set(until(None if w["next_run"] is None else w["next_run"] - now))
        self.sync["PI"].set(f"{w['pi']} {'HOME' if w['pi_home'] else 'AWAY'}",
                            colours.BLUE if w["pi_home"] else colours.GREY_BLUE)
        n = w["uploaded_24h"]
        self.sync["UPLOADED 24H"].set(f"{n} FILE{'' if n == 1 else 'S'}  {size(w['bytes_24h'])}" if n else "NONE")
        p = w["processing"]
        self.sync["PROCESSING"].set(f"{p} FILE{'' if p == 1 else 'S'}" if p else "NONE",
                                    colours.GOLD if p else colours.BLUE)
        failed = w["failed_24h"] + w["failed_jobs"]
        self.sync["FAILED 24H"].set(str(failed), colours.RED if failed else colours.BLUE)
        if w["error"]:
            self.error.set(w["error"], colours.RED if w["error_level"] == "error" else colours.ORANGE)
        else:
            self.error.set("NO ERRORS IN THE LAST 24 HOURS", colours.GREY_BLUE)
