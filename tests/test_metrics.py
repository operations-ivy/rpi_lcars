import urllib.request

from metrics import Metrics


def test_render_groups_by_name_with_help():
    m = Metrics()
    m.inc("lcars_taps_total", woke="false")
    m.inc("lcars_taps_total", woke="false")
    m.inc("lcars_taps_total", woke="true")
    m.set("lcars_ha_up", 1)
    text = m.render()
    assert text.count("# TYPE lcars_taps_total counter") == 1
    assert 'lcars_taps_total{woke="false"} 2' in text
    assert 'lcars_taps_total{woke="true"} 1' in text
    assert "lcars_ha_up 1" in text


def test_serves_metrics():
    m = Metrics()
    m.set("lcars_ha_up", 0)
    server = m.serve(0, host="127.0.0.1")
    try:
        port = server.server_address[1]
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics").read().decode()
        assert "lcars_ha_up 0" in body
    finally:
        server.shutdown()


def test_known_counters_start_at_zero():
    text = Metrics().render()
    assert 'lcars_taps_total{woke="true"} 0' in text
    assert 'lcars_unlock_attempts_total{result="denied"} 0' in text
    assert 'lcars_relocks_total{reason="button"} 0' in text
    assert 'lcars_commands_total{action="set_hvac_mode"} 0' in text
