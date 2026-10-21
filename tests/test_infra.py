import io
import json

from datasources.feeds import JsonFeed
from metrics import Metrics
from panel import infra


def test_words():
    assert infra.words("KubeProxyDown") == "KUBE PROXY DOWN"
    assert infra.words("CPUThrottlingHigh") == "CPU THROTTLING HIGH"
    assert infra.words("TargetDown") == "TARGET DOWN"


def test_infra_alerts_dedupes_and_skips_plumbing():
    same = {"labels": {"alertname": "NodeSystemdServiceFailed", "name": "foo.service", "severity": "warning"},
            "state": "firing", "activeAt": "a"}
    data = {"data": {"alerts": [same, same, {"labels": {"alertname": "Watchdog", "severity": "none"}, "state": "firing"},
                                {"labels": {"alertname": "X", "severity": "critical"}, "state": "pending"}]}}
    assert infra.infra_alerts(data) == [{"text": "NODE SYSTEMD SERVICE FAILED FOO.SERVICE", "severity": "warning",
                                         "since": "a"}]
    assert infra.infra_alerts(None) is None


def test_condition():
    assert infra.condition(None, None) == "UNKNOWN"
    assert infra.condition([], {"feeds": [], "recent": []}) == "GREEN"
    assert infra.condition([{"severity": "info"}], None) == "GREEN"
    assert infra.condition([{"severity": "warning"}], None) == "YELLOW"
    assert infra.condition([], {"feeds": [{"severity": 2}], "recent": []}) == "YELLOW"
    assert infra.condition([], {"feeds": [{"severity": 3}], "recent": []}) == "RED"
    assert infra.condition([], {"feeds": [], "recent": [{"live": True}]}) == "RED"


def test_overwatch_feed_down_and_old_alerts():
    data = {"feeds": [{"name": "scanner", "error": "connection refused", "state": None},
                      {"name": "upnp", "error": "", "state": {"alerts": [
                          {"label": "UPnP port forward", "at": 0, "detail": "opened"}], "panel": {}}}]}
    out = infra.overwatch(data, now=10000)
    assert out["feeds"][0] == {"name": "SCANNER", "word": "NO SIGNAL", "line": "", "severity": 3}
    assert out["recent"] == []                          # older than 30 minutes


def test_sizes_and_times():
    assert infra.size(512) == "512 B" and infra.size(1048576) == "1.0 MB"
    assert infra.ago(30) == "JUST NOW" and infra.ago(7200) == "2 HR AGO" and infra.ago(None) == "--"
    assert infra.until(30) == "NOW" and infra.until(480) == "IN 8 MIN"
    assert infra.number(12345) == "12,345" and infra.number(None) == "--"


class Opener:
    def __init__(self, body=None, fail=None):
        self.body, self.fail, self.calls = body, fail, 0

    def __call__(self, req, timeout):
        self.calls += 1
        if self.fail:
            raise self.fail
        return io.BytesIO(json.dumps(self.body).encode())


def test_feed_keeps_the_last_answer_while_down():
    m = Metrics()
    opener = Opener({"ok": 1})
    t = [100.0]
    feed = JsonFeed("wigle", "http://x/api/status", 60, m, opener=opener, now=lambda: t[0])
    assert feed.data is None and feed.age() is None and m.get("lcars_feed_up", feed="wigle") == 0
    assert feed.poll()
    assert feed.data == {"ok": 1} and m.get("lcars_feed_up", feed="wigle") == 1
    opener.fail = OSError("down")
    t[0] += 30
    assert not feed.poll()
    assert feed.data == {"ok": 1} and feed.age() == 30 and feed.error == "OFFLINE"
    assert m.get("lcars_feed_requests_total", feed="wigle", result="error") == 1
