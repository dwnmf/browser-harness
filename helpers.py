"""Browser control via CDP. Read, edit, extend -- this file is yours."""
import base64, csv, io, json, os, platform, socket, subprocess, time, urllib.request
from pathlib import Path
from urllib.parse import urlparse


def _load_env():
    p = Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

NAME = os.environ.get("BU_NAME", "default")
SUPPORTS_UNIX = hasattr(socket, "AF_UNIX")
SOCK = f"/tmp/bu-{NAME}.sock"
HOST = "127.0.0.1"
PORT = int(os.environ.get("BU_PORT", 39300 + (sum(ord(c) for c in NAME) % 1000)))
INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "chrome-extension://", "about:")


def _send(req):
    if SUPPORTS_UNIX:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCK)
    else:
        s = socket.create_connection((HOST, PORT), timeout=5)
        s.settimeout(None)
    s.sendall((json.dumps(req) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(1 << 20)
        if not chunk: break
        data += chunk
    s.close()
    r = json.loads(data)
    if "error" in r: raise RuntimeError(r["error"])
    return r


def cdp(method, session_id=None, **params):
    """Raw CDP. cdp('Page.navigate', url='...'), cdp('DOM.getDocument', depth=-1)."""
    return _send({"method": method, "params": params, "session_id": session_id}).get("result", {})


def drain_events():  return _send({"meta": "drain_events"})["events"]
def current_session(): return _send({"meta": "session"})["session_id"]
def use_session(session_id):
    """Switch the default CDP session. Useful after manually attaching to a target."""
    return _send({"meta": "set_session", "session_id": session_id})["session_id"]


# --- navigation / page ---
def goto_url(url):
    r = cdp("Page.navigate", url=url)
    d = (Path(__file__).parent / "domain-skills" / (urlparse(url).hostname or "").removeprefix("www.").split(".")[0])
    return {**r, "domain_skills": sorted(p.name for p in d.rglob("*.md"))[:10]} if d.is_dir() else r

def page_info():
    """{url, title, w, h, sx, sy, pw, ph} — viewport + scroll + page size.

    If a native dialog (alert/confirm/prompt/beforeunload) is open, returns
    {dialog: {type, message, ...}} instead — the page's JS thread is frozen
    until the dialog is handled (see interaction-skills/dialogs.md)."""
    dialog = _send({"meta": "pending_dialog"}).get("dialog")
    if dialog:
        return {"dialog": dialog}
    r = cdp("Runtime.evaluate",
            expression="JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY,pw:document.documentElement.scrollWidth,ph:document.documentElement.scrollHeight})",
            returnByValue=True)
    return json.loads(r["result"]["value"])

def page_text(separator=" ", max_chars=None):
    """Visible page text, normalized for quick research/scraping passes."""
    text = js("return document.body ? document.body.innerText : ''") or ""
    text = separator.join(text.split())
    return text[:max_chars] if max_chars else text

def page_links(limit=50):
    """Visible links from the current page: [{text, href}, ...]."""
    links = js("""
return Array.from(document.querySelectorAll('a'))
  .map(a => ({text: (a.innerText || a.textContent || '').trim(), href: a.href}))
  .filter(x => x.text && x.href)
""") or []
    return links[:limit]

def snippets(needles, context=350, limit=10):
    """Find text snippets around one or more needles in the current page."""
    if isinstance(needles, str):
        needles = [needles]
    text = page_text()
    low = text.lower()
    out = []
    for needle in needles:
        n = needle.lower()
        start = 0
        while len(out) < limit:
            idx = low.find(n, start)
            if idx < 0:
                break
            out.append(text[max(0, idx - context):idx + len(needle) + context])
            start = idx + len(needle)
    return out

def print_json(value):
    """Pretty-print data without escaping non-ASCII text."""
    print(json.dumps(value, ensure_ascii=False, indent=2))

# --- input ---
_debug_click_counter = 0

def click_at_xy(x, y, button="left", clicks=1):
    if os.environ.get("BH_DEBUG_CLICKS"):
        global _debug_click_counter
        try:
            from PIL import Image, ImageDraw
            dpr = js("window.devicePixelRatio") or 1
            path = capture_screenshot(f"/tmp/debug_click_{_debug_click_counter}.png")
            img = Image.open(path)
            draw = ImageDraw.Draw(img)
            px, py = int(x * dpr), int(y * dpr)
            r = int(15 * dpr)
            draw.ellipse([px - r, py - r, px + r, py + r], outline="red", width=int(3 * dpr))
            draw.line([px - r - int(5 * dpr), py, px + r + int(5 * dpr), py], fill="red", width=int(2 * dpr))
            draw.line([px, py - r - int(5 * dpr), px, py + r + int(5 * dpr)], fill="red", width=int(2 * dpr))
            img.save(path)
            print(f"[debug_click] saved {path} (x={x}, y={y}, dpr={dpr})")
        except Exception as e:
            print(f"[debug_click] overlay failed: {e}")
        _debug_click_counter += 1
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=clicks)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=clicks)

