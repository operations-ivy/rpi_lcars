"""What the ALERTS and WIGLE screens show, from the feeds' JSON: Prometheus'
/api/v1/alerts, overwatch's /api/state and wigle-console's /api/status.
Plain functions over plain data, so they're tested without a screen."""
import re

SEVERITY = {"critical": 0, "warning": 1, "info": 2}
# Prometheus' own plumbing, always firing: not a problem to show.
QUIET = {"Watchdog", "InfoInhibitor"}
# Labels that say where an alert is, best first.
WHERE = ("name", "job", "service", "namespace", "instance")
# Overwatch alerts this recent count as live (its page uses the same 5 min).
LIVE_SECONDS = 300
RECENT_SECONDS = 1800


def words(name):
    """"KubeProxyDown" -> "KUBE PROXY DOWN", "CPUThrottlingHigh" -> "CPU
    THROTTLING HIGH"."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name).upper()


def infra_alerts(data):
    """Firing alerts, worst first, one line each: [{"text", "severity"}]; None
    while Prometheus hasn't answered."""
    if data is None:
        return None
    seen, out = set(), []
    for a in data.get("data", {}).get("alerts", []):
        labels = a.get("labels", {})
        name, severity = labels.get("alertname", "?"), labels.get("severity", "none")
        if a.get("state") != "firing" or name in QUIET or severity not in SEVERITY:
            continue
        where = next((labels[k] for k in WHERE if labels.get(k)), "")
        text = f"{words(name)} {where.upper()}".strip()
        if text in seen:
            continue
        seen.add(text)
        out.append({"text": text, "severity": severity, "since": a.get("activeAt", "")})
    return sorted(out, key=lambda a: (SEVERITY[a["severity"]], a["since"]))


def overwatch(data, now):
    """{"feeds": [{"name", "word", "line", "severity"}], "recent": [{"text",
    "at", "live"}]}; None while overwatch hasn't answered. Severity is
    overwatch's: 0 all clear, 1 learning, 2 heads up, 3 alert or down."""
    if data is None:
        return None
    feeds, recent = [], []
    for f in data.get("feeds", []):
        state = f.get("state") or {}
        headline = (state.get("panel") or {}).get("headline") or {}
        if f.get("error"):
            feeds.append({"name": f["name"].upper(), "word": "NO SIGNAL", "line": "", "severity": 3})
        else:
            feeds.append({"name": f["name"].upper(), "word": headline.get("word", "--").upper(),
                          "line": (headline.get("line") or "").upper(), "severity": headline.get("severity", 0)})
        for a in state.get("alerts", []):
            age = now - a.get("at", 0)
            if age <= RECENT_SECONDS:
                detail = a.get("detail") or (f"{a['count']} NEARBY" if "count" in a else "")
                recent.append({"text": f"{a.get('label', a.get('kind', '?'))} {detail}".upper().strip(),
                               "at": a.get("at", 0), "live": age <= LIVE_SECONDS})
    recent.sort(key=lambda a: -a["at"])
    return {"feeds": feeds, "recent": recent}


def condition(infra, watch):
    """RED, YELLOW, GREEN, or UNKNOWN when neither feed has answered: the
    worst of the infrastructure's alerts and overwatch's feeds."""
    if infra is None and watch is None:
        return "UNKNOWN"
    worst = 2
    for a in infra or []:
        worst = min(worst, {"critical": 0, "warning": 1}.get(a["severity"], 2))
    for f in (watch or {}).get("feeds", []):
        worst = min(worst, 0 if f["severity"] >= 3 else 1 if f["severity"] == 2 else 2)
    if any(a["live"] for a in (watch or {}).get("recent", [])):
        worst = 0
    return ("RED", "YELLOW", "GREEN")[worst]


def wigle(data, now):
    """wigle-sync and the account, ready to show; None before an answer."""
    if data is None:
        return None
    last, sched, pi, account = (data.get(k) or {} for k in ("last_run", "schedule", "pi", "wigle"))
    runs = [r for r in (data.get("history") or {}).get("runs", []) if now - r.get("at", 0) <= 86400]
    uploads = account.get("uploads") or []
    errors = [e for e in (data.get("errors") or {}).get("items", []) if now - e.get("at", 0) <= 86400]
    return {
        "last_run": last.get("last_run_timestamp_seconds"),
        "last_ok": (last.get("last_run_timestamp_seconds") or 0) <= (last.get("last_success_timestamp_seconds") or 0),
        "next_run": sched.get("next_run"),
        "running": bool(sched.get("running")),
        "suspended": bool(sched.get("suspended")),
        "failed_jobs": sched.get("failed_jobs_24h", 0),
        "pi": (pi.get("host") or "PI").upper(),
        "pi_home": bool(pi.get("online_now")),
        "uploaded_24h": sum(r.get("uploaded", 0) for r in runs),
        "bytes_24h": sum(r.get("bytes_uploaded", 0) for r in runs),
        "failed_24h": sum(r.get("failed", 0) for r in runs),
        "processing": sum(1 for u in uploads if (u.get("percent_done") or 0) < 100),
        "rank": account.get("rank"), "prev_rank": account.get("prev_rank"),
        "month_rank": account.get("month_rank"),
        "wifi": account.get("wifi"), "bt": account.get("bt"),
        "locations": account.get("locations"), "month_events": account.get("month_events"),
        "error": (errors[0].get("event") or "").upper() if errors else "",
        "error_level": errors[0].get("level", "") if errors else "",
    }


def ago(seconds):
    if seconds is None:
        return "--"
    if seconds < 90:
        return "JUST NOW"
    if seconds < 5400:
        return f"{seconds / 60:.0f} MIN AGO"
    if seconds < 172800:
        return f"{seconds / 3600:.0f} HR AGO"
    return f"{seconds / 86400:.0f} DAYS AGO"


def until(seconds):
    if seconds is None:
        return "--"
    if seconds <= 60:
        return "NOW"
    if seconds < 5400:
        return f"IN {seconds / 60:.0f} MIN"
    return f"IN {seconds / 3600:.0f} HR"


def size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def number(n):
    return "--" if n is None else f"{n:,.0f}"
