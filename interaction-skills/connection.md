# Connection & Tab Visibility

## The omnibox popup problem

When Chrome opens fresh, the only CDP `type: "page"` targets are `chrome://inspect` and `chrome://omnibox-popup.top-chrome/` (a 1px invisible viewport). If the daemon attaches to the omnibox popup, all subsequent work — including `new_tab()` and `goto_url()` — happens on tabs that exist in CDP but may not be visible in the Chrome UI.

The daemon's `attach_first_page()` handles this by creating an `about:blank` tab when no real pages exist. If you still end up on an invisible tab, use `switch_tab()` which calls `Target.activateTarget` to bring the tab to front.

## Startup sequence

1. Check if a daemon is already running with `daemon_alive()`
2. If stale sockets exist but daemon is dead, clean them up
3. List open tabs with `list_tabs()` to see what's available
4. `ensure_real_tab()` attaches to a real page
5. `switch_tab(target_id)` both attaches AND activates (brings to front)

```python
if not daemon_alive():
    import os
    for f in ["/tmp/bu-default.sock", "/tmp/bu-default.pid"]:
        if os.path.exists(f): os.unlink(f)
    ensure_daemon()

tabs = list_tabs()
for t in tabs:
    print(t["url"][:60])

tab = ensure_real_tab()
```

## Chrome for Testing fallback

If the user's regular Chrome/Edge is closed, refuses `chrome://inspect` remote debugging, or never creates `DevToolsActivePort`, use an isolated Chrome for Testing install instead of repeatedly opening inspect tabs.

On Windows, launch it with an explicit CDP port and a separate profile:

```powershell
Start-Process 'C:\Tools\ChromeForTesting\chrome-win64\chrome.exe' -ArgumentList @(
  '--remote-debugging-port=9222',
  '--user-data-dir=C:\Tools\ChromeForTesting\UserData',
  '--disable-infobars',
  '--disable-notifications',
  '--deny-permission-prompts',
  '--disable-popup-blocking',
  '--disable-search-engine-choice-screen',
  '--disable-save-password-bubble',
  '--disable-translate',
  '--disable-features=AutofillServerCommunication,ChromeWhatsNewUI,MediaRouter,OptimizationHints,PasswordManagerOnboarding,PrivacySandboxSettings4,SigninIntercept,Translate',
  '--no-first-run',
  '--no-default-browser-check',
  'about:blank'
)
```

`--disable-infobars` removes the Chrome for Testing banner that says the browser is intended for automated testing. For a quieter local agent profile, also pre-seed `UserData\Default\Preferences` to block notifications, geolocation, microphone/camera prompts, clipboard prompts, password manager bubbles, autofill, translate, sign-in nudges, and default-browser checks. Keep this local hardening separate from remote stealth/anti-bot behavior; it is for reducing browser UI noise, not bypassing CAPTCHA/2FA. After launch, verify CDP before running the harness:

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

The daemon probes `BU_CDP_PORT` (default `9222`) before falling back to `DevToolsActivePort`, so this launch shape lets `browser-harness` attach without requiring the `chrome://inspect` permission flow.

## Bringing Chrome to front

If Chrome is behind other windows or on another desktop:

```python
import subprocess
subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'])
```

## Navigating

Prefer navigating an existing tab over `new_tab()`. Tabs created via CDP's `Target.createTarget` are visible but may open behind the active tab.

```python
tab = ensure_real_tab()
goto_url("https://example.com")
```