def type_text(text):
    cdp("Input.insertText", text=text)

_KEYS = {  # key → (windowsVirtualKeyCode, code, text)
    "Enter": (13, "Enter", "\r"), "Tab": (9, "Tab", "\t"), "Backspace": (8, "Backspace", ""),
    "Escape": (27, "Escape", ""), "Delete": (46, "Delete", ""), " ": (32, "Space", " "),
    "ArrowLeft": (37, "ArrowLeft", ""), "ArrowUp": (38, "ArrowUp", ""),
    "ArrowRight": (39, "ArrowRight", ""), "ArrowDown": (40, "ArrowDown", ""),
    "Home": (36, "Home", ""), "End": (35, "End", ""),
    "PageUp": (33, "PageUp", ""), "PageDown": (34, "PageDown", ""),
}
def press_key(key, modifiers=0):
    """Modifiers bitfield: 1=Alt, 2=Ctrl, 4=Meta(Cmd), 8=Shift.
    Special keys (Enter, Tab, Arrow*, Backspace, etc.) carry their virtual key codes
    so listeners checking e.keyCode / e.key all fire."""
    vk, code, text = _KEYS.get(key, (ord(key[0]) if len(key) == 1 else 0, key, key if len(key) == 1 else ""))
    base = {"key": key, "code": code, "modifiers": modifiers, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    cdp("Input.dispatchKeyEvent", type="keyDown", **base, **({"text": text} if text else {}))
    if text and len(text) == 1:
        cdp("Input.dispatchKeyEvent", type="char", text=text, **{k: v for k, v in base.items() if k != "text"})
    cdp("Input.dispatchKeyEvent", type="keyUp", **base)

def scroll(x, y, dy=-300, dx=0):
    cdp("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)


# --- visual ---
def capture_screenshot(path="/tmp/shot.png", full=False):
    r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=full)
    open(path, "wb").write(base64.b64decode(r["data"]))
    return path


# --- tabs ---
def list_tabs(include_chrome=True):
    out = []
    for t in cdp("Target.getTargets")["targetInfos"]:
        if t["type"] != "page": continue
        url = t.get("url", "")
        if not include_chrome and url.startswith(INTERNAL): continue
        out.append({"targetId": t["targetId"], "title": t.get("title", ""), "url": url})
    return out

def _browser_process_stats():
    """Best-effort local Chrome/Edge process count and RSS in MB."""
    names = ("chrome.exe", "msedge.exe") if platform.system() == "Windows" else ("Google Chrome", "chrome", "chromium", "msedge")
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["tasklist", "/FO", "CSV"], text=True, timeout=5)
            rows = csv.DictReader(io.StringIO(out))
            count, rss_kb = 0, 0
            for row in rows:
                image = (row.get("Image Name") or "").lower()
                if image not in names:
                    continue
                count += 1
                mem = (row.get("Mem Usage") or "0").replace("\xa0", " ").replace(",", "")
                digits = "".join(ch for ch in mem if ch.isdigit())
                rss_kb += int(digits or "0")
            return {"chrome_processes": count, "rss_mb": round(rss_kb / 1024)}
        out = subprocess.check_output(["ps", "-A", "-o", "comm=,rss="], text=True, timeout=5)
        count, rss_kb = 0, 0
        for line in out.splitlines():
            parts = line.rsplit(None, 1)
            if len(parts) != 2:
                continue
            comm, rss = parts
            if not any(name.lower() in comm.lower() for name in names):
                continue
            count += 1
            rss_kb += int(rss)
        return {"chrome_processes": count, "rss_mb": round(rss_kb / 1024)}
    except Exception:
        return {"chrome_processes": None, "rss_mb": None}

