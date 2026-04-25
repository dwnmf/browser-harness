from unittest.mock import patch
import helpers


def _capture_cdp():
    captured = []
    def fake_cdp(method, **kwargs):
        captured.append((method, kwargs))
        return {"result": {"value": None}}
    return fake_cdp, captured


def _evaluated_expression(captured):
    return next(kw["expression"] for m, kw in captured if m == "Runtime.evaluate")


def test_simple_expression_passes_through():
    fake_cdp, captured = _capture_cdp()
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.js("document.title")
    assert _evaluated_expression(captured) == "document.title"


def test_return_statement_gets_wrapped():
    fake_cdp, captured = _capture_cdp()
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.js("const x = 1; return x")
    assert _evaluated_expression(captured) == "(function(){const x = 1; return x})()"


def test_iife_with_internal_return_is_not_double_wrapped():
    fake_cdp, captured = _capture_cdp()
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.js("(function(){ return document.title; })()")
    assert _evaluated_expression(captured) == "(function(){ return document.title; })()"


def test_positional_args_are_js_arguments():
    fake_cdp, captured = _capture_cdp()
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.js("const email = arguments[0]; return email", "a@example.com")
    assert _evaluated_expression(captured) == '(function(){const email = arguments[0]; return email}).apply(null, ["a@example.com"])'


def test_target_id_is_keyword_only():
    captured = []
    def fake_cdp(method, **kwargs):
        captured.append((method, kwargs))
        if method == "Target.attachToTarget":
            return {"sessionId": "SESSION123"}
        return {"result": {"value": None}}
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.js("document.title", target_id="TARGET123")
    assert captured[0] == ("Target.attachToTarget", {"targetId": "TARGET123", "flatten": True})
