"""启动 / 复用专用 Chrome（保留登录态）。

    python start_agent_chrome.py

幂等：端口已开则什么都不做。登录 cookie 存在 PROF 目录，关窗口关进程都不丢。
改成你机器上的路径即可（Windows 用 %LOCALAPPDATA% 下的 profile 也行）。
"""
import os
import socket
import subprocess
import sys
import time

PROF = os.path.expandvars(r"%USERPROFILE%\.local\hermes\chrome-agent")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222


def port_up(port=PORT):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.close()
        return True
    except Exception:
        return False


def ensure(open_url="about:blank"):
    if port_up():
        print("9222 已就绪（复用现有实例）")
        return True

    if not os.path.exists(CHROME):
        alt = [
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        found = next((p for p in alt if os.path.exists(p)), None)
        if not found:
            raise SystemExit("找不到 chrome.exe，请修改 CHROME 路径")
        chrome = found
    else:
        chrome = CHROME

    os.makedirs(PROF, exist_ok=True)
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：父进程退出后 Chrome 继续活着
    subprocess.Popen(
        [
            chrome,
            "--user-data-dir=" + PROF,
            "--remote-debugging-port=%d" % PORT,
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1440,920",
            open_url,
        ],
        close_fds=True,
        creationflags=0x00000008 | 0x00000200,
    )

    for _ in range(40):
        if port_up():
            print("Chrome 启动完成，9222 就绪")
            return True
        time.sleep(0.5)
    print("启动超时：端口未开放")
    return False


def close_all():
    """优雅关闭这个 profile 的浏览器（只关自己，不碰用户主浏览器）。"""
    import json
    import urllib.request
    import websocket

    ver = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/version" % PORT, timeout=5))
    ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=20)
    ws.send(json.dumps({"id": 1, "method": "Browser.close", "params": {}}))
    time.sleep(3)
    print("已关闭，端口:", port_up())


if __name__ == "__main__":
    if "--close" in sys.argv:
        close_all()
    else:
        url = next((a for a in sys.argv[1:] if a.startswith("http")), "about:blank")
        sys.exit(0 if ensure(url) else 1)
