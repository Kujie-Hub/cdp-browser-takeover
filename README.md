# cdp-browser-takeover

让 AI 真正接管你本机的 Chrome —— 不是告诉你点哪里，而是自己动手点。

通过 Chrome DevTools Protocol (CDP) 直连浏览器，在一个**独立的、已登录的**浏览器实例里操作网页：读页面、点按钮、输入中文、发布内容。主浏览器不受影响，登录态跨进程持久保存。

> 这是一个 [Hermes Agent](https://hermes-agent.nousresearch.com/docs) 风格的 skill，也可以当作普通的 Python 工具库直接用。

## 为什么需要它

大多数 AI 只能聊，不能动。让它去网页上帮你点一下，它会说「我没有手」。

浏览器自动化常见的坑是**登录墙**：验证码、二步验证，机器根本过不去。这个方案的思路是——**登录交给人，操作交给机器**。你手动登录一次，登录态存在专用 profile 目录里，之后关窗口、关进程都不会丢，Agent 随时接管。

## 特性

- **保留登录态**：专用 Chrome profile，登录一次长期复用
- **不碰主浏览器**：独立实例，你的账号、书签、插件互不干扰
- **纯 DOM 驱动**：全程读页面文本，不截图、不走视觉模型，没有视觉能力的模型也能跑
- **可验证可见性**：用未登录的隐身上下文回看自己发布的内容，检测影子封禁（ghost ban）

## 快速开始

```bash
pip install websocket-client
```

```python
import sys
sys.path.insert(0, "./scripts")
from cdp import CDP

c = CDP(match="example.com")      # 按 URL 子串选择标签页
c.goto("https://example.com", wait=5)
print(c.ev("document.title"))

# 输入中文（先 focus，再用 Input.insertText，React 受控组件也能收到）
c.ev("document.querySelector('input[name=q]').focus()")
c.type_text("你好世界")

# 真实鼠标事件点击（比 el.click() 兼容性好）
c.real_click("document.querySelector('button[type=submit]')")

c.close()
```

启动 / 复用专用浏览器：

```bash
python scripts/start_agent_chrome.py            # 启动
python scripts/start_agent_chrome.py --close    # 关闭
```

## 兼容性与限制

| 项 | 支持情况 |
|---|---|
| 浏览器 | 仅 Chromium 系（Chrome / Edge / Brave / Chromium）。Firefox、Safari 不兼容 |
| Chrome 版本 | 136+ 禁止在默认 user-data-dir 上开调试端口 —— 必须用独立 profile（本项目已处理） |
| 操作系统 | 脚本为 Windows 编写；macOS / Linux 需改 chrome 路径、去掉 `creationflags`、改用 `start_new_session=True` |
| AI 模型 | 不挑。全程读 DOM 文本，视觉能力为 0 也能跑 |
| 必须人工 | 首次登录密码、短信/邮箱验证码、reCAPTCHA / 滑块（**不做**，违反规则） |

## 坑（都是踩出来的）

1. **Chrome 已有实例时，再带 `--remote-debugging-port` 启动无效** —— 参数会被转发给老实例，进程秒退，端口永不开。必须用独立 `--user-data-dir`。
2. **同名按钮常有多个，其中一个是 `0×0` 隐藏的**。选元素必须过滤可见性，否则点到隐藏按钮，坐标 `(0,0)`。
3. **`document.cookie.includes('auth_token')` 恒为 false** —— auth_token 是 httpOnly。用页面文本判断登录状态。
4. **`/json/new` 必须用 PUT**，GET 返回 `405`。
5. **浏览器自动化框架的 daemon 常不认外部 CDP 端点**，要接管自己启动的 Chrome，得自己连 websocket。

## 检测影子封禁

发布内容后，想知道「别人能不能看见」——用未登录的独立浏览器上下文回看：

```python
ver = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/version"))
bws = websocket.create_connection(ver["webSocketDebuggerUrl"])
ctx = bsend("Target.createBrowserContext")["browserContextId"]   # 无 cookie 的隐身上下文
tid = bsend("Target.createTarget", url=post_url, browserContextId=ctx)["targetId"]
# 从 /json/list 取该 target 的 webSocketDebuggerUrl，读 document.body.innerText
```

未登录视图里能看到 = 正常；只有你自己登录后能看见 = 影子封禁。完整实现见 `SKILL.md`。

## 安全边界

- 主号操作**先发 1-2 条**验证可见性，再继续
- 内容**逐条手写不同**，别用模板；同账号 48 小时内不超过 3-5 条
- 遇到登录墙**停下问用户**，绝不猜密码
- 密码不要写入任何文件或日志

各平台对自动化的容忍度不同。X 相对宽松，**抖音、小红书的设备指纹与行为检测严得多，用自动化操作主号被封只是时间问题** —— 务必先用小号验证。

## License

MIT
