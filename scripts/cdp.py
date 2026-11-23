"""极简 CDP 客户端：直连本机 Chrome 调试端口（默认 9222）。

用法:
    from cdp import CDP
    c = CDP(match="x.com")          # 按 URL 子串选标签页；无匹配则取第一个
    c.ev("location.href")
    c.goto("https://x.com/home", wait=6)
    c.real_click("document.querySelector('button[type=submit]')")
    c.ev("document.querySelector('input[name=q]').focus()")
    c.type_text("中文内容")
    c.shot("E:/tmp/a.png")
    c.close()

注意: cdp.py 本身只依赖 websocket-client（pip install websocket-client）。
"""
import json
import time
import urllib.request

import websocket

PORT = 9222


def _http(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), method=method)
    return json.load(urllib.request.urlopen(req, timeout=10))


def list_tabs():
    return _http("/json/list")


def new_tab(url):
    """开新标签页。必须用 PUT，GET 会 405。"""
    req = urllib.request.Request("http://127.0.0.1:%d/json/new?%s" % (PORT, url), method="PUT")
    return json.load(urllib.request.urlopen(req, timeout=10))


class CDP:
    def __init__(self, match="", tab_id=None):
        tabs = [t for t in list_tabs() if t.get("type") == "page"]
        target = None
        if tab_id:
            target = next((t for t in tabs if t.get("id") == tab_id), None)
        if target is None and match:
            target = next((t for t in tabs if match in (t.get("url") or "")), None)
        if target is None:
            target = tabs[0]
        self.url = target.get("url")
        self.id = target.get("id")
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=60, max_size=20 * 1024 * 1024
        )
        self._n = 0

    def send(self, method, **params):
        self._n += 1
        self.ws.send(json.dumps({"id": self._n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._n:
                if "error" in msg:
                    raise RuntimeError(method + " -> " + str(msg["error"]))
                return msg.get("result", {})

    def ev(self, expr, await_promise=False):
        r = self.send(
            "Runtime.evaluate",
            expression=expr,
            returnByValue=True,
            awaitPromise=await_promise,
            userGesture=True,
        )
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:500])
        return r.get("result", {}).get("value")

    def goto(self, url, wait=3):
        self.send("Page.enable")
        self.send("Page.navigate", url=url)
        time.sleep(wait)

    def real_click(self, selector_js):
        """selector_js 是返回 element 的 JS 表达式。用真实鼠标事件点击。"""
        box = self.ev(
            "(() => { const el = " + selector_js + "; if(!el) return null;"
            " el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect();"
            " return {x: r.x + r.width/2, y: r.y + r.height/2}; })()"
        )
        if not box:
            return "NOT_FOUND"
        x, y = box["x"], box["y"]
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.send(
                "Input.dispatchMouseEvent",
                type=t, x=x, y=y, button="left", clickCount=1, buttons=1,
            )
            time.sleep(0.06)
        return "OK %.0f,%.0f" % (x, y)

    def type_text(self, text):
        """插入文本到当前焦点元素（React 受控组件也能收到）。先 focus 目标元素。"""
        self.send("Input.insertText", text=text)

    def press_enter(self):
        for t in ("keyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", type=t, key="Enter",
                      windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)

    def shot(self, path):
        import base64
        r = self.send("Page.captureScreenshot", format="png")
        open(path, "wb").write(base64.b64decode(r["data"]))
        return path

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