def browser_pressure(tab_warn=12, tab_critical=25, rss_warn_mb=1500, rss_critical_mb=3000):
    """Quiet browser pressure check. Returns data; prints nothing and closes nothing."""
    tabs = list_tabs(include_chrome=True)
    real_tabs = [t for t in tabs if not t.get("url", "").startswith(INTERNAL)]
    internal_tabs = len(tabs) - len(real_tabs)
    stats = _browser_process_stats()
    tab_count = len(tabs)
    rss_mb = stats["rss_mb"]
    pressure = "ok"
    if tab_count >= tab_critical or (rss_mb is not None and rss_mb >= rss_critical_mb):
        pressure = "critical"
    elif tab_count >= tab_warn or (rss_mb is not None and rss_mb >= rss_warn_mb):
        pressure = "warn"
    suggestion = None
    if pressure == "critical":
        suggestion = "reuse_tab_or_close_harness_tabs"
    elif pressure == "warn":
        suggestion = "reuse_tab"
    cur = current_tab()
    return {
        "tabs": tab_count,
        "real_tabs": len(real_tabs),
        "internal_tabs": internal_tabs,
        "chrome_processes": stats["chrome_processes"],
        "rss_mb": rss_mb,
        "active_tab_url": cur.get("url", ""),
        "pressure": pressure,
        "suggestion": suggestion,
    }

tab_pressure = browser_pressure

def _same_host(a, b):
    try:
        return (urlparse(a).hostname or "").removeprefix("www.") == (urlparse(b).hostname or "").removeprefix("www.")
    except Exception:
        return False

def reuse_or_new_tab(url="about:blank", reuse_host=True, max_tabs=15):
    """Open `url`, preferring an existing tab before creating more browser pressure.

    Reuse order: exact URL, same host when `reuse_host` is true, then the current
    real tab once `max_tabs` is reached. Returns the target id in all cases.
    """
    tabs = list_tabs(include_chrome=False)
    for t in tabs:
        if t.get("url") == url:
            switch_tab(t["targetId"])
            return t["targetId"]
    if url != "about:blank" and reuse_host:
        for t in tabs:
            if _same_host(t.get("url", ""), url):
                switch_tab(t["targetId"])
                goto_url(url)
                return t["targetId"]
    if len(list_tabs(include_chrome=True)) >= max_tabs and url != "about:blank":
        try:
            cur = current_tab()
            if cur.get("targetId") and cur.get("url") and not cur["url"].startswith(INTERNAL):
                goto_url(url)
                return cur["targetId"]
        except Exception:
            pass
        if tabs:
            switch_tab(tabs[0]["targetId"])
            goto_url(url)
            return tabs[0]["targetId"]
    return new_tab(url)

open_or_reuse_tab = reuse_or_new_tab

def close_harness_tabs(keep_current=True, close_blank=True, close_inspect=True, close_duplicate_urls=False):
    """Close clearly technical harness tabs. Does not close arbitrary user pages."""
    current_id = None
    if keep_current:
        try:
            current_id = current_tab().get("targetId")
        except Exception:
            current_id = None
    seen_urls = set()
    closed = []
    for t in list_tabs(include_chrome=True):
        tid, url = t.get("targetId"), t.get("url", "")
        if keep_current and tid == current_id:
            seen_urls.add(url)
            continue
        technical = (
            (close_blank and url == "about:blank") or
            (close_inspect and url.startswith("chrome://inspect")) or
            (close_duplicate_urls and url and url in seen_urls and not url.startswith(INTERNAL))
        )
        if not technical:
            seen_urls.add(url)
            continue
        try:
            cdp("Target.closeTarget", targetId=tid)
            closed.append(t)
        except Exception:
            pass
        seen_urls.add(url)
    return closed

def current_tab():
    try:
        info = page_info()
        url = info.get("url")
        title = info.get("title", "").removeprefix("\U0001F7E2 ")
        for t in list_tabs(include_chrome=True):
            if url and t.get("url") == url:
                return t
            if title and t.get("title", "").removeprefix("\U0001F7E2 ") == title:
                return t
    except Exception:
        pass
    t = cdp("Target.getTargetInfo").get("targetInfo", {})
    return {"targetId": t.get("targetId"), "url": t.get("url", ""), "title": t.get("title", "")}

def attach_target(target_id, activate=True):
    """Attach to any CDP target and make it the default session."""
    if activate:
        try: cdp("Target.activateTarget", targetId=target_id)
        except Exception: pass
    sid = cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"]
    return use_session(sid)

def browser_state(include_chrome=False, events=10):
    """Compact state dump for debugging target/session/page issues."""
    ev = drain_events()
    return {
        "session_id": current_session(),
        "current_tab": current_tab(),
        "page_info": page_info(),
        "tabs": list_tabs(include_chrome=include_chrome),
        "events": ev[-events:],
    }

def _mark_tab():
    """Prepend 🟢 to tab title so the user can see which tab the agent controls."""
    try: cdp("Runtime.evaluate", expression="if(!document.title.startsWith('\U0001F7E2'))document.title='\U0001F7E2 '+document.title")
    except Exception: pass

