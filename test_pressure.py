from unittest.mock import patch

import helpers


def test_browser_pressure_is_quiet_and_reports_warn():
    tabs = [{"targetId": str(i), "url": f"https://example.com/{i}", "title": ""} for i in range(13)]
    with patch("helpers.list_tabs", return_value=tabs), \
         patch("helpers.current_tab", return_value={"url": "https://example.com/0"}), \
         patch("helpers._browser_process_stats", return_value={"chrome_processes": 4, "rss_mb": 900}):
        pressure = helpers.browser_pressure()

    assert pressure["tabs"] == 13
    assert pressure["real_tabs"] == 13
    assert pressure["pressure"] == "warn"
    assert pressure["suggestion"] == "reuse_tab"


def test_reuse_or_new_tab_reuses_same_host():
    tabs = [{"targetId": "abc", "url": "https://example.com/old", "title": ""}]
    with patch("helpers.list_tabs", return_value=tabs), \
         patch("helpers.switch_tab") as switch_tab, \
         patch("helpers.goto_url") as goto_url, \
         patch("helpers.new_tab") as new_tab:
        target_id = helpers.reuse_or_new_tab("https://example.com/new")

    assert target_id == "abc"
    switch_tab.assert_called_once_with("abc")
    goto_url.assert_called_once_with("https://example.com/new")
    new_tab.assert_not_called()


def test_reuse_or_new_tab_reuses_current_when_tab_limit_hit():
    tabs = [{"targetId": str(i), "url": f"https://site{i}.test", "title": ""} for i in range(15)]
    with patch("helpers.list_tabs", return_value=tabs), \
         patch("helpers.current_tab", return_value={"targetId": "cur", "url": "https://current.test"}), \
         patch("helpers.goto_url") as goto_url, \
         patch("helpers.new_tab") as new_tab:
        target_id = helpers.reuse_or_new_tab("https://fresh.test", reuse_host=False, max_tabs=15)

    assert target_id == "cur"
    goto_url.assert_called_once_with("https://fresh.test")
    new_tab.assert_not_called()


def test_close_harness_tabs_closes_only_technical_tabs():
    tabs = [
        {"targetId": "keep", "url": "https://work.test", "title": ""},
        {"targetId": "blank", "url": "about:blank", "title": ""},
        {"targetId": "inspect", "url": "chrome://inspect/#devices", "title": ""},
        {"targetId": "user", "url": "https://example.com", "title": ""},
    ]
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("helpers.current_tab", return_value={"targetId": "keep"}), \
         patch("helpers.list_tabs", return_value=tabs), \
         patch("helpers.cdp", side_effect=fake_cdp):
        closed = helpers.close_harness_tabs()

    assert [t["targetId"] for t in closed] == ["blank", "inspect"]
    assert calls == [
        ("Target.closeTarget", {"targetId": "blank"}),
        ("Target.closeTarget", {"targetId": "inspect"}),
    ]
