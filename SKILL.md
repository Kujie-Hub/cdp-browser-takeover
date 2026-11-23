---
name: cdp-browser-takeover
description: Use when 要接管本机 Chrome 操作站点（X/抖音/B站）。
version: 1.0.0
author: Hermes
license: MIT
metadata:
  hermes:
    tags: [browser, cdp, automation, x, douyin, xiaohongshu]
    related_skills: [inspecting-hermes-desktop-dom, dogfood]
---

# CDP 浏览器接管

用专用 Chrome profile + 远程调试端口，直接走 CDP 协议驱动页面。**不依赖 browser_exec 的 daemon**，不受其「必须预先有调试端口」的限制。

## When to Use（何时用）

- 需要在已登录状态下操作站点（发帖、评论、上传、抓取后台数据）
- 需要绕过登录墙但**不想碰用户主浏览器**
- 需要验证「别人能不能看见」（影子封禁、限流）——这是 CDP 独有的杀手功能
- GUI 自动化（键鼠模拟）不靠谱时的替代方案

## 核心步骤

### 1. 启动专用 Chrome（一次性，之后复用登录态）

```python
import subprocess, socket, time
PROF = r"C:\Users\<user>\.local\hermes\chrome-agent"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

if not port_up(9222):
    subprocess.Popen([CHROME, f"--user-data-dir={PROF}",
                      "--remote-debugging-port=9222", "--remote-allow-origins=*",
                      "--no-first-run", "--no-default-browser-check",
                      "--window-size=1440,920", "about:blank"],
                     close_fds=True, creationflags=0x00000008 | 0x00000200)
```

`scripts/start_agent_chrome.py` 是可直接调用的版本。

### 2. 用 CDP 类驱动

`scripts/cdp.py` 提供 `ev / goto / real_click / type_text / shot`。用法：

```python
import sys; sys.path.insert(0, r"./scripts")
from cdp import CDP
c = CDP(match="x.com")        # 按 URL 子串选标签页
c.goto("https://x.com/home", wait=6)
print(c.ev("location.href"))
c.close()
```

### 3. 开新标签页必须用 PUT

```python
req = urllib.request.Request("http://127.0.0.1:9222/json/new?" + url, method="PUT")
urllib.request.urlopen(req).read()
```

GET 会返回 `405 Method Not Allowed`。

### 4. 输入中文

先 focus 元素，再用 `Input.insertText`（不要用 JS 改 value，React 受控组件收不到）：

```python
c.ev("document.querySelector('input[name=username_or_email]').focus()")
c.type_text("中文内容")
```

### 5. 点击：优先真实鼠标事件

`real_click` 走 `Input.dispatchMouseEvent`（mouseMoved→Pressed→Released），比 `el.click()` 兼容性好。

## 关键坑（都踩过）

1. **Chrome 已有实例时，再带 `--remote-debugging-port` 启动是无效的**——参数被转发给老实例，进程秒退，端口永不开。必须用**独立 `--user-data-dir`**。不要试图 taskkill 用户的主浏览器。
2. **页面上同名按钮常有多个，其中一个是 0×0 隐藏的**。选元素必须过滤可见性：
   ```js
   [...document.querySelectorAll('button[type=submit]')].find(b => b.getBoundingClientRect().width > 0)
   ```
   点错隐藏按钮会导致坐标 `(0,0)`，还可能触发意外的「离开页面？」弹窗。
3. **`document.cookie.includes('auth_token')` 恒为 false**——auth_token 是 httpOnly。用页面文本判断登录态（如是否出现自己的用户名），别用 cookie。
4. **browser_exec 的 daemon 不认外部 `BU_CDP_URL`**——它在执行 code 之前就做了端口检查。要接管自己启动的 Chrome，必须自己连 websocket，不要走 browser_exec。
5. **Windows 上 `write_file` 工具底层走 bash，含引号的 Python 源码会炸**（`unexpected EOF`）。用 `execute_code` 里 `open(p,'w').write(src)` 直接写。
6. **`wmic` 不存在**（新 Windows 已移除）。别用它查命令行。