def switch_tab(target_id):
    # Unmark old tab
    try: cdp("Runtime.evaluate", expression="if(document.title.startsWith('\U0001F7E2 '))document.title=document.title.slice(2)")
    except Exception: pass
    cdp("Target.activateTarget", targetId=target_id)
    sid = cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"]
    _send({"meta": "set_session", "session_id": sid})
    _mark_tab()
    return sid

def new_tab(url="about:blank"):
    # Always create blank, then goto: passing url to createTarget races with
    # attach, so the brief about:blank is "complete" by the time the caller
    # polls and wait_for_load() returns before navigation actually starts.
    tid = cdp("Target.createTarget", url="about:blank")["targetId"]
    switch_tab(tid)
    if url != "about:blank":
        goto_url(url)
    return tid

def ensure_real_tab():
    """Switch to a real user tab if current is chrome:// / internal / stale."""
    tabs = list_tabs(include_chrome=False)
    if not tabs:
        return None
    try:
        cur = current_tab()
        if cur["url"] and not cur["url"].startswith(INTERNAL):
            return cur
    except Exception:
        pass
    switch_tab(tabs[0]["targetId"])
    return tabs[0]

def iframe_target(url_substr):
    """First iframe target whose URL contains `url_substr`. Use with js(..., target_id=...)."""
    for t in cdp("Target.getTargets")["targetInfos"]:
        if t["type"] == "iframe" and url_substr in t.get("url", ""):
            return t["targetId"]
    return None


# --- utility ---
def wait(seconds=1.0):
    time.sleep(seconds)

def wait_for_load(timeout=15.0):
    """Poll document.readyState == 'complete' or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js("document.readyState") == "complete": return True
        time.sleep(0.3)
    return False

def js(expression, *args, target_id=None):
    """Run JS in the attached tab (default) or inside an iframe target (via iframe_target()).

    Expressions with top-level `return` are automatically wrapped in an IIFE, so both
    `document.title` and `const x = 1; return x` are valid inputs. Positional
    Python args are exposed as JS `arguments`; pass iframe targets as
    `target_id=...` so data is not mistaken for a CDP target id.
    """
    sid = cdp("Target.attachToTarget", targetId=target_id, flatten=True)["sessionId"] if target_id else None
    if args:
        expression = f"(function(){{{expression}}}).apply(null, {json.dumps(args)})"
    elif "return " in expression and not expression.strip().startswith("("):
        expression = f"(function(){{{expression}}})()"
    r = cdp("Runtime.evaluate", session_id=sid, expression=expression, returnByValue=True, awaitPromise=True)
    return r.get("result", {}).get("value")


_KC = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, " ": 32, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40}


def dispatch_key(selector, key="Enter", event="keypress"):
    """Dispatch a DOM KeyboardEvent on the matched element.

    Use this when a site reacts to synthetic DOM key events on an element more reliably
    than to raw CDP input events.
    """
    kc = _KC.get(key, ord(key) if len(key) == 1 else 0)
    js(
        f"(()=>{{const e=document.querySelector({json.dumps(selector)});if(e){{e.focus();e.dispatchEvent(new KeyboardEvent({json.dumps(event)},{{key:{json.dumps(key)},code:{json.dumps(key)},keyCode:{kc},which:{kc},bubbles:true}}));}}}})()"
    )

def upload_file(selector, path):
    """Set files on a file input via CDP DOM.setFileInputFiles. `path` is an absolute filepath (use tempfile.mkstemp if needed)."""
    doc = cdp("DOM.getDocument", depth=-1)
    nid = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)["nodeId"]
    if not nid: raise RuntimeError(f"no element for {selector}")
    cdp("DOM.setFileInputFiles", files=[path] if isinstance(path, str) else list(path), nodeId=nid)

def http_get(url, headers=None, timeout=20.0):
    """Pure HTTP — no browser. Use for static pages / APIs. Wrap in ThreadPoolExecutor for bulk.

    When BROWSER_USE_API_KEY is set, routes through the fetch-use proxy (handles bot
    detection, residential proxies, retries). Falls back to local urllib otherwise."""
    if os.environ.get("BROWSER_USE_API_KEY"):
        try:
            from fetch_use import fetch_sync
            return fetch_sync(url, headers=headers, timeout_ms=int(timeout * 1000)).text
        except ImportError:
            pass
    import gzip
    h = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"}
    if headers: h.update(headers)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip": data = gzip.decompress(data)
        return data.decode()
