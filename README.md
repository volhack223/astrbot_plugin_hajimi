# AstrBot Plugin Hajimi (姬咪奈)

🐾 **`astrbot_plugin_hajimi`** 是一个专为 [AstrBot](https://github.com/AstrBot-Dev/AstrBot) 设计的 **Gemini 真实浏览器拟人操作与多模态创作插件**。

ps：自己自行去整一个gemini的会员。自行去搜JIO，PIXEL，学生认证等免费会员来用，我这里就不教了。

通过 Playwright 异步自动化引擎与深度防反自动化指纹伪装（Stealth Evade）、双域根凭证持久化技术，本插件能够在无头或有头 Chromium 浏览器中直接模拟真人操作 Google Gemini 网页端，同时支持 **网页端深度文本对话问答、图片创作/改图（换脸/换头、素描、二次元、赛博朋克等）、GIF 动图、Veo 视频生成、Lyria 音乐合成、自动 LRU 缓存清理、用量限额查询** 等全部高级网页端功能！

---

## ✨ 核心功能亮点

1. **💬 文本对话与多模态创作智能双模分流**
   - **纯文本对话转发**：发送 `hajimi 对比下主流大模型的功能` 或使用显式前缀 `hajimi 对话 <问题>`，插件会自动识别为文本问答，**不触发画图指令**，并将 Gemini 网页端的完整长文回复自动分段转发到 QQ。
   - **多模态媒体创作**：发送 `hajimi 画一张流萤的JK图`、使用风格预设（如 `转动漫`、`换头`、`照片转gif`、`纯音乐`）或发送图片/`@群友`，自动调用网页端生成图片、GIF、视频或音乐并返回。
2. **🧹 本地多媒体缓存自动 LRU 清理（支持 WebUI 设置）**
   - 内置 `_conf_schema.json`，可在 **AstrBot WebUI 插件设置面板**中直接滑动调节 `media_cache` 缓存上限（默认 `300 MB`）。
   - 启动时、每次媒体生成后以及后台定时巡检时自动按修改时间从旧到新清理超出上限的媒体文件，防止长期运行占满服务器/NAS 磁盘。
3. **🤖 默认 `Gemini 4 Hydrogen` 模型与一键切换**
   - 默认使用最新的 **`gemini-hydrogen` (`Gemini 4 Hydrogen`)** 模型（已替换原 `3.8 Flash`），并支持在 `gemini-flash-lite`、`gemini-hydrogen`、`gemini-pro` 与 `gemini-argon` 之间自由切换。
4. **🛡️ 极致反指纹与永久免掉线机制**
   - **Stealth 伪装**：深度抹除 `navigator.webdriver` 痕迹，伪造真实 `chrome` 对象、High-Entropy Client Hints、WebGL 硬件指纹及动态对齐内核的 `User-Agent`，完美绕过 Google 的反爬与风控。
   - **双域根凭证克隆**：同时支持 `.google.com` 与 `accounts.google.com` 的根凭证（如 `__Host-GAPS`、`LSID` 等）持久化，彻底解决传统单 Cookie 方案 2~3 小时换票掉线痛点。
   - **后台 20 分钟智能保活**：定时在后台隐形刷新会话并落盘同步，让登录态 365 天持续有效。
5. **👥 智能群友头像融图/换脸互动**
   - 支持通过 `@群友` 自动拉取其 QQ 高清头像，与基础图像或提示词无缝融合成图。

截图示意：
<img width="126" height="280" alt="43e3b0f35e94f853c17f791b951ce315" src="https://github.com/user-attachments/assets/78ada9e3-b214-4291-b57b-fe19deabf7b6" />
<img width="126" height="280" alt="image" src="https://github.com/user-attachments/assets/b1fc270a-5ed7-4383-bb34-dcff9b9baad7" />
<img width="125" height="85" alt="image" src="https://github.com/user-attachments/assets/b42157dc-41da-483a-9afd-f149f15d9160" />
<img width="126" height="280" alt="66127bb0c04c19e36120d36d9592c15e" src="https://github.com/user-attachments/assets/4ec1c907-fd50-40be-8e51-75f776b7b989" />
<img width="126" height="310" alt="e5f55c220abd8a2ebb2ec781fb5e7d65" src="https://github.com/user-attachments/assets/92daa0a5-6b78-4c6d-90cb-bfc172c7bd9a" />

---

## 📦 环境准备与安装

在使用本插件前，请确保您的 AstrBot 运行容器（或本地环境）已安装 **Playwright 及其系统依赖项**：

```bash
pip install playwright playwright-stealth
playwright install --with-deps chromium
```

随后将本项目代码放入 AstrBot 的插件目录中（例如 `data/plugins/astrbot_plugin_hajimi`），重启 AstrBot 后即可在 WebUI **插件设置** 中调整缓存大小与默认模型。

---

## 🔐 登录配置指南（推荐双域根凭证法）

为了让插件长期稳定免登录运行，推荐使用 **【双域根凭证克隆法】**（100% 永不掉线）：

1. 在电脑浏览器中登录并打开 [Google Gemini 网页端](https://gemini.google.com/app)。
2. 按 `F12` 打开开发者工具，切换到 **Application (应用) -> Cookies**。
3. 复制 `.google.com` 域下的整串 Cookie 内容。
4. 在 AstrBot 中发送指令绑定 Gemini 凭证：
   ```text
   hajimi rawcookie <你复制的gemini域Cookie串>
   ```
5. 同时在浏览器打开 [Google 账号中心](https://accounts.google.com)，按 `F12` 复制 `accounts.google.com` 域下的 Cookie（包含 `GAPS`, `LSID` 等根凭证），发送：
   ```text
   hajimi 根凭证 <你复制的accounts域Cookie串>
   ```

*(注：插件也支持通过 `hajimi 登录` 调出网页进行交互式登录或直接修改 `hajimi_config.json` 写入 `secure_1psid` 和 `secure_1psidts`)*。

---

## 📋 指令大全

在 AstrBot 中，所有指令均以 `hajimi`（或 `/hajimi`, `!hajimi`）开头：

### 1. 基础、缓存与菜单
* `hajimi` 或 `hajimi 菜单`：查看当前插件状态、缓存占用、可用模型及全量预设菜单。
* `hajimi 清理缓存`：立即按设定上限清理旧媒体文件并查看剩余空间。
* `hajimi 缓存 <MB>`：（主人专用）在线修改本地媒体缓存上限，例如 `hajimi 缓存 300`。
* `hajimi 截图`：获取当前 Chromium 浏览器的实时画面及登录状态诊断。
* `hajimi reset`：开启全新的 Gemini 网页对话窗口（清空当前上下文）。
* `hajimi 额度`：点击左下角设置按钮，查询当前账号的剩余额度与周限额并截图返回。

### 2. 模型切换
* `hajimi 1` 或 `hajimi lite`：切换至 `gemini-flash-lite` (极速轻量)
* `hajimi 2` / `hajimi hydrogen` / `hajimi flash`：切换至 `gemini-hydrogen` (**默认均衡主力**)
* `hajimi 3` / `hajimi pro`：切换至 `gemini-pro` (高质量推理与创作)
* `hajimi 4` / `hajimi argon`：切换至 `gemini-argon` (长程/实验特调)

### 3. 文本对话模式（网页回复转发至 QQ）
* **自动识别纯文本提问**：`hajimi 对比下主流大模型的功能`
* **强制对话前缀**（即使锁定了常驻画图预设也能直接聊天）：`hajimi 对话 帮我写一个 Python 异步爬虫` 或 `hajimi 问 今天适合看什么电影`

### 4. 多模态创作与预设
直接发送文字或携带图片、`@群友` 即可开始创作。支持在指令前后或开头附带风格预设：
* **直接作画**：`hajimi 画一张流萤的JK图`
* **改图/换头**：`hajimi 换头 把他的头换到这张图上` （需附带原图，或 `@群友`）
* **动漫风**：`hajimi 转动漫 赛博朋克风的少女`
* **GIF 动图**：`hajimi 照片转gif 让这张图片动起来`
* **视频生成**：`hajimi 动漫风格 樱花树下的少年`
* **音乐生成**：`hajimi 纯音乐 治愈的钢琴曲`
* **常驻预设锁定**：`hajimi 预设 赛博` （之后创作均自动套用赛博朋克风，发送 `hajimi 预设 取消` 恢复智能自动识别）。
* **历史作品重发**：`hajimi 发送` 或 `hajimi 发送 gif`（提取当前网页对话中的最新媒体补发至 QQ）。

### 5. 主人专属运维指令
* `hajimi 绑定主人 [QQ号]`：将指定 QQ 设为插件主人。
* `hajimi 登录`：拉起反指纹伪装的 Google 登录引导页并返回带坐标标尺的截图。
* `hajimi 坐标 <X> <Y>`：拟人点击网页上指定坐标（如点击按钮或人机验证）。
* `hajimi 点击 <文字>`：点击网页上包含指定文本的元素。
* `hajimi 输入 <内容>`：在当前聚焦的输入框中模拟真人打字并回车。
* `hajimi proxy <http://ip:port>`：动态修改浏览器代理并自动重启重连。

---

## ⚙️ 配置文件说明 (`hajimi_config.json`)

插件会在首次运行自动生成 `hajimi_config.json`，也可直接在 AstrBot WebUI 的插件设置面板中可视化调节：
```json
{
  "admin_qqs": [],
  "max_cache_mb": 300,
  "secure_1psid": "",
  "secure_1psidts": "",
  "accounts_cookie_str": "",
  "proxy": "[http://192.168.33.133:7890](http://192.168.33.133:7890)",
  "headless": true,
  "default_model": "gemini-hydrogen",
  "default_preset": "",
  "persistent_chat_url": "[https://gemini.google.com/app](https://gemini.google.com/app)",
  "media_timeout": 240
}
```

---
V3.6.0：首次发布

V3.6.1：改善对话文字排版

V3.6.2：修复换头功能

## 💡 常见问题 (FAQ)

1. **Q：为什么提示浏览器未登录或跳转到了 CookieMismatch 页面？**
   A：说明您的 Cookie 已失效或未正确绑定根凭证。建议重新执行 `hajimi 根凭证` 与 `hajimi rawcookie` 绑定最新凭证。
2. **Q：生成的视频或 GIF 动图文件很大怎么办？**
   A：插件内置了三档自适应 GIF 压缩器，若检测到 `ffmpeg` 工具存在，会自动将视频压缩至 `6MB` 以内的 `.gif` 动图发送（若 QQ 通道仍拒收则自动回退发送原版 `.mp4` 视频）；同时 `media_cache` 目录会在超过设定容量（默认 `300MB`）后自动清理最旧的缓存文件。