## 影子封禁验证（高价值）

发完内容后，用**未登录的独立浏览器上下文**打开自己的帖子/评论链接，看是否公开可见：

```python
ver = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/version"))
bws = websocket.create_connection(ver["webSocketDebuggerUrl"])   # browser 级 endpoint
ctx = bsend("Target.createBrowserContext")["browserContextId"]    # 隐身上下文，无 cookie
tid = bsend("Target.createTarget", url=post_url, browserContextId=ctx)["targetId"]
# 从 /json/list 取该 targetId 的 webSocketDebuggerUrl，读 document.body.innerText
# 最后 disposeBrowserContext 清理
```

未登录视图里能看到 = 没被影子封禁。看不到只有自己能看到 = ghost ban。

注意：`createTarget` 后要等 6-8 秒再读，X 这类 SPA 渲染慢；target 可能被浏览器提前回收，取不到就跳过并说明，**不要假报成功**。

## 站点要点

### X / Twitter
- 登录页会被改版，当前是 `x.com/i/jf/onboarding/web?mode=login`，输入框 `input[name=username_or_email]`，另有隐藏的 `input[name=password]`
- 支持「邮箱验证码登录」，比密码安全：填邮箱 → 点可见的 submit → 验证码发到邮箱 → 用户报码 → 填入
- **不要帮用户过 Google 的 reCAPTCHA**，那是反机器人验证，破解违规且会连累 Google 账号
- 发评论：`[data-testid="tweetTextarea_0"]`（contenteditable）→ insertText → `[data-testid="tweetButtonInline"]`
- 发布成功判据三合一：编辑器被清空 + 出现「已发送」toast + 出现自己新帖的 `/status/<id>` 链接

### 抖音 / 小红书 / B站
- 结构同理，重点是先用一次 `document.querySelectorAll` 枚举 input/button 摸清 DOM，再写选择器
- 这些站点对自动化更敏感，**先用小号验证**，别直接上主号

## 兼容性与限制

**浏览器**：仅 Chromium 系（Chrome / Edge / Brave / Chromium）。Firefox 走 WebDriver BiDi、Safari 走自己的协议，与本 skill 不兼容。国产套壳（360/QQ）理论可用但内核旧，常缺 CDP API。

**Chrome 版本**：136+ 起禁止在**默认** user-data-dir 上开远程调试端口 —— 这正是必须用独立 profile 目录的原因之一。已在 Chrome 157 实测通过。

**操作系统**：`scripts/start_agent_chrome.py` 为 Windows 编写（写死 `C:\Program Files\...` + `creationflags`）。迁到 macOS/Linux 需改三处：chrome 路径、去掉 `creationflags`、改用 `start_new_session=True`。`cdp.py` 本身跨平台，无需改动。

**AI 模型**：不依赖特定模型。全程读 DOM 文本，截图与视觉模型都不需要，视觉能力为 0 的模型（如 deepseek）也能完整跑通。模型强弱只影响判断质量（评论是否像真人），不影响可操作性。纯图片内容（图形验证码、canvas 表格）除外。

**必须人工介入**：① 首次登录密码（agent 不得接触）② 邮箱/短信验证码（用户口头提供）③ reCAPTCHA / 滑块 / 点选验证（**不做**，违规且连累关联账号）④ 活体检测。

**站点风险**：Cloudflare Turnstile 等强反爬站可能直接拦截。抖音、小红书的设备指纹与行为检测远严于 X，用自动化操作主号封号只是时间问题 —— 务必先小号验证。

**会失效的部分**：站点改版后 `data-testid` / CSS 选择器会变，需重新用 `document.querySelectorAll` 枚举 DOM。X 登录页已改版过多次。

## 账号安全铁律

- 主号操作**先发 1-2 条**，验证可见性再继续
- 评论/发帖内容**逐条手写不同**，不用模板；同账号 48 小时内不超过 3-5 条
- 遇到登录墙：**停下问用户**，绝不猜密码
- 验证码可以让用户口头提供，密码不要写入任何文件或记忆
