import os
import re
import time
import json
import uuid
import base64
import shutil
import tempfile
import traceback
import subprocess
import random
import asyncio
from collections import deque
from typing import List, Optional, Dict, Any, Tuple, Deque

import aiohttp
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Image, Plain, Reply, At

try:
    from astrbot.api import AstrBotConfig
except ImportError:
    AstrBotConfig = dict  # type: ignore

# 兼容导入 AstrBot 视频与音频组件
try:
    from astrbot.api.message_components import Video
except ImportError:
    Video = None

try:
    from astrbot.api.message_components import Record
except ImportError:
    Record = None

# 导入 Playwright 异步 API
try:
    from playwright.async_api import async_playwright, BrowserContext, Page, Response
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# 可选导入 playwright_stealth (若容器内安装了则自动启用额外伪装)
try:
    from playwright_stealth import stealth_async
    STEALTH_LIB_AVAILABLE = True
except ImportError:
    STEALTH_LIB_AVAILABLE = False


# ==================== 姬咪奈（姬咪）专属随机人味语录池 ====================
WAIT_CHAT_REPLIES = [
    "💬 收到喵~ 姬咪正在向 Gemini 网页端认真请教中，马上把回复转达给你~🐾",
    "🐱 明白啦喵！姬咪已经把你的问题递给网页端的 Gemini 啦，稍等片刻哦~✨",
    "🐾 思考中喵~ 正在连接 Gemini 网页端组织语言，马上回复你哦~"
]

WAIT_DRAW_REPLIES = [
    "🎨 收到喵~ 姬咪正在铺开空白画布努力作画喵，稍微等本喵一下下哦~🐾",
    "🖌️ 灵感大爆发喵！姬咪的画笔已经转起来啦，给人家十来秒时间~✨",
    "🐾 哼哼，交给我吧喵！姬咪正在调色板里疯狂搅拌，马上给你变出一张新图~",
    "✨ 这种小事难不倒本姬咪喵！正在全力挥动画笔，精彩马上呈现~"
]

WAIT_EDIT_REPLIES = [
    "🐱 盯——（竖起猫耳仔细观察原图中）… 明白啦！姬咪这就开始施展改图魔法喵~",
    "🎨 姬咪奈收到！正在全息画布上对着原图涂涂改改中，稍等片刻喵~🐟",
    "🐱 唔喵…这个改图要求很有趣呢！姬咪已经在动笔重绘啦，乖乖等我一下哦~",
    "🖌️ 收到原图喵！姬咪正在注入新的灵魂，稍微等一下下哦~🐾"
]

WAIT_VIDEO_REPLIES = [
    "🎬 摄影机就位喵！姬咪正在全力渲染动态画面，视频/动图制作较慢，请耐心等本喵一两分钟哦~🐾",
    "🎞️ 收到动态创作指令喵！姬咪正在一帧一帧手绘动画特效，稍微等一下下啦~✨",
    "🐾 姬咪大导演开机啦！正在召唤光影魔法生成动态影像，精彩马上上映喵~"
]

WAIT_MUSIC_REPLIES = [
    "🎵 姬咪戴上耳机开始调音啦喵！正在为你谱写专属旋律，稍等片刻哦~🐾",
    "🎹 灵感音符跳动中喵~ 姬咪正在录音棚里努力编曲，马上唱给你听~✨",
    "🎸 收到点歌/作曲要求喵！姬咪的乐队已经准备就绪，请静候佳音喵~"
]

DONE_REPLIES = [
    "✨ 作品出炉啦喵~ 快看看合不合心意，记得夸夸姬咪哦！",
    "🎨 哒哒！姬咪奈的大作完成喵，请查收~🐾",
    "🐱 呼~ 终于搞定啦，姬咪的猫爪子都忙酸了喵，不给个小鱼干犒劳一下吗？🐟",
    "🖌️ 哼哼，也不看看是谁出手！新鲜出炉的作品送到啦喵~✨",
    "🐾 搞定喵！当当当当~ 快看看姬咪这次的创作魔法效果怎么样？"
]

QUEUE_WAIT_REPLIES = [
    "🐾 喵呜~ 姬咪爪子正忙着呢！已经帮你排在后面啦（当前排队：{pos}/{max_q}），乖乖等本喵一下哦~✨",
    "🐱 收到指令喵！前面还有任务在执行中，你排在第 {pos}/{max_q} 位，请耐心等待姬咪哦~🐟",
    "✨ 别急别急喵~ 姬咪正在全力处理上一个任务，已经给你拿好 {pos}/{max_q} 号爱的号码牌啦~🐾"
]

QUEUE_FULL_REPLIES = [
    "😿 喵呜！姬咪的排队小本本已经写满啦（最多同时排 {max_q} 个指令喵），等本喵手头忙完再来找我好不好嘛~🐾",
    "🐱 忙不过来啦喵！后面已经排了 {max_q} 个任务咯，心疼一下姬咪的小猫爪，稍后再发指令吧~🐟"
]

NEXT_TASK_REPLIES = [
    "🐾 呼~ 上一个忙完啦！现在开始执行你的下一个指令啦，姬咪马上开动喵~✨",
    "🐱 叮咚！久等啦喵~ 轮到你的指令咯，姬咪这就为你处理~🎨",
    "✨ 擦擦额头的汗喵~ 前面的任务搞定啦，马上开始执行你的指令咯！🐾"
]

FAIL_REPLIES = [
    "😿 失败了喵，让我看看什么原因喵：“{reason}”",
    "🐱 呜哇…这次执行失败了喵，让我看看什么原因喵：“{reason}”",
    "🐾 糟糕，魔法中断失败了喵，让我看看什么原因喵：“{reason}”"
]

QUOTA_COST_HINTS = {
    "image": "💡 本次预计消耗3%额度喵~",
    "video": "💡 本次预计消耗20%左右额度喵~",
    "gif":   "💡 本次预计消耗20%左右额度喵~",
    "music": "💡 本次预计消耗3%左右额度喵~"
}


# ==================== 极简模型映射表（已同步升级为 Gemini 4 Hydrogen） ====================
MODEL_ALIASES = {
    "1": "gemini-flash-lite",
    "lite": "gemini-flash-lite",
    "flash-lite": "gemini-flash-lite",
    "gemini-flash-lite": "gemini-flash-lite",

    "2": "gemini-hydrogen",
    "hydrogen": "gemini-hydrogen",
    "gemini-hydrogen": "gemini-hydrogen",
    "flash": "gemini-hydrogen",
    "3.8": "gemini-hydrogen",
    "3.8flash": "gemini-hydrogen",
    "gemini-flash": "gemini-hydrogen",

    "3": "gemini-pro",
    "pro": "gemini-pro",
    "gemini-pro": "gemini-pro",
    "carbon": "gemini-pro",
    "gemini-carbon": "gemini-pro",

    "4": "gemini-argon",
    "argon": "gemini-argon",
    "gemini-argon": "gemini-argon",
}

MODEL_DESC = {
    "gemini-flash-lite": "1️⃣ lite     -> Flash-Lite (极速轻量)",
    "gemini-hydrogen":   "2️⃣ hydrogen -> Gemini 4 Hydrogen (默认均衡主力，已替换 3.8 Flash)",
    "gemini-pro":        "3️⃣ pro      -> Pro / Thinking (高质量推理与创作)",
    "gemini-argon":      "4️⃣ argon    -> Gemini 4 Argon (长程/实验特调)"
}

WEB_MODEL_KEYWORDS = {
    "gemini-flash-lite": ["flash-lite", "3.5 flash-lite", "lite"],
    "gemini-hydrogen":   ["hydrogen", "4 hydrogen", "flash", "3.8"],
    "gemini-pro":        ["pro", "carbon", "thinking", "advanced", "deep", "思考", "专业"],
    "gemini-argon":      ["argon", "exp", "实验"]
}


# ==================== 网页端同款多模态预设库 ====================
STYLE_PRESETS: Dict[str, Tuple[str, str, str]] = {
    "换头": (
        "image", "🔄 智能换头/融图",
        "Please extract the face and head features from the second attached image (avatar reference) and seamlessly blend/replace them onto the main person in the first image, perfectly matching the original lighting, angle, clothing, and background."
    ),
    "换脸": (
        "image", "🔄 智能换脸/融图",
        "Please extract the face and head features from the second attached image (avatar reference) and seamlessly blend/replace them onto the main person in the first image, perfectly matching the original lighting, angle, clothing, and background."
    ),
    "素描": (
        "image", "✏️ 铅笔素描",
        "Please generate or transform the image into a detailed pencil sketch drawing style, with realistic hand-drawn graphite shading, cross-hatching, and paper texture."
    ),
    "转动漫": (
        "image", "🌸 照片转动漫",
        "Please transform the subject and scene into a high-quality Japanese anime style illustration, faithfully preserving the original pose, expression, composition, and key features."
    ),
    "二次元": (
        "image", "✨ 二次元立绘",
        "Please create or redraw the image in an exquisite 2D ACG anime artwork style, featuring vibrant colors, cel-shading, expressive eyes, and Makoto Shinkai / Kyoto Animation inspired lighting."
    ),
    "单色": (
        "image", "🖤 单色艺术",
        "Please create or transform the image into a striking monochrome / black-and-white fine art style, emphasizing dramatic contrast, light and shadow, and clean tonal depth."
    ),
    "像素画": (
        "image", "👾 复古像素画",
        "Please create or transform the image into a retro 16-bit pixel art style, with crisp pixel placement, nostalgic game color palette, and charming sprite aesthetics."
    ),
    "涂鸦": (
        "image", "🖍️ 潮流手绘涂鸦",
        "Please create or edit the image with a vibrant street-art doodle / graffiti illustration style, featuring bold hand-drawn marker outlines, playful splatters, and energetic colors."
    ),
    "水彩": (
        "image", "🎨 柔美水彩",
        "Please create or transform the image into a soft, translucent watercolor painting style, with natural pigment bleeding, delicate brush strokes, and cold-press watercolor paper texture."
    ),
    "赛博": (
        "image", "🌃 赛博朋克",
        "Please create or transform the image into a cyberpunk aesthetic, featuring futuristic neon lighting, cyan and magenta color grading, rain-slicked reflections, and high-tech atmosphere."
    ),
    "黏土": (
        "image", "🧸 3D黏土风",
        "Please create or transform the image into a cute 3D claymation / handcrafted polymer clay figure style, with soft studio lighting, rounded miniature textures, and playful charm."
    ),
    "贴纸": (
        "image", "🏷️ Q版模切贴纸",
        "Please turn the subject into a cute chibi die-cut vector sticker design, with a thick white border, flat vibrant colors, and clean isolated background."
    ),
    "照片转gif": (
        "gif", "🎞️ 照片转GIF动图",
        "Please animate this image and turn it into a smooth, lively looping animated GIF. Keep the original characters and art style intact while adding natural movement and expressions."
    ),
    "转gif": (
        "gif", "🎞️ 照片转GIF动图",
        "Please animate this image and turn it into a smooth, lively looping animated GIF. Keep the original characters and art style intact while adding natural movement and expressions."
    ),
    "表情包": (
        "gif", "😹 搞笑表情包GIF",
        "Please generate an expressive, funny, and exaggerated chibi meme animated GIF suitable for chat stickers, with lively looping motion."
    ),
    "像素动图": (
        "gif", "👾 像素风GIF动图",
        "Please generate an animated pixel art GIF with retro 16-bit frame-by-frame sprite animation and a smooth loop."
    ),
    "涂鸦动图": (
        "gif", "⚡ 涂鸦特效GIF",
        "Please generate an animated GIF with dynamic neon scribble / hand-drawn doodle effects dancing and glowing around the moving subject."
    ),
    "动漫动图": (
        "gif", "🌸 动漫风GIF动图",
        "Please generate a smooth Japanese anime style animated GIF with fluid sakuga motion, wind-blown hair, and vibrant lighting."
    ),
    "动漫风格": (
        "video", "🎬 动漫风格视频",
        "Please generate a video in a high-quality Japanese anime film style, featuring fluid 2D animation, cinematic anime lighting, and dynamic camera movement."
    ),
    "动漫视频": (
        "video", "🎬 动漫风格视频",
        "Please generate a video in a high-quality Japanese anime film style, featuring fluid 2D animation, cinematic anime lighting, and dynamic camera movement."
    ),
    "像素风": (
        "video", "🕹️ 像素画风格视频",
        "Please generate a video in a detailed retro pixel art animation style, with nostalgic 16-bit visual effects and smooth pixel motion."
    ),
    "像素视频": (
        "video", "🕹️ 像素画风格视频",
        "Please generate a video in a detailed retro pixel art animation style, with nostalgic 16-bit visual effects and smooth pixel motion."
    ),
    "涂鸦特效": (
        "video", "✨ 涂鸦特效视频",
        "Please generate a video featuring dynamic glowing hand-drawn doodle / neon scribble VFX animations interacting with the subject and motion."
    ),
    "涂鸦视频": (
        "video", "✨ 涂鸦特效视频",
        "Please generate a video featuring dynamic glowing hand-drawn doodle / neon scribble VFX animations interacting with the subject and motion."
    ),
    "电影感": (
        "video", "🎥 电影大片质感视频",
        "Please generate a cinematic video shot on 35mm film lens, with shallow depth of field, dramatic anamorphic lighting, rich color grading, and smooth camera tracking."
    ),
    "定格动画": (
        "video", "🧶 定格动画视频",
        "Please generate a video in a handcrafted stop-motion animation style (claymation / felt miniature), with charming frame-by-frame tactile movement."
    ),
    "赛博霓虹": (
        "video", "🌌 赛博霓虹视频",
        "Please generate a futuristic cyberpunk video filled with glowing neon holograms, atmospheric rain particles, and dynamic sci-fi camera motion."
    ),
    "纯音乐": (
        "music", "☕ Lo-Fi纯音乐",
        "Please generate a relaxing instrumental Lo-Fi chillhop music track with warm piano chords, gentle vinyl crackle, and a soothing beat."
    ),
    "lofi": (
        "music", "☕ Lo-Fi纯音乐",
        "Please generate a relaxing instrumental Lo-Fi chillhop music track with warm piano chords, gentle vinyl crackle, and a soothing beat."
    ),
    "流行": (
        "music", "🎤 现代流行音乐",
        "Please generate a catchy modern Pop music track with an upbeat melody, rich instrumentation, and polished studio production."
    ),
    "动漫ost": (
        "music", "🎻 动漫OST配乐",
        "Please generate an emotional and energetic Japanese Anime OST music track combining orchestral strings, bright piano, and dynamic rhythm."
    ),
    "电音": (
        "music", "🎧 电子音乐(EDM)",
        "Please generate an energetic electronic synthwave / EDM music track with vibrant synthesizers, punchy bassline, and driving beats."
    ),
    "古风": (
        "music", "🪈 国风民乐",
        "Please generate a traditional Chinese Guofeng instrumental music track featuring guzheng, pipa, bamboo flute (dizi), and poetic melodies."
    ),
    "钢琴曲": (
        "music", "🎹 治愈独奏钢琴",
        "Please generate an expressive and soothing solo acoustic piano music piece with delicate melody and warm reverb."
    ),
}


# ==================== 深度反自动化指纹伪造脚本 (Stealth Evade JS) ====================
STEALTH_INIT_SCRIPT = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}

    window.chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' }
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' }
        },
        csi: function() { return {}; },
        loadTimes: function() { return {}; }
    };

    const realUa = navigator.userAgent.replace(/HeadlessChrome/g, 'Chrome');
    const matchVer = realUa.match(/Chrome\\/(\\d+)\\.(\\d+)\\.(\\d+)\\.(\\d+)/);
    const majorVer = matchVer ? matchVer[1] : '131';
    const fullVer = matchVer ? matchVer[0].split('/')[1] : '131.0.6778.85';

    const fakeBrands = [
        { brand: 'Google Chrome', version: majorVer },
        { brand: 'Chromium', version: majorVer },
        { brand: 'Not_A Brand', version: '24' }
    ];
    const fakeFullList = [
        { brand: 'Google Chrome', version: fullVer },
        { brand: 'Chromium', version: fullVer },
        { brand: 'Not_A Brand', version: '24.0.0.0' }
    ];
    try {
        Object.defineProperty(navigator, 'userAgentData', {
            get: () => ({
                brands: fakeBrands,
                mobile: false,
                platform: 'Linux',
                getHighEntropyValues: async (hints) => ({
                    architecture: 'x86',
                    bitness: '64',
                    brands: fakeBrands,
                    fullVersionList: fakeFullList,
                    mobile: false,
                    model: '',
                    platform: 'Linux',
                    platformVersion: '6.5.0',
                    uaFullVersion: fullVer,
                    wow64: false
                }),
                toJSON: () => ({ brands: fakeBrands, mobile: false, platform: 'Linux' })
            })
        });
    } catch (e) {}

    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

    const getParameterProxyHandler = {
        apply: function(target, ctx, args) {
            const param = args[0];
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel Iris OpenGL Engine';
            return Reflect.apply(target, ctx, args);
        }
    };
    try {
        if (window.WebGLRenderingContext) {
            WebGLRenderingContext.prototype.getParameter = new Proxy(WebGLRenderingContext.prototype.getParameter, getParameterProxyHandler);
        }
        if (window.WebGL2RenderingContext) {
            WebGL2RenderingContext.prototype.getParameter = new Proxy(WebGL2RenderingContext.prototype.getParameter, getParameterProxyHandler);
        }
    } catch (e) {}

    for (const prop of Object.getOwnPropertyNames(window)) {
        if (prop.startsWith('cdc_') || prop.startsWith('__pw') || prop.startsWith('__playwright')) {
            try { delete window[prop]; } catch (e) {}
        }
    }
})();
"""


@register(
    "astrbot_plugin_hajimi",
    "fnos_user",
    "Gemini真实浏览器拟人操作多模态与文本对话插件(支持Hydrogen默认模型+LRU自动缓存清理+纯文本问答+主人鉴权)",
    "3.6.0"
)
class HajimiPlugin(Star):
    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        self.astrbot_config = config
        self.plugin_dir = os.path.dirname(__file__)
        self.config_path = os.path.join(self.plugin_dir, "hajimi_config.json")
        self.cache_dir = os.path.join(self.plugin_dir, "media_cache")
        self.user_data_dir = os.path.join(self.plugin_dir, "browser_profile")
        self.storage_state_path = os.path.join(self.plugin_dir, "storage_state.json")
        self.imported_json_cookie_path = os.path.join(self.plugin_dir, "google_cookies.json")
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(self.user_data_dir, exist_ok=True)

        self.config = self._load_config()
        self.current_model: str = self.config.get("default_model", "gemini-hydrogen")
        self.current_preset: str = self.config.get("default_preset", "")
        self.persistent_chat_url: str = self.config.get("persistent_chat_url", "https://gemini.google.com/app")
        self.admin_qqs: List[str] = [str(x).strip() for x in self.config.get("admin_qqs", []) if str(x).strip()]

        self.pw = None
        self.browser_context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self._page_op_lock = asyncio.Lock()
        self.MAX_QUEUE_SIZE = 2
        self._task_running: bool = False
        self._wait_queue: Deque[asyncio.Event] = deque()

        self.is_logged_in = False
        self.keepalive_task: Optional[asyncio.Task] = None

        self._intercepted_media: List[Tuple[bytes, str, str]] = []
        self._capturing_media: bool = False

        # 记录最近一次生成的本地媒体文件与模式，便于 `hajimi 发送` 随时补发
        self.last_generated_files: List[Tuple[str, str]] = []
        self.last_generated_mode: str = "image"

        # 启动时立即按上限清理一次超额多媒体缓存
        self._cleanup_media_cache()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._init_browser())
        except RuntimeError:
            pass

    # ==================== 本地多媒体缓存空间自动管理 (LRU) ====================
    def _get_max_cache_mb(self) -> int:
        """优先读取 AstrBot WebUI 设置中的 max_cache_mb，其次读取本地配置，默认 300MB"""
        val = None
        if isinstance(self.astrbot_config, dict) and self.astrbot_config.get("max_cache_mb") is not None:
            val = self.astrbot_config.get("max_cache_mb")
        elif self.config.get("max_cache_mb") is not None:
            val = self.config.get("max_cache_mb")
        try:
            return int(val) if val is not None else 300
        except (ValueError, TypeError):
            return 300

    def _get_media_cache_stats(self) -> Tuple[int, int]:
        """返回 (文件总数, 总字节数)"""
        total_files = 0
        total_bytes = 0
        if not os.path.isdir(self.cache_dir):
            return 0, 0
        try:
            for root, _, filenames in os.walk(self.cache_dir):
                for fn in filenames:
                    fp = os.path.join(root, fn)
                    try:
                        st = os.stat(fp)
                        total_files += 1
                        total_bytes += st.st_size
                    except OSError:
                        pass
        except Exception:
            pass
        return total_files, total_bytes

    def _cleanup_media_cache(self, protected_paths: Optional[List[str]] = None) -> Tuple[int, int, int]:
        """
        自动 LRU 清理 media_cache 目录：
        当总占用超过 max_cache_mb (默认 300MB) 时，按修改时间从旧到新删除文件，直到总大小 <= 上限。
        返回: (删除文件数, 释放字节数, 清理后剩余总字节数)
        """
        max_mb = self._get_max_cache_mb()
        if not os.path.isdir(self.cache_dir):
            return 0, 0, 0

        entries: List[Tuple[str, int, float]] = []
        total_bytes = 0
        for root, _, filenames in os.walk(self.cache_dir):
            for fn in filenames:
                fp = os.path.join(root, fn)
                try:
                    st = os.stat(fp)
                    entries.append((fp, st.st_size, st.st_mtime))
                    total_bytes += st.st_size
                except OSError:
                    pass

        if max_mb <= 0:
            return 0, 0, total_bytes

        limit_bytes = max_mb * 1024 * 1024
        if total_bytes <= limit_bytes:
            return 0, 0, total_bytes

        before_bytes = total_bytes
        protected_set = {os.path.abspath(p) for p in (protected_paths or []) if p}

        # 按修改时间升序排序（最旧的文件排在最前面优先清理）
        entries.sort(key=lambda item: item[2])

        deleted_count = 0
        freed_bytes = 0

        # 第一轮：优先清理非受保护的旧文件
        for fp, fsize, _ in entries:
            if total_bytes <= limit_bytes:
                break
            if os.path.abspath(fp) in protected_set:
                continue
            try:
                os.remove(fp)
                total_bytes -= fsize
                freed_bytes += fsize
                deleted_count += 1
            except OSError as e:
                logger.debug(f"[Hajimi 缓存清理] 删除文件跳过 ({fp}): {e}")

        # 同步剔除已被清理的 last_generated_files 记录
        if self.last_generated_files:
            self.last_generated_files = [(fn, fp) for fn, fp in self.last_generated_files if os.path.exists(fp)]

        if deleted_count > 0:
            logger.info(
                f"🧹 [Hajimi 缓存清理] media_cache 超出上限 ({before_bytes / 1048576:.1f}MB > {max_mb}MB)，"
                f"已自动删除 {deleted_count} 个旧文件 (释放 {freed_bytes / 1048576:.1f}MB)，"
                f"当前剩余 {total_bytes / 1048576:.1f}MB"
            )
        return deleted_count, freed_bytes, total_bytes

    # ==================== 配置文件与主人权限管理 ====================
    def _normalize_model_name(self, model_name: str) -> str:
        m = (model_name or "").strip().lower()
        if m in MODEL_ALIASES:
            return MODEL_ALIASES[m]
        return "gemini-hydrogen"

    def _load_config(self) -> Dict[str, Any]:
        default_cfg: Dict[str, Any] = {
            "admin_qqs": [],
            "max_cache_mb": 300,
            "secure_1psid": os.getenv("SECURE_1PSID", "").strip(),
            "secure_1psidts": os.getenv("SECURE_1PSIDTS", "").strip(),
            "accounts_cookie_str": "",
            "proxy": os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "http://192.168.33.133:7890",
            "headless": True,
            "default_model": "gemini-hydrogen",
            "default_preset": "",
            "persistent_chat_url": "https://gemini.google.com/app",
            "media_timeout": 240
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                default_cfg.update({k: v for k, v in saved.items() if v is not None})
            except Exception as e:
                logger.warning(f"[Hajimi] 读取配置文件失败，使用默认配置: {e}")

        # 合并 AstrBot WebUI 插件配置面板中的参数（若已设置）
        if isinstance(self.astrbot_config, dict):
            for key in ("max_cache_mb", "default_model", "media_timeout", "proxy", "headless", "admin_qqs"):
                if key in self.astrbot_config and self.astrbot_config[key] is not None:
                    val = self.astrbot_config[key]
                    # 仅当 WebUI 中非默认空值或明确配置时同步
                    if key == "admin_qqs" and not val and default_cfg.get("admin_qqs"):
                        self.astrbot_config["admin_qqs"] = list(default_cfg["admin_qqs"])
                        continue
                    if key == "proxy" and val == "http://192.168.33.133:7890" and default_cfg.get("proxy"):
                        continue
                    default_cfg[key] = val

        # 自动将旧配置的 gemini-flash 迁移为最新的 gemini-hydrogen
        default_cfg["default_model"] = self._normalize_model_name(default_cfg.get("default_model", "gemini-hydrogen"))
        self._save_config_dict(default_cfg)
        return default_cfg

    def _reload_disk_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if v is not None:
                        self.config[k] = v
            except Exception as e:
                logger.warning(f"[Hajimi] 重新读取磁盘配置文件失败: {e}")

        if isinstance(self.astrbot_config, dict):
            for key in ("max_cache_mb", "media_timeout", "headless"):
                if key in self.astrbot_config and self.astrbot_config[key] is not None:
                    self.config[key] = self.astrbot_config[key]
            if self.astrbot_config.get("admin_qqs"):
                self.config["admin_qqs"] = list(self.astrbot_config["admin_qqs"])

        self.admin_qqs = [str(x).strip() for x in self.config.get("admin_qqs", []) if str(x).strip()]

    def _save_config_dict(self, cfg: Dict[str, Any]):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Hajimi] 保存配置文件失败: {e}")

    def _save_config(self):
        self.config["admin_qqs"] = self.admin_qqs
        self.config["max_cache_mb"] = self._get_max_cache_mb()
        self.config["default_model"] = self.current_model
        self.config["default_preset"] = self.current_preset
        self.config["persistent_chat_url"] = self.persistent_chat_url
        self._save_config_dict(self.config)

        # 同步写回 AstrBotConfig（如可用）
        if isinstance(self.astrbot_config, dict):
            try:
                self.astrbot_config["admin_qqs"] = list(self.admin_qqs)
                self.astrbot_config["max_cache_mb"] = self.config["max_cache_mb"]
                self.astrbot_config["default_model"] = self.current_model
                self.astrbot_config["proxy"] = self.config.get("proxy", "")
                if hasattr(self.astrbot_config, "save_config"):
                    self.astrbot_config.save_config()
            except Exception:
                pass

    def _is_master(self, event: AstrMessageEvent) -> bool:
        """
        判断当前发送指令的用户是否为主人（管理员）：
        1. 若 AstrBot 框架已将该用户设为 admin (event.is_admin() == True)，直接放行；
        2. 若发送者 QQ 号在 admin_qqs 列表中，直接放行。
        """
        try:
            if hasattr(event, "is_admin") and callable(event.is_admin) and event.is_admin():
                return True
        except Exception:
            pass
        sender_id = str(event.get_sender_id() or "").strip()
        if sender_id and sender_id in self.admin_qqs:
            return True
        return False

    # ==================== 后台主动续期保活、缓存清理与 Cookie 持久化 ====================
    async def _periodic_keepalive_loop(self):
        while True:
            await asyncio.sleep(1200)
            try:
                # 定期清理超出设定上限的多媒体缓存
                await asyncio.to_thread(self._cleanup_media_cache)

                if self._task_running or self._page_op_lock.locked():
                    continue
                async with self._page_op_lock:
                    if self.browser_context and self.page and not self.page.is_closed():
                        cur_url = self.page.url
                        if "gemini.google.com" in cur_url and "accounts.google.com" not in cur_url:
                            await self.page.evaluate("() => { window.dispatchEvent(new Event('focus')); }")
                            self.is_logged_in = await self._check_page_login_state(self.page)
                            if self.is_logged_in:
                                await self._save_live_browser_state()
                                logger.info("💓 [Hajimi 保活] 后台 20 分钟静默续期完成，长效 Cookie 已同步落盘")
            except Exception as e:
                logger.debug(f"[Hajimi 保活] 略过: {e}")

    async def _on_network_response(self, response: Response):
        if not self._capturing_media:
            return
        try:
            url = response.url
            if response.status != 200:
                return
            ct = (response.headers.get("content-type") or "").lower()

            if any(x in url.lower() for x in ("gstatic.com", "play.google.com", "avatar", "favicon", "logo", ".svg", ".js", ".css")):
                return

            is_target_media = False
            if any(m in ct for m in ("video/", "audio/", "image/gif", "image/webp", "image/png", "image/jpeg")):
                if any(host in url.lower() for host in ("googleusercontent.com", "ggpht.com", "googleapis.com", "gemini.google.com", "blob:")):
                    is_target_media = True

            if is_target_media:
                body = await response.body()
                if len(body) > 15 * 1024:
                    logger.info(f"📥 [Hajimi 浏览器嗅探] 捕获媒体流: {ct} | 大小={len(body)//1024}KB | URL={url[:70]}...")
                    self._intercepted_media.append((body, ct, url))
        except Exception:
            pass

    async def _save_live_browser_state(self):
        if not self.browser_context:
            return
        try:
            all_cookies = await self.browser_context.cookies()
            one_year_later = int(time.time()) + 365 * 86400
            upgraded_cookies = []
            updated_cfg = False

            for c in all_cookies:
                c_copy = dict(c)
                if c_copy.get("expires", -1) <= 0 and any(d in c_copy.get("domain", "") for d in ("google.com", "youtube.com")):
                    c_copy["expires"] = one_year_later
                    upgraded_cookies.append(c_copy)

                if c.get("name") == "__Secure-1PSID" and c.get("value"):
                    if self.config.get("secure_1psid") != c["value"]:
                        self.config["secure_1psid"] = c["value"]
                        updated_cfg = True
                elif c.get("name") == "__Secure-1PSIDTS" and c.get("value"):
                    if self.config.get("secure_1psidts") != c["value"]:
                        self.config["secure_1psidts"] = c["value"]
                        updated_cfg = True

            if upgraded_cookies:
                try:
                    await self.browser_context.add_cookies(upgraded_cookies)
                except Exception:
                    pass

            await self.browser_context.storage_state(path=self.storage_state_path)
            if updated_cfg:
                self._save_config()
                logger.info("♻️ [Hajimi 浏览器] 已同步最新 1PSIDTS 并固化 365 天持久化凭证！")
        except Exception as e:
            logger.debug(f"[Hajimi 浏览器] 导出实时 Cookie 快照略过: {e}")

    async def _has_valid_browser_cookies(self, context: BrowserContext) -> bool:
        try:
            existing = await context.cookies(["https://gemini.google.com", "https://www.google.com", "https://accounts.google.com"])
            has_psid = any(c.get("name") in ("__Secure-1PSID", "SID", "__Host-GAPS") and c.get("value") for c in existing)
            if has_psid:
                return True
        except Exception:
            pass

        if os.path.exists(self.storage_state_path):
            try:
                with open(self.storage_state_path, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
                saved_cookies = state_data.get("cookies", [])
                if saved_cookies:
                    one_year_later = int(time.time()) + 365 * 86400
                    for sc in saved_cookies:
                        if sc.get("expires", -1) <= 0:
                            sc["expires"] = one_year_later
                    await context.add_cookies(saved_cookies)
                    logger.info(f"♻️ [Hajimi 浏览器] 已从 storage_state.json 恢复 {len(saved_cookies)} 项长效登录 Cookie！")
                    return any(c.get("name") == "__Secure-1PSID" and c.get("value") for c in saved_cookies)
            except Exception as e:
                logger.warning(f"[Hajimi 浏览器] 恢复 storage_state.json 快照异常: {e}")

        return False

    async def _inject_cookies_to_context(self, context: BrowserContext, clear_first: bool = False):
        psid = (self.config.get("secure_1psid") or "").strip()
        psidts = (self.config.get("secure_1psidts") or "").strip()
        raw_cookie_str = (self.config.get("raw_cookie_str") or "").strip()
        acc_cookie_str = (self.config.get("accounts_cookie_str") or "").strip()
        exp_ts = int(time.time()) + 365 * 86400

        if clear_first:
            try:
                await context.clear_cookies()
                if os.path.exists(self.storage_state_path):
                    os.remove(self.storage_state_path)
                logger.info("🧹 [Hajimi 浏览器] 已清理旧的冲突 Cookie 与快照")
            except Exception:
                pass

        cookies_to_add = []

        if os.path.exists(self.imported_json_cookie_path):
            try:
                with open(self.imported_json_cookie_path, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                if isinstance(raw_list, dict) and "cookies" in raw_list:
                    raw_list = raw_list["cookies"]
                if isinstance(raw_list, list):
                    for item in raw_list:
                        if not isinstance(item, dict) or not item.get("name") or item.get("value") is None:
                            continue
                        name = str(item["name"]).strip()
                        val = str(item["value"]).strip()
                        dom = str(item.get("domain") or ".google.com").strip()
                        path = str(item.get("path") or "/").strip()
                        is_host = name.startswith("__Host-")
                        is_sec = bool(item.get("secure", True)) or name.startswith("__Secure-") or is_host
                        c_obj: Dict[str, Any] = {
                            "name": name,
                            "value": val,
                            "path": path,
                            "secure": is_sec,
                            "httpOnly": bool(item.get("httpOnly", False)),
                            "sameSite": "Lax",
                            "expires": exp_ts
                        }
                        if is_host:
                            target_host = dom.lstrip(".")
                            c_obj["url"] = f"https://{target_host}"
                        else:
                            c_obj["domain"] = dom
                        cookies_to_add.append(c_obj)
                    logger.info(f"📂 [Hajimi 浏览器] 已从 google_cookies.json 读取 {len(cookies_to_add)} 项全域名 Cookie！")
            except Exception as e:
                logger.warning(f"[Hajimi 浏览器] 解析 google_cookies.json 失败: {e}")

        if raw_cookie_str:
            for pair in raw_cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        is_host = k.startswith("__Host-")
                        is_sec = k.startswith("__Secure-") or is_host
                        cookie_item: Dict[str, Any] = {
                            "name": k,
                            "value": v,
                            "path": "/",
                            "secure": True if is_sec else False,
                            "httpOnly": True if "PSID" in k or k in ("SID", "HSID", "SSID") else False,
                            "sameSite": "Lax",
                            "expires": exp_ts
                        }
                        if is_host:
                            host_url = "https://accounts.google.com" if any(x in k for x in ("GAPS", "LSID")) else "https://gemini.google.com"
                            cookie_item["url"] = host_url
                        else:
                            cookie_item["domain"] = ".google.com"
                        cookies_to_add.append(cookie_item)

        if acc_cookie_str:
            for pair in acc_cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        is_host = k.startswith("__Host-")
                        c_acc: Dict[str, Any] = {
                            "name": k,
                            "value": v,
                            "path": "/",
                            "secure": True,
                            "httpOnly": True,
                            "sameSite": "Lax",
                            "expires": exp_ts
                        }
                        if is_host:
                            c_acc["url"] = "https://accounts.google.com"
                        else:
                            c_acc["domain"] = "accounts.google.com"
                        cookies_to_add.append(c_acc)

        if psid and not any(c["name"] == "__Secure-1PSID" for c in cookies_to_add):
            cookies_to_add.append({
                "name": "__Secure-1PSID", "value": psid, "domain": ".google.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "Lax", "expires": exp_ts
            })
        if psidts and not any(c["name"] == "__Secure-1PSIDTS" for c in cookies_to_add):
            cookies_to_add.append({
                "name": "__Secure-1PSIDTS", "value": psidts, "domain": ".google.com", "path": "/",
                "secure": True, "httpOnly": True, "sameSite": "Lax", "expires": exp_ts
            })

        cookies_to_add.append({
            "name": "CONSENT", "value": "YES+cb.20240116-07-p0.en+FX+410", "domain": ".google.com",
            "path": "/", "secure": True, "sameSite": "Lax", "expires": exp_ts
        })

        if not cookies_to_add:
            return

        success_cnt = 0
        for c in cookies_to_add:
            try:
                await context.add_cookies([c])
                success_cnt += 1
            except Exception:
                pass
        logger.info(f"🍪 [Hajimi 浏览器] 已成功注入 {success_cnt}/{len(cookies_to_add)} 项 365 天长效 Cookie！")

    async def _check_page_login_state(self, page: Page) -> bool:
        try:
            url = page.url
            if "accounts.google.com" in url or "CookieMismatch" in url:
                return False

            has_sign_in_btn = await page.evaluate("""() => {
                const linksAndBtns = document.querySelectorAll('a, button');
                for (const el of linksAndBtns) {
                    if (el.offsetParent === null) continue;
                    const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
                    const href = (el.getAttribute('href') || '').toLowerCase();
                    if (txt === 'sign in' || txt === '登录' || txt === '登入' || href.includes('accounts.google.com/servicelogin')) {
                        return true;
                    }
                }
                return false;
            }""")
            if has_sign_in_btn:
                return False

            input_locator = page.locator(
                'rich-textarea div[contenteditable="true"], '
                'div.ql-editor[contenteditable="true"], '
                'div[role="textbox"][contenteditable="true"], '
                'textarea[aria-label*="prompt" i], '
                'textarea[placeholder*="Gemini" i]'
            )
            if await input_locator.count() > 0:
                return True
        except Exception:
            pass
        return False

    async def _get_clean_user_agent(self, pw_instance) -> str:
        try:
            tmp_browser = await pw_instance.chromium.launch(headless=True, args=["--no-sandbox"])
            tmp_page = await tmp_browser.new_page()
            raw_ua = await tmp_page.evaluate("() => navigator.userAgent")
            await tmp_browser.close()
            clean_ua = raw_ua.replace("HeadlessChrome/", "Chrome/")
            logger.info(f"🎭 [Hajimi 反指纹] 已对齐原生内核 User-Agent: {clean_ua}")
            return clean_ua
        except Exception:
            return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    async def _init_browser(self, force_restart: bool = False, force_reinject_cookies: bool = False) -> Tuple[bool, str]:
        if not PLAYWRIGHT_AVAILABLE:
            msg = "容器内尚未安装 playwright！请在容器终端执行：`pip install playwright && playwright install --with-deps chromium`"
            logger.error(f"❌ [Hajimi] {msg}")
            return False, msg

        async with self._page_op_lock:
            if self.page is not None and not self.page.is_closed() and not force_restart:
                self.is_logged_in = await self._check_page_login_state(self.page)
                if self.is_logged_in:
                    return True, "浏览器已就绪"

            await self._close_browser_unlocked()
            self._reload_disk_config()

            proxy_str = (self.config.get("proxy") or "").strip().strip("[]'\"")
            headless = bool(self.config.get("headless", True))

            logger.info(f"🌐 [Hajimi 浏览器] 正在启动反指纹伪装 Chromium (无头模式={headless}, 代理={proxy_str or '直连'})...")
            try:
                self.pw = await async_playwright().start()
                clean_ua = await self._get_clean_user_agent(self.pw)

                chrome_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-infobars",
                    "--window-size=1366,900",
                    "--lang=zh-CN,zh",
                    "--use-gl=angle",
                    "--use-angle=gl-egl",
                    "--ignore-gpu-blocklist",
                ]
                if headless:
                    chrome_args.append("--headless=new")

                launch_kwargs: Dict[str, Any] = {
                    "user_data_dir": self.user_data_dir,
                    "headless": headless,
                    "viewport": {"width": 1366, "height": 900},
                    "locale": "zh-CN",
                    "user_agent": clean_ua,
                    "ignore_https_errors": True,
                    "ignore_default_args": ["--enable-automation"],
                    "args": chrome_args
                }
                if proxy_str:
                    launch_kwargs["proxy"] = {"server": proxy_str}

                self.browser_context = await self.pw.chromium.launch_persistent_context(**launch_kwargs)
                await self.browser_context.add_init_script(STEALTH_INIT_SCRIPT)

                if force_reinject_cookies:
                    await self._inject_cookies_to_context(self.browser_context, clear_first=True)
                else:
                    has_existing = await self._has_valid_browser_cookies(self.browser_context)
                    if not has_existing:
                        logger.info("ℹ️ [Hajimi 浏览器] 本地浏览器配置尚无 Cookie，首次从配置文件导入...")
                        await self._inject_cookies_to_context(self.browser_context, clear_first=False)
                    else:
                        logger.info("♻️ [Hajimi 浏览器] 检测到 Chromium Profile 内已有持久化的最新登录态，直接复用！")

                pages = self.browser_context.pages
                self.page = pages[0] if pages else await self.browser_context.new_page()
                if STEALTH_LIB_AVAILABLE:
                    try:
                        await stealth_async(self.page)
                        logger.info("🛡️ [Hajimi 反指纹] 已挂载 playwright-stealth 深度伪装层！")
                    except Exception:
                        pass

                self.page.on("response", self._on_network_response)

                target_url = self.persistent_chat_url or "https://gemini.google.com/app"
                logger.info(f"🔗 [Hajimi 浏览器] 正在打开对话页面: {target_url}")
                await self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                if "CookieMismatch" in self.page.url or "we've detected a problem with your cookie" in (await self.page.content()).lower():
                    logger.warning("⚠️ [Hajimi 浏览器] 检测到 Google CookieMismatch 冲突页，正在清理重复 Cookie 并重新加载...")
                    await self.browser_context.clear_cookies()
                    await self._inject_cookies_to_context(self.browser_context, clear_first=False)
                    await self.page.goto("https://gemini.google.com/app?hl=zh-CN", wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(4)

                await self._dismiss_popups(self.page)

                if self.keepalive_task is None or self.keepalive_task.done():
                    self.keepalive_task = asyncio.create_task(self._periodic_keepalive_loop())

                self.is_logged_in = await self._check_page_login_state(self.page)
                if self.is_logged_in:
                    if "gemini.google.com/app" in self.page.url:
                        self.persistent_chat_url = self.page.url
                        self._save_config()
                    # 启动后自动对齐默认模型（如 Gemini 4 Hydrogen）
                    await self._switch_web_model_if_needed(self.page, self.current_model)
                    await self._save_live_browser_state()
                    logger.info(f"🎉 [Hajimi 浏览器] Gemini 网页端登录成功！当前绑定会话: {self.persistent_chat_url} | 默认模型: {self.current_model}")
                    return True, f"已成功连接并锁定网页会话：{self.persistent_chat_url}（当前模型：{self.current_model}）"
                else:
                    cur_url = self.page.url
                    logger.warning(f"⚠️ [Hajimi 浏览器] 页面已打开 ({cur_url})，当前处于待登录状态。")
                    return False, (
                        f"当前处于未登录状态 (URL: {cur_url})。\n"
                        f"👉 方式1：主人发送 `hajimi 登录` 使用反指纹伪装页面登录；\n"
                        f"👉 方式2（100%免密过风控且永不掉线）：主人发送 `hajimi 根凭证 <在accounts.google.com复制的Cookie>` + `hajimi rawcookie <在gemini复制的Cookie>`！"
                    )

            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f"❌ [Hajimi 浏览器] 启动异常:\n{tb_str}")
                await self._close_browser_unlocked()
                return False, f"启动 Chromium 失败: {type(e).__name__}: {e}"

    async def _close_browser_unlocked(self):
        if self.browser_context:
            await self._save_live_browser_state()
        try:
            if self.browser_context:
                await self.browser_context.close()
        except Exception:
            pass
        try:
            if self.pw:
                await self.pw.stop()
        except Exception:
            pass
        self.page = None
        self.browser_context = None
        self.pw = None

    async def terminate(self):
        if self.keepalive_task:
            self.keepalive_task.cancel()
        async with self._page_op_lock:
            await self._close_browser_unlocked()

    async def _dismiss_popups(self, page: Page):
        popup_selectors = [
            'button:has-text("Got it")',
            'button:has-text("知道了")',
            'button:has-text("Continue")',
            'button:has-text("继续")',
            'button[aria-label="Close"]',
            'button[aria-label="关闭"]'
        ]
        for sel in popup_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=500):
                    await loc.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

    # ==================== 网页交互式原生登录辅助（带坐标标尺与红点反馈） ====================
    async def _screenshot_with_ruler(self, page: Page, click_point: Optional[Tuple[int, int]] = None) -> bytes:
        try:
            await page.evaluate("""(pt) => {
                const old = document.getElementById('__hajimi_ruler_overlay');
                if (old) old.remove();
                const overlay = document.createElement('div');
                overlay.id = '__hajimi_ruler_overlay';
                overlay.style.cssText = 'position:fixed;top:0;left:0;width:1366px;height:900px;pointer-events:none;z-index:2147483647;';

                for (let x = 100; x < 1366; x += 100) {
                    const line = document.createElement('div');
                    line.style.cssText = `position:absolute;left:${x}px;top:0;width:1px;height:900px;background:rgba(255,0,0,0.18);`;
                    const label = document.createElement('span');
                    label.innerText = x;
                    label.style.cssText = 'position:absolute;top:2px;left:2px;font:bold 11px sans-serif;color:#d00;background:rgba(255,255,255,0.75);padding:0 2px;border-radius:2px;';
                    line.appendChild(label);
                    overlay.appendChild(line);
                }
                for (let y = 100; y < 900; y += 100) {
                    const line = document.createElement('div');
                    line.style.cssText = `position:absolute;top:${y}px;left:0;height:1px;width:1366px;background:rgba(255,0,0,0.18);`;
                    const label = document.createElement('span');
                    label.innerText = y;
                    label.style.cssText = 'position:absolute;left:2px;top:2px;font:bold 11px sans-serif;color:#d00;background:rgba(255,255,255,0.75);padding:0 2px;border-radius:2px;';
                    line.appendChild(label);
                    overlay.appendChild(line);
                }

                if (pt && pt.length === 2) {
                    const dot = document.createElement('div');
                    dot.style.cssText = `position:absolute;left:${pt[0]-7}px;top:${pt[1]-7}px;width:14px;height:14px;border-radius:50%;background:rgba(255,0,0,0.85);border:2px solid #fff;box-shadow:0 0 6px #f00;`;
                    overlay.appendChild(dot);
                }
                document.body.appendChild(overlay);
            }""", list(click_point) if click_point else None)
            shot = await page.screenshot(full_page=False)
            await page.evaluate("""() => {
                const el = document.getElementById('__hajimi_ruler_overlay');
                if (el) el.remove();
            }""")
            return shot
        except Exception:
            return await page.screenshot(full_page=False)

    # ==================== 拟人化网页操作：切换模型 / 额度查询 / 上传参考图 / 输入发送 ====================
    async def _switch_web_model_if_needed(self, page: Page, target_model: str) -> Tuple[bool, str]:
        target_model = self._normalize_model_name(target_model)
        keywords = WEB_MODEL_KEYWORDS.get(target_model, ["hydrogen", "flash"])
        try:
            picker_selectors = [
                'button[data-test-id="bard-mode-menu-button"]',
                'bard-mode-switcher button',
                'input-area-v2 button[aria-haspopup="menu"]',
                'button[aria-label*="model" i]',
                'button[aria-label*="模型" i]',
                'button[aria-label*="切换模式" i]',
                'button[aria-haspopup="menu"]:has-text("Hydrogen")',
                'button[aria-haspopup="menu"]:has-text("Flash")',
                'button[aria-haspopup="menu"]:has-text("Pro")',
                'button[aria-haspopup="menu"]:has-text("Carbon")',
                'button[aria-haspopup="menu"]:has-text("Argon")',
                'button[aria-haspopup="menu"]:has-text("Lite")',
                'button[aria-haspopup="menu"]:has-text("Gemini")',
            ]
            picker_btn = None
            for sel in picker_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    picker_btn = loc
                    break

            if picker_btn is not None:
                cur_btn_raw = (await picker_btn.inner_text()).strip()
                cur_btn_low = cur_btn_raw.lower()
                # 如果当前按钮文字已经匹配目标模型，直接跳过点击
                if target_model == "gemini-hydrogen" and "hydrogen" in cur_btn_low and "lite" not in cur_btn_low:
                    return True, cur_btn_raw.splitlines()[0].strip()
                if target_model == "gemini-flash-lite" and "lite" in cur_btn_low:
                    return True, cur_btn_raw.splitlines()[0].strip()
                if target_model == "gemini-pro" and ("pro" in cur_btn_low or "carbon" in cur_btn_low):
                    return True, cur_btn_raw.splitlines()[0].strip()
                if target_model == "gemini-argon" and "argon" in cur_btn_low:
                    return True, cur_btn_raw.splitlines()[0].strip()

                await picker_btn.click()
                clicked_menu = True
                await asyncio.sleep(1.0)
            else:
                clicked_menu = await page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    for (const b of btns) {
                        if (b.offsetParent === null) continue;
                        const t = (b.innerText || '').trim().toLowerCase();
                        if (['hydrogen', 'flash', 'pro', 'carbon', 'argon', 'lite'].some(k => t.includes(k)) && t.length < 35) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if clicked_menu:
                    await asyncio.sleep(1.0)

            if not clicked_menu:
                return False, "未找到模型切换下拉按钮"

            menu_items = page.locator('[role="menuitem"], [role="menuitemradio"], [role="option"], mat-option, button.mat-mdc-menu-item')
            count = await menu_items.count()

            for i in range(count):
                item = menu_items.nth(i)
                if not await item.is_visible():
                    continue
                raw_text = (await item.inner_text()).strip()
                text = raw_text.lower()

                if target_model == "gemini-hydrogen":
                    if "lite" in text:
                        continue
                    if "hydrogen" in text or "3.8" in text or "flash" in text:
                        await item.click()
                        await asyncio.sleep(1.0)
                        first_line = raw_text.splitlines()[0].strip() if raw_text else target_model
                        logger.info(f"🔄 [Hajimi 浏览器] 已精准命中 Hydrogen 模型: {first_line}")
                        return True, first_line

                if target_model == "gemini-flash-lite" and "lite" not in text and "极速" not in text:
                    continue

                if any(k in text for k in keywords):
                    await item.click()
                    await asyncio.sleep(1.0)
                    first_line = raw_text.splitlines()[0].strip() if raw_text else target_model
                    logger.info(f"🔄 [Hajimi 浏览器] 已在网页端点击切换至模型: {target_model} (命中菜单项: {first_line})")
                    return True, first_line

            await page.keyboard.press("Escape")
            return False, "下拉菜单中未找到匹配的模型项"
        except Exception as e:
            logger.debug(f"[Hajimi 浏览器] 网页模型切换微调跳过: {e}")
            return False, str(e)

    async def _check_usage_quota_and_capture(self, page: Page) -> Tuple[Optional[bytes], str]:
        await self._dismiss_popups(page)
        try:
            gear_selectors = [
                'button[aria-label*="Settings" i]',
                'button[aria-label*="设置" i]',
                'button[mattooltip*="设置" i]',
                'button[mattooltip*="Settings" i]',
                'button[data-test-id*="settings" i]',
                'button:has(mat-icon:has-text("settings"))',
            ]
            clicked_gear = False
            for sel in gear_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    clicked_gear = True
                    await asyncio.sleep(1.0)
                    break

            if not clicked_gear:
                clicked_gear = await page.evaluate("""() => {
                    const icons = Array.from(document.querySelectorAll('mat-icon, .google-symbols, svg'));
                    for (const ic of icons) {
                        const txt = (ic.innerText || ic.getAttribute('data-mat-icon-name') || '').trim().toLowerCase();
                        if (txt === 'settings') {
                            const btn = ic.closest('button, a, [role="button"]');
                            if (btn && btn.offsetParent !== null) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""")
                if clicked_gear:
                    await asyncio.sleep(1.0)

            if not clicked_gear:
                return None, "未能定位到左下角设置小齿轮按钮喵"

            quota_menu_selectors = [
                '[role="menuitem"]:has-text("用量限额")',
                '[role="menuitem"]:has-text("用量")',
                '[role="menuitem"]:has-text("限额")',
                '[role="menuitem"]:has-text("额度")',
                '[role="menuitem"]:has-text("Usage")',
                '[role="menuitem"]:has-text("limit")',
            ]
            clicked_quota_item = False
            for sel in quota_menu_selectors:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    clicked_quota_item = True
                    await asyncio.sleep(2.0)
                    break

            if not clicked_quota_item:
                first_menu_item = page.locator('.mat-mdc-menu-panel [role="menuitem"], [role="menu"] [role="menuitem"]').first
                if await first_menu_item.count() > 0 and await first_menu_item.is_visible():
                    await first_menu_item.click()
                    clicked_quota_item = True
                    await asyncio.sleep(2.0)

            dialog_selectors = [
                'mat-dialog-container',
                '[role="dialog"]',
                '.mat-mdc-dialog-surface',
                '.cdk-overlay-pane:has-text("限额")',
                '.cdk-overlay-pane:has-text("额度")',
                '.cdk-overlay-pane:has-text("Usage")',
                '.cdk-overlay-pane',
            ]
            target_container = None
            quota_text = ""

            for sel in dialog_selectors:
                loc = page.locator(sel).last
                if await loc.count() > 0 and await loc.is_visible():
                    box = await loc.bounding_box()
                    if box and box.get("width", 0) >= 150 and box.get("height", 0) >= 80:
                        target_container = loc
                        try:
                            quota_text = (await loc.inner_text()).strip()
                        except Exception:
                            pass
                        if quota_text:
                            break

            shot_bytes: Optional[bytes] = None
            if target_container:
                try:
                    box = await target_container.bounding_box()
                    if box:
                        pad = 12
                        clip_rect = {
                            "x": max(0, box["x"] - pad),
                            "y": max(0, box["y"] - pad),
                            "width": min(1366 - max(0, box["x"] - pad), box["width"] + pad * 2),
                            "height": min(900 - max(0, box["y"] - pad), box["height"] + pad * 2),
                        }
                        shot_bytes = await page.screenshot(clip=clip_rect)
                    else:
                        shot_bytes = await target_container.screenshot()
                except Exception:
                    shot_bytes = await page.screenshot(full_page=False)
            else:
                shot_bytes = await page.screenshot(full_page=False)

            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            await self._dismiss_popups(page)

            return shot_bytes, quota_text

        except Exception as e:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return None, f"查询额度异常: {e}"

    async def _upload_files_to_page(self, page: Page, file_paths: List[str]):
        if not file_paths:
            return
        try:
            file_input = page.locator('input[type="file"]')
            if await file_input.count() > 0:
                await file_input.first.set_input_files(file_paths)
                logger.info(f"📎 [Hajimi 浏览器] 已通过 input[type=file] 直接挂载 {len(file_paths)} 张参考图")
                await asyncio.sleep(2.5)
                return

            upload_btn_selectors = [
                'button[aria-label*="Upload" i]',
                'button[aria-label*="Add" i]',
                'button[aria-label*="上传" i]',
                'button[aria-label*="添加" i]',
                'button[mattooltip*="Upload" i]',
                'uploader button',
                'button:has(mat-icon:has-text("add"))',
            ]
            for sel in upload_btn_selectors:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    try:
                        async with page.expect_file_chooser(timeout=5000) as fc_info:
                            await btn.click()
                            await asyncio.sleep(0.6)
                            sub_btn = page.locator(
                                '[role="menuitem"]:has-text("Upload"), '
                                '[role="menuitem"]:has-text("上传"), '
                                'button:has-text("Upload file"), '
                                'button:has-text("上传文件")'
                            ).first
                            if await sub_btn.count() > 0 and await sub_btn.is_visible():
                                await sub_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(file_paths)
                        logger.info(f"📎 [Hajimi 浏览器] 已通过模拟点击上传按钮挂载 {len(file_paths)} 张参考图")
                        await asyncio.sleep(2.5)
                        return
                    except Exception:
                        pass

            if await file_input.count() > 0:
                await file_input.first.set_input_files(file_paths)
                await asyncio.sleep(2.5)
                return

            logger.warning("⚠️ [Hajimi 浏览器] 未找到文件上传控件")
        except Exception as e:
            logger.warning(f"[Hajimi 浏览器] 上传参考图异常: {e}")

    async def _extract_latest_gemini_text(self, page: Page, before_resp_count: int = 0) -> str:
        try:
            text = await page.evaluate("""(beforeCount) => {
                const cleanNodeText = (el) => {
                    if (!el) return '';
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll(
                        'message-actions, .response-footer, button, mat-icon, .google-symbols, svg, ' +
                        'model-thoughts, .thoughts-container, [data-test-id*="thought"]'
                    ).forEach(n => n.remove());
                    return (clone.innerText || '').trim();
                };

                const containers = document.querySelectorAll('model-response, [data-message-author-role="model"]');
                if (containers.length > 0) {
                    const lastContainer = containers[containers.length - 1];
                    const contentEl = lastContainer.querySelector('.model-response-text, message-content, .markdown') || lastContainer;
                    const t = cleanNodeText(contentEl);
                    if (t) return t;
                }

                const msgContents = document.querySelectorAll('.model-response-text, message-content, .markdown');
                if (msgContents.length > 0) {
                    const t = cleanNodeText(msgContents[msgContents.length - 1]);
                    if (t) return t;
                }

                const errSelectors = [
                    'mat-snack-bar-container',
                    '[role="alert"]',
                    '.error-message',
                    '.warning-message'
                ];
                for (const esel of errSelectors) {
                    const errEl = document.querySelector(esel);
                    if (errEl && errEl.offsetParent !== null) {
                        const et = (errEl.innerText || '').trim();
                        if (et) return et;
                    }
                }
                return '';
            }""", before_resp_count)
            return (text or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _is_refusal_or_error_text(text: str) -> bool:
        if not text:
            return False
        low = text.lower()
        refusal_keywords = (
            "i can't generate",
            "i cannot generate",
            "i'm unable to",
            "i am unable to",
            "can't create",
            "cannot create",
            "can't help with",
            "third-party content",
            "content policy",
            "safety guidelines",
            "against my guidelines",
            "please edit your prompt",
            "try again later",
            "something went wrong",
            "unable to process",
            "无法生成",
            "不能生成",
            "抱歉，我无法",
            "很抱歉，我不能",
            "违反",
            "内容政策",
            "第三方内容",
            "请修改您的提示",
            "出了点问题",
            "达到上限",
            "额度已用完",
        )
        return any(k in low for k in refusal_keywords)

    async def _submit_prompt_and_wait(
        self,
        page: Page,
        prompt: str,
        file_paths: List[str],
        mode: str,
        timeout_sec: int = 300
    ) -> Tuple[List[Tuple[str, str]], str]:
        resp_selector = 'model-response, message-content, .model-response-text, [data-message-author-role="model"]'

        async with self._page_op_lock:
            await self._dismiss_popups(page)

            try:
                backdrop = page.locator('.image-expansion-dialog-backdrop, .cdk-overlay-backdrop-showing').first
                if await backdrop.count() > 0 and await backdrop.is_visible(timeout=500):
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            before_urls = set(await page.evaluate("""() => {
                const urls = [];
                document.querySelectorAll('img, video, audio, source').forEach(el => {
                    if (el.src) urls.push(el.src);
                    if (el.currentSrc) urls.push(el.currentSrc);
                });
                return urls;
            }"""))
            before_resp_count = await page.locator(resp_selector).count()

            self._intercepted_media.clear()
            self._capturing_media = (mode != "chat")

            if file_paths:
                await self._upload_files_to_page(page, file_paths)

            input_box = page.locator(
                'rich-textarea div[contenteditable="true"], '
                'div.ql-editor[contenteditable="true"], '
                'div[role="textbox"][contenteditable="true"], '
                'textarea[aria-label*="prompt" i]'
            ).first
            await input_box.wait_for(state="visible", timeout=15000)
            await input_box.click()
            await asyncio.sleep(0.3)

            await input_box.fill(prompt)
            await asyncio.sleep(0.6)

            send_btn = page.locator(
                'button[aria-label*="Send" i], '
                'button[aria-label*="发送" i], '
                'button.send-button, '
                'button[mattooltip*="Send" i]'
            ).last
            if await send_btn.count() > 0 and await send_btn.is_visible():
                await send_btn.click()
            else:
                await input_box.press("Enter")

            logger.info(f"🚀 [Hajimi 浏览器] 已点击发送 (模式={mode})，正在等待 Gemini 响应...")

        try:
            start_ts = time.time()
            media_ready_ticks = 0
            text_only_stable_ticks = 0
            last_text_snapshot = ""

            while time.time() - start_ts < timeout_sec:
                await asyncio.sleep(2.0 if mode == "chat" else 2.2)
                elapsed = time.time() - start_ts

                async with self._page_op_lock:
                    busy_state = await page.evaluate("""(beforeRespCount) => {
                        const stopBtns = document.querySelectorAll(
                            'button[aria-label*="Stop" i], button[aria-label*="停止" i], .stop-button, button[mattooltip*="Stop" i]'
                        );
                        for (const btn of stopBtns) {
                            if (btn.offsetParent !== null) return 'stop_btn_visible';
                        }

                        const resps = document.querySelectorAll('model-response, message-content, [data-message-author-role="model"]');
                        if (resps.length <= beforeRespCount) {
                            return 'waiting_new_response_container';
                        }
                        const lastResp = resps[resps.length - 1].closest('model-response') || resps[resps.length - 1];

                        const spinners = lastResp.querySelectorAll(
                            'mat-progress-spinner, mat-spinner, [role="progressbar"], .loading, .skeleton, .shimmer, ' +
                            'image-generation-placeholder, generated-image-placeholder, video-generation-placeholder, ' +
                            'bard-avatar.thinking, .thinking-indicator'
                        );
                        for (const sp of spinners) {
                            if (sp.offsetParent !== null) return 'spinner_visible';
                        }

                        const imgs = lastResp.querySelectorAll('img');
                        for (const img of imgs) {
                            const src = img.src || img.currentSrc || '';
                            if (!src.includes('avatar') && !src.includes('favicon') && !src.includes('gstatic.com')) {
                                if (!img.complete || img.naturalWidth < 150) {
                                    return 'image_still_loading';
                                }
                            }
                        }

                        const footerEl = lastResp.querySelector('message-actions, .response-footer, .actions-container');
                        if (footerEl && footerEl.offsetParent !== null && footerEl.querySelectorAll('button').length >= 2) {
                            return 'idle_with_footer';
                        }

                        const allBtns = Array.from(lastResp.querySelectorAll('button')).filter(b => b.offsetParent !== null);
                        let actionMatchCount = 0;
                        for (const b of allBtns) {
                            const label = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.innerText || '')).toLowerCase();
                            if (
                                label.includes('good') || label.includes('bad') || label.includes('copy') ||
                                label.includes('retry') || label.includes('regenerate') || label.includes('draft') ||
                                label.includes('thumb_up') || label.includes('thumb_down') || label.includes('content_copy') || label.includes('refresh') ||
                                label.includes('不错') || label.includes('不好') || label.includes('赞') || label.includes('踩') ||
                                label.includes('复制') || label.includes('重试') || label.includes('重新生成')
                            ) {
                                actionMatchCount++;
                            }
                        }
                        if (actionMatchCount >= 2) {
                            return 'idle_with_footer';
                        }

                        return 'idle_no_footer';
                    }""", before_resp_count)

                    loaded_dom_media_count = await page.evaluate("""(beforeList) => {
                        const beforeSet = new Set(beforeList);
                        let cnt = 0;
                        const resps = document.querySelectorAll('model-response, message-content, [data-message-author-role="model"]');
                        const root = resps.length > 0 ? (resps[resps.length - 1].closest('model-response') || resps[resps.length - 1]) : document;

                        root.querySelectorAll('img, video, audio, video source, audio source').forEach(el => {
                            const src = el.src || el.currentSrc || '';
                            if (!src || beforeSet.has(src)) return;
                            if (src.includes('avatar') || src.includes('favicon') || src.includes('gstatic.com')) return;
                            const tag = el.tagName.toLowerCase();
                            if (tag === 'img') {
                                if (el.complete && el.naturalWidth >= 200 && el.naturalHeight >= 200) {
                                    cnt++;
                                }
                            } else if (tag === 'video' || tag === 'audio' || tag === 'source') {
                                cnt++;
                            }
                        });
                        return cnt;
                    }""", list(before_urls))

                    cur_text = await self._extract_latest_gemini_text(page, before_resp_count)

                if loaded_dom_media_count > 0 or len(self._intercepted_media) > 0:
                    if busy_state in ("stop_btn_visible", "spinner_visible", "image_still_loading"):
                        media_ready_ticks = 0
                        continue
                    media_ready_ticks += 1
                    if media_ready_ticks >= 2:
                        logger.info(f"✅ [Hajimi 浏览器] 检测到媒体已完全渲染就绪 (耗时 {int(elapsed)}s)！")
                        break
                    continue

                if busy_state in ("stop_btn_visible", "waiting_new_response_container", "spinner_visible", "image_still_loading"):
                    text_only_stable_ticks = 0
                    if cur_text:
                        last_text_snapshot = cur_text
                    continue

                if cur_text:
                    if cur_text == last_text_snapshot:
                        text_only_stable_ticks += 1
                    else:
                        last_text_snapshot = cur_text
                        text_only_stable_ticks = 1

                    min_elapsed = 3 if mode == "chat" else 6

                    if self._is_refusal_or_error_text(cur_text) and text_only_stable_ticks >= 2:
                        logger.info(f"⚠️ [Hajimi 浏览器] 检测到 Gemini 拒绝/错误回复 (耗时 {int(elapsed)}s): {cur_text[:80]}")
                        break

                    if busy_state == "idle_with_footer" and text_only_stable_ticks >= 2 and elapsed >= min_elapsed:
                        logger.info(f"✅ [Hajimi 浏览器] 检测到 Gemini 已完成文本回复 (模式={mode}, 耗时 {int(elapsed)}s): {cur_text[:80]}")
                        break

                    if text_only_stable_ticks >= 4 and elapsed >= (min_elapsed + 4):
                        logger.info(f"✅ [Hajimi 浏览器] 文本回复已完全静止 (模式={mode}, 耗时 {int(elapsed)}s): {cur_text[:80]}")
                        break
                else:
                    if busy_state == "idle_with_footer" and elapsed >= 12:
                        text_only_stable_ticks += 1
                        if text_only_stable_ticks >= 3:
                            break

            async with self._page_op_lock:
                saved_files: List[Tuple[str, str]] = await self._extract_and_save_all_new_media(
                    page,
                    before_urls,
                    file_paths,
                    allow_dom_screenshot_fallback=(mode != "chat")
                )
                final_text = await self._extract_latest_gemini_text(page, before_resp_count)
                if not final_text and last_text_snapshot:
                    final_text = last_text_snapshot
                await self._save_live_browser_state()

            return saved_files, final_text

        finally:
            self._capturing_media = False

    async def _extract_and_save_all_new_media(
        self,
        page: Page,
        before_urls: set,
        input_file_paths: List[str] = None,
        only_last_response: bool = True,
        allow_dom_screenshot_fallback: bool = True
    ) -> List[Tuple[str, str]]:
        """
        从当前页面提取并保存生成的媒体文件（图片/视频/音频），并自动触发 LRU 缓存上限检查。
        """
        saved_results: List[Tuple[str, str]] = []
        seen_hashes = set()

        new_media_Urls: List[str] = await page.evaluate("""(args) => {
            const beforeSet = new Set(args.beforeList);
            const onlyLast = args.onlyLast;
            const found = [];
            const containers = document.querySelectorAll('model-response, message-content, [data-message-author-role="model"]');
            let roots = [document];
            if (containers.length > 0) {
                if (onlyLast) {
                    roots = [containers[containers.length - 1].closest('model-response') || containers[containers.length - 1]];
                } else {
                    roots = Array.from(containers);
                }
            }

            roots.forEach(root => {
                root.querySelectorAll('video, audio, video source, audio source, img').forEach(el => {
                    const src = el.src || el.currentSrc || '';
                    if (!src || beforeSet.has(src)) return;
                    if (src.includes('avatar') || src.includes('favicon') || src.includes('gstatic.com')) return;
                    if (el.tagName.toLowerCase() === 'img' && (el.naturalWidth < 180 || el.naturalHeight < 180)) return;
                    if (!found.includes(src)) found.push(src);
                });
            });
            return found;
        }""", {"beforeList": list(before_urls), "onlyLast": only_last_response})

        input_hashes = set()
        if input_file_paths:
            for fpath in input_file_paths:
                if os.path.exists(fpath):
                    try:
                        with open(fpath, "rb") as f:
                            fb = f.read()
                        input_hashes.add((len(fb), fb[:64]))
                    except Exception:
                        pass

        for m_url in new_media_Urls:
            try:
                raw_bytes: Optional[bytes] = None
                content_type = ""

                b64_data = await page.evaluate("""async (url) => {
                    try {
                        const res = await fetch(url, {credentials: 'include'});
                        if (!res.ok) return null;
                        const blob = await res.blob();
                        return await new Promise((resolve) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                    } catch (e) {
                        return null;
                    }
                }""", m_url)

                if b64_data and "," in b64_data:
                    header, b64_str = b64_data.split(",", 1)
                    content_type = header
                    raw_bytes = base64.b64decode(b64_str)

                if not raw_bytes and not m_url.startswith(("blob:", "data:")):
                    candidates = [m_url]
                    if "googleusercontent.com" in m_url and "=" not in m_url.split("/")[-1]:
                        candidates.insert(0, f"{m_url}=s2048")
                    for fetch_url in candidates:
                        try:
                            api_resp = await self.browser_context.request.get(fetch_url, timeout=30000)
                            if api_resp.status == 200:
                                body = await api_resp.body()
                                if len(body) > 10 * 1024:
                                    raw_bytes = body
                                    content_type = api_resp.headers.get("content-type", "")
                                    break
                        except Exception:
                            pass

                if raw_bytes and len(raw_bytes) > 10 * 1024:
                    sig_hash = (len(raw_bytes), raw_bytes[:64])
                    if sig_hash in input_hashes:
                        logger.info("🛡️ [Hajimi 浏览器] 自动过滤掉用户输入的参考原图，只保留 AI 生成结果~")
                        continue

                    if sig_hash not in seen_hashes:
                        seen_hashes.add(sig_hash)
                        ext = self._detect_media_extension(raw_bytes, content_type)
                        fname = f"{uuid.uuid4().hex}{ext}"
                        fpath = os.path.join(self.cache_dir, fname)
                        with open(fpath, "wb") as f:
                            f.write(raw_bytes)
                        saved_results.append((fname, fpath))
            except Exception as e:
                logger.warning(f"[Hajimi 浏览器] 提取 DOM 媒体失败 ({m_url[:50]}): {e}")

        if not saved_results and self._intercepted_media:
            for raw_bytes, content_type, url in self._intercepted_media:
                sig_hash = (len(raw_bytes), raw_bytes[:64])
                if sig_hash in input_hashes:
                    continue
                if sig_hash not in seen_hashes:
                    seen_hashes.add(sig_hash)
                    ext = self._detect_media_extension(raw_bytes, content_type)
                    fname = f"{uuid.uuid4().hex}{ext}"
                    fpath = os.path.join(self.cache_dir, fname)
                    with open(fpath, "wb") as f:
                        f.write(raw_bytes)
                    saved_results.append((fname, fpath))

        if not saved_results and allow_dom_screenshot_fallback:
            try:
                last_resp = page.locator('model-response, message-content, [data-message-author-role="model"]').last
                if await last_resp.count() > 0:
                    imgs = last_resp.locator('img')
                    img_cnt = await imgs.count()
                    for i in range(img_cnt):
                        img_el = imgs.nth(i)
                        box = await img_el.bounding_box()
                        if box and box.get("width", 0) >= 180 and box.get("height", 0) >= 180:
                            shot_bytes = await img_el.screenshot(type="png")
                            if len(shot_bytes) > 10 * 1024:
                                sig_hash = (len(shot_bytes), shot_bytes[:64])
                                if sig_hash in input_hashes:
                                    continue
                                fname = f"{uuid.uuid4().hex}.png"
                                fpath = os.path.join(self.cache_dir, fname)
                                with open(fpath, "wb") as f:
                                    f.write(shot_bytes)
                                saved_results.append((fname, fpath))
                                logger.info("📸 [Hajimi 浏览器] 已通过 DOM 图片元素无损截图成功提取生成作品！")
            except Exception as e:
                logger.warning(f"[Hajimi 浏览器] 元素级截图兜底异常: {e}")

        if len(saved_results) > 1:
            saved_results = [saved_results[-1]]

        if saved_results:
            self._cleanup_media_cache(protected_paths=[fp for _, fp in saved_results])

        return saved_results

    # ==================== 统一媒体发送与 GIF 智能体积压缩 ====================
    @staticmethod
    def _convert_video_to_gif_if_possible(filepath: str) -> Tuple[str, str]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in (".mp4", ".webm") or not shutil.which("ffmpeg"):
            return os.path.basename(filepath), filepath

        gif_path = os.path.splitext(filepath)[0] + ".gif"
        max_gif_bytes = 6 * 1024 * 1024

        compression_tiers = [
            (10, 360, 128, 6),
            (8,  280, 64,  5),
            (6,  220, 48,  4),
        ]

        for tier_idx, (fps, width, max_colors, max_sec) in enumerate(compression_tiers, start=1):
            try:
                vf_filter = (
                    f"fps={fps},scale={width}:-1:flags=lanczos,"
                    f"split[s0][s1];[s0]palettegen=max_colors={max_colors}:stats_mode=diff[p];"
                    f"[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
                )
                result = subprocess.run(
                    [
                        "ffmpeg", "-y", "-t", str(max_sec), "-i", filepath,
                        "-vf", vf_filter, "-loop", "0", gif_path
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=120,
                    check=False,
                )
                if result.returncode == 0 and os.path.isfile(gif_path):
                    fsize = os.path.getsize(gif_path)
                    logger.info(f"🎞️ [Hajimi GIF压缩] 第 {tier_idx} 档完成: 大小={fsize // 1024}KB (上限 {max_gif_bytes // 1024}KB)")
                    if 0 < fsize <= max_gif_bytes or tier_idx == len(compression_tiers):
                        return os.path.basename(gif_path), gif_path
            except Exception as exc:
                logger.warning(f"[Hajimi] 第 {tier_idx} 档 ffmpeg 转 GIF 异常: {exc}")

        return os.path.basename(filepath), filepath

    async def _send_saved_media_to_qq(
        self,
        event: AstrMessageEvent,
        saved_media_list: List[Tuple[str, str]],
        mode: str,
        custom_done_text: Optional[str] = None
    ):
        sent_paths: List[str] = []
        for filename, saved_path in saved_media_list:
            orig_video_path = saved_path if saved_path.lower().endswith((".mp4", ".webm")) else None

            if mode == "gif" and orig_video_path:
                filename, saved_path = await asyncio.to_thread(self._convert_video_to_gif_if_possible, saved_path)
            elif mode == "music" and saved_path.lower().endswith((".mp4", ".webm")) and shutil.which("ffmpeg"):
                mp3_path = os.path.splitext(saved_path)[0] + ".mp3"
                try:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["ffmpeg", "-y", "-i", saved_path, "-vn", "-acodec", "libmp3lame", "-q:a", "2", mp3_path],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False
                    )
                    if os.path.isfile(mp3_path) and os.path.getsize(mp3_path) > 0:
                        saved_path = mp3_path
                        filename = os.path.basename(mp3_path)
                except Exception:
                    pass

            sent_paths.append(saved_path)
            ext = os.path.splitext(filename)[1].lower()
            if ext in (".mp4", ".webm"):
                if Video is not None and hasattr(Video, "fromFileSystem"):
                    await event.send(event.chain_result([Video.fromFileSystem(saved_path)]))
                else:
                    await event.send(event.plain_result(f"🎬 视频已生成并保存至：{saved_path}"))
            elif ext in (".mp3", ".wav", ".ogg", ".m4a"):
                if Record is not None and hasattr(Record, "fromFileSystem"):
                    await event.send(event.chain_result([Record.fromFileSystem(saved_path)]))
                else:
                    await event.send(event.plain_result(f"🎵 音乐已生成并保存至：{saved_path}"))
            else:
                try:
                    if hasattr(Image, "fromFileSystem"):
                        img_comp = Image.fromFileSystem(saved_path)
                    else:
                        with open(saved_path, "rb") as f:
                            b64_str = base64.b64encode(f.read()).decode("utf-8")
                        img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                    await event.send(event.chain_result([img_comp]))
                except Exception as send_err:
                    logger.warning(f"⚠️ [Hajimi 发送兜底] 发送图片/GIF ({filename}) 触发 QQ 协议异常: {send_err}")
                    if orig_video_path and os.path.exists(orig_video_path) and Video is not None and hasattr(Video, "fromFileSystem"):
                        await event.send(event.plain_result("🐾 喵呜~ QQ 动图通道嫌这张 GIF 太大拒收啦，姬咪立刻为你改发高清原版短视频喵！🎬"))
                        await event.send(event.chain_result([Video.fromFileSystem(orig_video_path)]))
                    else:
                        raise send_err

        # 发送完毕后再次检查并按设定容量清理超出上限的旧缓存
        await asyncio.to_thread(self._cleanup_media_cache, sent_paths)

        done_msg = custom_done_text or random.choice(DONE_REPLIES)
        await event.send(event.plain_result(done_msg))

    @staticmethod
    def _split_long_text(text: str, max_len: int = 3000) -> List[str]:
        """将超长文本按换行符智能切分为多段，避免 QQ 单条消息过长被吞"""
        if len(text) <= max_len:
            return [text]
        chunks: List[str] = []
        remaining = text
        while len(remaining) > max_len:
            split_idx = remaining.rfind("\n", 0, max_len)
            if split_idx < max_len // 2:
                split_idx = max_len
            chunks.append(remaining[:split_idx].rstrip())
            remaining = remaining[split_idx:].lstrip("\n")
        if remaining:
            chunks.append(remaining)
        return chunks

    @staticmethod
    def _detect_media_extension(raw_bytes: bytes, content_type: str = "") -> str:
        if raw_bytes.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WEBP":
            return ".webp"
        if raw_bytes.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if len(raw_bytes) > 12 and raw_bytes[4:8] == b"ftyp":
            brand = raw_bytes[8:12]
            if brand in (b"M4A ", b"M4B "):
                return ".m4a"
            return ".mp4"
        if raw_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            return ".webm"
        if raw_bytes.startswith(b"ID3") or raw_bytes.startswith((b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
            return ".mp3"
        if raw_bytes.startswith(b"RIFF") and raw_bytes[8:12] == b"WAVE":
            return ".wav"
        if raw_bytes.startswith(b"OggS"):
            return ".ogg"

        ct = (content_type or "").lower()
        for ext_key, ext_val in [
            ("gif", ".gif"), ("webp", ".webp"), ("jpeg", ".jpg"), ("jpg", ".jpg"),
            ("mp4", ".mp4"), ("webm", ".webm"), ("mpeg", ".mp3"), ("mp3", ".mp3"),
            ("wav", ".wav"), ("ogg", ".ogg"), ("m4a", ".m4a")
        ]:
            if ext_key in ct:
                return ext_val
        return ".png"

    def _extract_image_url(self, event: AstrMessageEvent) -> str:
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                return getattr(comp, "url", "") or getattr(comp, "file", "")
            elif isinstance(comp, Reply) and getattr(comp, "chain", None):
                for sub_comp in comp.chain:
                    if isinstance(sub_comp, Image):
                        return getattr(sub_comp, "url", "") or getattr(sub_comp, "file", "")
                    elif isinstance(sub_comp, dict) and sub_comp.get("type") == "image":
                        data = sub_comp.get("data", {})
                        return data.get("url") or data.get("file") or ""
        return ""

    def _extract_at_avatars(self, event: AstrMessageEvent, raw_text: str) -> List[Tuple[str, str]]:
        self_id = str(getattr(event.message_obj, "self_id", ""))
        targets = []
        seen_qq = set()

        for comp in event.message_obj.message:
            if isinstance(comp, At):
                qq_str = str(getattr(comp, "qq", "") or getattr(comp, "target", ""))
                name_str = getattr(comp, "name", "") or f"用户({qq_str})"
                if qq_str and qq_str.isdigit() and qq_str != self_id and qq_str not in seen_qq:
                    seen_qq.add(qq_str)
                    targets.append((qq_str, name_str))

        for match in re.finditer(r"@([^\(\s]+)\((\d{5,11})\)", raw_text):
            name_str, qq_str = match.group(1), match.group(2)
            if qq_str != self_id and qq_str not in seen_qq:
                seen_qq.add(qq_str)
                targets.append((qq_str, name_str))

        return targets

    async def _download_to_tempfile(self, session: aiohttp.ClientSession, url_or_path: str) -> str:
        content_type = ""
        if url_or_path.startswith("http"):
            dl_timeout = aiohttp.ClientTimeout(total=45)
            async with session.get(url_or_path, ssl=False, timeout=dl_timeout) as resp:
                if resp.status != 200:
                    raise ValueError(f"下载参考图失败 HTTP {resp.status}")
                raw_bytes = await resp.read()
                content_type = resp.headers.get("content-type", "")
        elif url_or_path.startswith("base64://"):
            raw_bytes = base64.b64decode(url_or_path.replace("base64://", ""))
        elif url_or_path.startswith("data:image/"):
            header, b64_str = url_or_path.split(",", 1)
            content_type = header
            raw_bytes = base64.b64decode(b64_str)
        else:
            clean_path = url_or_path.replace("file://", "")
            with open(clean_path, "rb") as f:
                raw_bytes = f.read()

        ext = self._detect_media_extension(raw_bytes, content_type)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=self.cache_dir)
        tmp.write(raw_bytes)
        tmp.close()
        return tmp.name

    def _build_menu_text(self) -> str:
        preset_info = f"【{self.current_preset}】({STYLE_PRESETS[self.current_preset][1]})" if self.current_preset in STYLE_PRESETS else "【无 (智能自动识别)】"
        status_str = "✅ 真实浏览器已登录并锁定会话" if self.is_logged_in else "⚠️ 浏览器待登录 (仅限主人发 hajimi 登录)"
        queue_info = f"🔥 创作进行中 (后方排队: {len(self._wait_queue)}/{self.MAX_QUEUE_SIZE})" if self._task_running else "🟢 空闲待命"
        master_info = ", ".join(self.admin_qqs) if self.admin_qqs else "未单独绑定(默认使用AstrBot管理员或发 hajimi 绑定主人)"
        file_cnt, total_bytes = self._get_media_cache_stats()
        max_mb = self._get_max_cache_mb()
        cache_limit_str = f"{max_mb}MB (超出自动清理)" if max_mb > 0 else "不限制"

        lines = [
            f"🐾 姬咪全能创作与对话中心 v3.6.0",
            f"👉 状态：{status_str}",
            f"👉 队列：{queue_info}",
            f"👉 主人QQ：{master_info}",
            f"👉 当前模型：【{self.current_model}】",
            f"👉 常驻预设：{preset_info}",
            f"👉 媒体缓存：{total_bytes / 1048576:.1f}MB / {cache_limit_str} (共 {file_cnt} 个文件)\n",
            "📋 【模型切换指令】：",
        ]
        for m_key, desc in MODEL_DESC.items():
            mark = "✅" if m_key == self.current_model else "⬜"
            lines.append(f"{mark} {desc}")

        lines.extend([
            "\n💬 【网页端文本对话模式】：",
            "• 直接提问（自动识别纯文本对话）：hajimi 对比下主流大模型的功能",
            "• 强制对话前缀（跳过预设直接问答）：hajimi 对话 <问题> 或 hajimi 问 <问题>",
            "\n🎨 【图片/改图创作与预设】：",
            "• 直接描述作画：hajimi 画一张流萤的JK图",
            "• 风格预设：换头 | 换脸 | 素描 | 转动漫 | 二次元 | 单色 | 像素画 | 涂鸦 | 水彩 | 赛博 | 黏土 | 贴纸",
            "🎞️ 【GIF动图预设】：照片转gif | 表情包 | 像素动图 | 涂鸦动图 | 动漫动图",
            "🎬 【视频生成预设】：动漫风格 | 像素风 | 涂鸦特效 | 电影感 | 定格动画 | 赛博霓虹",
            "🎵 【音乐生成预设】：纯音乐 | 流行 | 动漫ost | 电音 | 古风 | 钢琴曲",
            "\n🛠️ 【日常运维与缓存管理】：",
            "• 手动清理/调整缓存上限：hajimi 清理缓存 | hajimi 缓存 300",
            "• 提取当前网页/历史对话生成的作品：hajimi 发送 (或 hajimi 发送 gif)",
            "• 查看当前网页实时画面：hajimi 截图",
            "• 查询剩余百分比与周额度：hajimi 额度",
            "• 开启新对话窗口(重置上下文)：hajimi reset",
            "\n🔐 【主人专属管理指令】：",
            "• 绑定主人QQ：hajimi 绑定主人 [QQ号]",
            "• 网页登录与凭证设置：hajimi 登录 | hajimi 根凭证 | hajimi rawcookie | hajimi cookie"
        ])
        return "\n".join(lines)

    def _parse_preset_and_mode(
        self,
        prompt: str,
        has_image: bool = False,
        has_at: bool = False
    ) -> Tuple[str, str, Optional[str], str]:
        """
        智能意图与模式路由：
        1. 显式对话前缀 (`对话`/`聊`/`问`/`chat`/`ask`) -> 强制进入 `chat` 模式，绕过画图预设；
        2. 显式生图前缀 (`画图`/`生图`/`绘图`/`改图`/`draw`/`img`) -> 强制进入 `image` 模式；
        3. 预设关键词 (`STYLE_PRESETS`) 或常驻预设 (`self.current_preset`) -> 进入对应多媒体模式；
        4. 自然语言自动分流：
           - 含音乐/GIF/视频/作画关键词，或携带图片/`@群友`进行改图 -> 进入对应多媒体模式；
           - 其余常规问答（如「对比下主流大模型的功能」）-> 自动进入 `chat` 纯文本对话模式！
        """
        text = prompt.strip()

        # 1. 显式对话模式前缀：hajimi 对话/聊/问/chat/ask <问题>
        chat_prefix_match = re.match(
            r"^(?:对话|聊|聊天|问|提问|问答|chat|ask|text)(?:[:：\s]+|$)(.*)",
            text,
            flags=re.IGNORECASE | re.DOTALL
        )
        if chat_prefix_match:
            clean_q = chat_prefix_match.group(1).strip() or text
            return "chat", clean_q, None, ""

        # 2. 显式生图/改图前缀：hajimi 画图/生图/绘图/改图/draw/img <描述>
        explicit_draw_prefix = re.match(
            r"^(?:画图|生图|绘图|改图|作画|draw|img|image)(?:[:：\s]+|$)(.*)",
            text,
            flags=re.IGNORECASE | re.DOTALL
        )
        if explicit_draw_prefix:
            clean_draw = explicit_draw_prefix.group(1).strip() or text
            return "image", clean_draw, None, ""

        # 3. 匹配风格预设（开头或结尾）
        matched_preset_key = None
        for p_key in sorted(STYLE_PRESETS.keys(), key=len, reverse=True):
            pattern_start = rf"^(?:#|【)?{re.escape(p_key)}(?:】|\s+|$)(.*)"
            m_start = re.match(pattern_start, text, flags=re.IGNORECASE | re.DOTALL)
            if m_start:
                matched_preset_key = p_key
                text = m_start.group(1).strip()
                break

            pattern_end = rf"^(.*?)\s+(?:#|【)?{re.escape(p_key)}(?:】)?$"
            m_end = re.match(pattern_end, text, flags=re.IGNORECASE | re.DOTALL)
            if m_end:
                matched_preset_key = p_key
                text = m_end.group(1).strip()
                break

        if not matched_preset_key and self.current_preset in STYLE_PRESETS:
            matched_preset_key = self.current_preset

        if matched_preset_key:
            mode, display_name, style_instruction = STYLE_PRESETS[matched_preset_key]
            return mode, text, display_name, style_instruction

        # 4. 无预设时的自然语言意图识别
        low = text.lower()

        # 4.1 音乐生成意图
        if any(w in low for w in ("音乐", "歌曲", "伴奏", "作曲", "编曲", "纯音乐", "唱一首", "mp3", "lyria", "bgm", "配乐")):
            return "music", text, None, ""

        # 4.2 GIF 动图意图
        if any(w in low for w in ("gif", "动图", "动态图", "表情包动图", "照片转gif", "动起来")):
            return "gif", text, None, ""

        # 4.3 视频生成意图（避免「对比视频大模型」等纯文本问题误触发）
        if any(w in low for w in ("生成视频", "做个视频", "制作视频", "拍一段", "短视频", "短片", "veo", "mp4", "涂鸦特效", "动画视频")):
            return "video", text, None, ""

        # 4.4 绘画 / 生图 / 改图意图
        draw_keywords = (
            "画一张", "画个", "画幅", "画一幅", "画只", "画条", "画名", "帮我画", "给我画", "请画", "画一个", "画出来", "画成",
            "生图", "画图", "绘图", "作画", "改图", "修图", "p图", "融图", "抠图", "换背景", "换装", "换衣服",
            "重绘", "上色", "线稿", "插画", "立绘", "壁纸", "头像", "海报", "表情包", "四格漫画", "写真",
            "渲染图", "设计图", "logo", "图标", "jk图", "美图", "draw ", "generate an image", "create an image"
        )
        if any(w in low for w in draw_keywords) or re.search(r"(?:^|帮我|给我|请|来一张|来个|生成一张|生成个|制作一张|做一张)画", text):
            return "image", text, None, ""

        # 4.5 携带 @群友 时默认进行头像融图/改图
        if has_at:
            return "image", text, None, ""

        # 4.6 携带参考图片时，若非识图问答则默认改图，若是识图问答则走对话
        if has_image:
            qa_about_img_keywords = (
                "是什么", "什么意思", "识别", "翻译", "总结", "提取", "ocr",
                "看看这是", "分析", "解释", "解答", "做题", "怎么写", "介绍"
            )
            if any(w in low for w in qa_about_img_keywords):
                return "chat", text, None, ""
            return "image", text, None, ""

        # 4.7 其余常规提问全部路由到纯文本对话模式
        return "chat", text, None, ""

    # ==================== 主指令监听入口 ====================
    @filter.regex(r"(?i)^\s*(?:@\S+\s*)*[/!]?hajimi(?:\s+|$)")
    async def hajimi_global_listener(self, event: AstrMessageEvent):
        raw_msg = event.message_str.strip()
        body = re.sub(r"^\s*(?:@\S+\s*)*[/!]?hajimi\s*", "", raw_msg, count=1, flags=re.IGNORECASE | re.DOTALL).strip()

        if not body or body.lower() in {"模型", "model", "models", "status", "菜单", "help", "-m", "预设", "presets"}:
            yield event.plain_result(self._build_menu_text())
            event.stop_event()
            return

        # ==================== 0. 绑定/添加主人 QQ 指令: hajimi 绑定主人 [QQ号] ====================
        bind_master_match = re.match(r"^(?:绑定主人|设置主人|添加主人|admin)\s*(\d*)$", body, re.IGNORECASE)
        if bind_master_match:
            if self.admin_qqs and not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能修改主人名单喵~🐾")
                event.stop_event()
                return
            target_qq = bind_master_match.group(1).strip() or str(event.get_sender_id() or "").strip()
            if not target_qq:
                yield event.plain_result("😿 未能获取到你的 QQ 号喵，请发送 `hajimi 绑定主人 你的QQ号`~")
                event.stop_event()
                return
            if target_qq not in self.admin_qqs:
                self.admin_qqs.append(target_qq)
                self._save_config()
            yield event.plain_result(f"🎉 绑定成功喵！已将 QQ `{target_qq}` 设为姬咪的专属主人，登录与 Cookie 配置指令现已仅对主人开放~🐾")
            event.stop_event()
            return

        # ==================== 0.2 本地多媒体缓存管理指令: hajimi 清理缓存 / hajimi 缓存 [MB] ====================
        cache_cmd_match = re.match(r"^(?:清理缓存|清空缓存|缓存清理|缓存|cache)(?:\s+(\d+))?$", body, re.IGNORECASE)
        if cache_cmd_match:
            new_limit_str = cache_cmd_match.group(1)
            if new_limit_str is not None:
                if not self._is_master(event):
                    yield event.plain_result("😾 哼！只有姬咪的主人才能修改缓存空间上限喵~🐾")
                    event.stop_event()
                    return
                new_mb = int(new_limit_str)
                self.config["max_cache_mb"] = new_mb
                if isinstance(self.astrbot_config, dict):
                    self.astrbot_config["max_cache_mb"] = new_mb
                self._save_config()

            del_cnt, freed_b, rem_b = await asyncio.to_thread(self._cleanup_media_cache)
            file_cnt, _ = self._get_media_cache_stats()
            cur_max = self._get_max_cache_mb()
            limit_desc = f"{cur_max}MB" if cur_max > 0 else "不限制"
            yield event.plain_result(
                f"🧹 【姬咪本地媒体缓存状态】喵：\n"
                f"• 缓存上限：{limit_desc}（可在 AstrBot WebUI 插件设置中随时调整）\n"
                f"• 本次清理：删除 {del_cnt} 个旧文件，释放 {freed_b / 1048576:.1f}MB\n"
                f"• 当前占用：{rem_b / 1048576:.1f}MB（剩余 {file_cnt} 个媒体文件）"
            )
            event.stop_event()
            return

        # ==================== 0.5 重新发送 / 提取当前对话历史作品指令: hajimi 发送 [gif] ====================
        resend_match = re.match(r"^(?:发送|重发|补发|提取|resend|send)(?:\s+(gif|动图|视频|video|音乐|music))?$", body, re.IGNORECASE)
        if resend_match:
            sub_type = (resend_match.group(1) or "").strip().lower()
            target_mode = "gif" if sub_type in ("gif", "动图") else ("music" if sub_type in ("音乐", "music") else "auto")

            if not self.page or self.page.is_closed():
                ok, info = await self._init_browser()
                if not ok and not self.page:
                    yield event.plain_result(f"😿 浏览器尚未启动喵：{info}")
                    event.stop_event()
                    return

            await event.send(event.plain_result("🐾 收到喵！姬咪正在从当前网页对话中为你提取并重新发送生成内容，稍等一下下哦~✨"))
            try:
                async with self._page_op_lock:
                    extracted_files = await self._extract_and_save_all_new_media(
                        self.page, before_urls=set(), input_file_paths=None, only_last_response=False
                    )
                    page_text = await self._extract_latest_gemini_text(self.page, 0)

                if not extracted_files and self.last_generated_files:
                    valid_cached = [(fn, fp) for fn, fp in self.last_generated_files if os.path.exists(fp)]
                    if valid_cached:
                        extracted_files = valid_cached
                        if target_mode == "auto":
                            target_mode = self.last_generated_mode

                if extracted_files:
                    send_mode = target_mode if target_mode != "auto" else "image"
                    await self._send_saved_media_to_qq(
                        event,
                        extracted_files,
                        mode=send_mode,
                        custom_done_text="✨ 哒哒！姬咪已经把当前对话里的作品重新发送出来啦喵，请查收~🐾"
                    )
                elif page_text:
                    for chunk in self._split_long_text(page_text):
                        await event.send(event.plain_result(chunk))
                else:
                    yield event.plain_result("😿 当前网页对话框里既没有找到生成的媒体文件，也没有找到历史缓存喵（可先发 `hajimi 截图` 看看当前停留在哪个页面哦）~")
            except Exception as e:
                logger.error(f"[Hajimi 发送] 提取重发异常:\n{traceback.format_exc()}")
                yield event.plain_result(f"😿 重新发送时出小差错了喵：{type(e).__name__}: {e}")
            event.stop_event()
            return

        # ==================== 1. 网页交互式原生登录入口（仅限主人）: hajimi 登录 / login ====================
        if body.lower() in {"登录", "login", "signin", "网页登录"}:
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能操作网页登录喵~（若你是主人但尚未绑定，请先发一次 `hajimi 绑定主人`）🐾")
                event.stop_event()
                return
            if self._task_running:
                yield event.plain_result("🐾 姬咪正在执行任务喵，请等当前任务完成后再操作登录哦~")
                event.stop_event()
                return
            if not self.page or self.page.is_closed():
                await self._init_browser()
            if not self.page:
                yield event.plain_result("😿 浏览器启动失败喵，请检查容器环境！")
                event.stop_event()
                return
            await event.send(event.plain_result("🔐 正在启用 Stealth 反指纹伪装打开 Google 登录页喵，请稍候约 3 秒..."))
            async with self._page_op_lock:
                await self.page.goto("https://www.google.com/?hl=zh-CN", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(1.5)
                login_url = "https://accounts.google.com/ServiceLogin?hl=zh-CN&continue=https%3A%2F%2Fgemini.google.com%2Fapp"
                await self.page.goto(login_url, wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(3)
                shot_bytes = await self._screenshot_with_ruler(self.page)
            b64_str = base64.b64encode(shot_bytes).decode("utf-8")
            img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
            yield event.chain_result([
                img_comp,
                Plain(
                    "🔐 【Google 反指纹登录向导】喵：\n"
                    "1️⃣ 发送 `hajimi 输入 你的谷歌邮箱`\n"
                    "2️⃣ 看到密码框后，发送 `hajimi 输入 你的密码`\n"
                    "💡 如果 Google 依然提示「此浏览器可能不安全」，请直接使用 **100% 永不掉线的【双域根凭证克隆法】**：\n"
                    "• 在电脑浏览器打开 `https://accounts.google.com` 按 F12 复制整串 Cookie 发：`hajimi 根凭证 <内容>`\n"
                    "• 再把 Gemini 页的 Cookie 发：`hajimi rawcookie <内容>`"
                )
            ])
            event.stop_event()
            return

        # ==================== 1.2 注入 accounts.google.com 专属根凭证（仅限主人） ====================
        acc_cookie_match = re.match(r"^(?:根凭证|accountcookie|acccookie|导入)\s+(.+)$", body, re.IGNORECASE | re.DOTALL)
        if acc_cookie_match:
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能设置根凭证 Cookie 喵~🐾")
                event.stop_event()
                return
            raw_input = acc_cookie_match.group(1).strip().strip("'\"")
            self._reload_disk_config()
            if raw_input.startswith("[") and raw_input.endswith("]"):
                try:
                    parsed_json = json.loads(raw_input)
                    with open(self.imported_json_cookie_path, "w", encoding="utf-8") as f:
                        json.dump(parsed_json, f, ensure_ascii=False, indent=2)
                    await event.send(event.plain_result("📂 收到 Cookie-Editor 全量 JSON 凭证喵！正在注入全域名根凭证并重启浏览器..."))
                except Exception as e:
                    yield event.plain_result(f"😿 JSON 格式解析失败喵: {e}")
                    event.stop_event()
                    return
            else:
                self.config["accounts_cookie_str"] = raw_input
                self._save_config()
                await event.send(event.plain_result("🔑 收到 `accounts.google.com` 根凭证喵！正在绑定长效换票令牌并重启浏览器..."))

            ok, msg = await self._init_browser(force_restart=True, force_reinject_cookies=True)
            if ok:
                yield event.plain_result(f"🎉 根凭证绑定成功喵！现在浏览器拥有完整的 `accounts.google.com` 换票权限，静置再久也不会掉线啦！\n{msg}")
            else:
                yield event.plain_result(f"ℹ️ 根凭证已保存！如果尚未注入 Gemini 主站 Cookie，请接着发送一次 `hajimi rawcookie <在gemini页面复制的Cookie>` 即可完成合体喵！\n({msg})")
            event.stop_event()
            return

        # ==================== 1.5 快捷查看剩余额度与周限额指令: hajimi 额度 ====================
        if body.lower() in {"额度", "限额", "用量", "用量限额", "剩余额度", "周额度", "quota", "usage", "limit"}:
            if self._task_running:
                yield event.plain_result("🐾 姬咪正在全力处理任务中喵，为避免打断当前生成，请等当前任务完成后再查额度哦（可先发 `hajimi 截图` 看进度喵）~")
                event.stop_event()
                return
            if not self.page or self.page.is_closed() or not self.is_logged_in:
                ok, info = await self._init_browser()
                if not ok and not self.page:
                    yield event.plain_result(f"😿 浏览器尚未就绪喵：{info}")
                    event.stop_event()
                    return
            await event.send(event.plain_result("📊 收到喵！姬咪正在点击左下角「设置 ⚙️ -> 用量限额」为你查询剩余百分比与周额度，稍等两秒钟哦~🐾"))
            async with self._page_op_lock:
                shot_bytes, quota_summary = await self._check_usage_quota_and_capture(self.page)
                try:
                    await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(1.5)
                    self.persistent_chat_url = "https://gemini.google.com/app"
                    self._save_config()
                except Exception:
                    pass

            if shot_bytes:
                b64_str = base64.b64encode(shot_bytes).decode("utf-8")
                img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                yield event.chain_result([img_comp])
            else:
                yield event.plain_result(f"📊 【姬咪用量与周限额查询】：\n{quota_summary}")
            event.stop_event()
            return

        # ==================== 2. 网页实时截图诊断指令: hajimi 截图 ====================
        if body.lower() in {"截图", "screenshot", "screen", "画面", "看看网页"}:
            if not self.page or self.page.is_closed():
                ok, info = await self._init_browser()
                if not ok and not self.page:
                    yield event.plain_result(f"😿 浏览器尚未启动喵：{info}")
                    event.stop_event()
                    return
            try:
                async with self._page_op_lock:
                    if self._task_running:
                        shot_bytes = await self.page.screenshot(full_page=False)
                        is_ok = self.is_logged_in
                    else:
                        is_ok = await self._check_page_login_state(self.page)
                        self.is_logged_in = is_ok
                        if is_ok:
                            await self._save_live_browser_state()
                            shot_bytes = await self.page.screenshot(full_page=False)
                        else:
                            shot_bytes = await self._screenshot_with_ruler(self.page)

                b64_str = base64.b64encode(shot_bytes).decode("utf-8")
                img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                run_tip = f"🎬 正在后台运行任务中 (后方排队: {len(self._wait_queue)}/{self.MAX_QUEUE_SIZE})" if self._task_running else ("✅ 已就绪 (可发 `hajimi 点击 <左侧历史标题>` + `hajimi 发送` 提取旧作品)" if is_ok else "❌ 待登录 (已开启红字坐标标尺)")
                yield event.chain_result([
                    img_comp,
                    Plain(f"📸 当前浏览器实时画面喵~\n🔗 URL: {self.page.url}\n🐾 状态: {run_tip}")
                ])
            except Exception as e:
                yield event.plain_result(f"😿 截图失败喵: {e}")
            event.stop_event()
            return

        # ==================== 3. 重置/新建对话窗口指令: hajimi reset / 新对话 ====================
        if body.lower() in {"reset", "重置", "新对话", "清空", "new"}:
            if self._task_running:
                yield event.plain_result("🐾 姬咪正在执行任务中喵，请等当前任务完成后再重置对话框哦~")
                event.stop_event()
                return
            self.persistent_chat_url = "https://gemini.google.com/app"
            self._save_config()
            if self.page and not self.page.is_closed():
                async with self._page_op_lock:
                    await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3)
                    await self._switch_web_model_if_needed(self.page, self.current_model)
            yield event.plain_result(f"🐾 已开启全新的 Gemini 网页对话框喵（当前模型：【{self.current_model}】）！~✨")
            event.stop_event()
            return

        # ==================== 3.5 在线注入完整整串 Cookie（仅限主人）: hajimi rawcookie <整串Cookie> ====================
        raw_cookie_match = re.match(r"^(?:rawcookie|fullcookie|整串cookie)\s+(.+)$", body, re.IGNORECASE | re.DOTALL)
        if raw_cookie_match:
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能设置 Cookie 喵~🐾")
                event.stop_event()
                return
            raw_val = raw_cookie_match.group(1).strip().strip("'\"")
            self._reload_disk_config()
            if raw_val.startswith("[") and raw_val.endswith("]"):
                try:
                    parsed_json = json.loads(raw_val)
                    with open(self.imported_json_cookie_path, "w", encoding="utf-8") as f:
                        json.dump(parsed_json, f, ensure_ascii=False, indent=2)
                except Exception:
                    self.config["raw_cookie_str"] = raw_val
            else:
                self.config["raw_cookie_str"] = raw_val
            self._save_config()
            await event.send(event.plain_result("🍪 收到完整 Cookie 字符串喵！正在注入 365 天长效凭证并重启浏览器..."))
            ok, msg = await self._init_browser(force_restart=True, force_reinject_cookies=True)
            if ok:
                yield event.plain_result(f"🎉 完整 Cookie 登录成功喵！\n{msg}")
            else:
                yield event.plain_result(f"😿 注入后提示：{msg}")
            event.stop_event()
            return

        # ==================== 3.6 远程坐标点击指令: hajimi 坐标 <X> <Y> ====================
        coord_match = re.match(r"^(?:坐标|xy|点坐标|clickxy)\s+(\d+)\s*[,，\s]\s*(\d+)$", body, re.IGNORECASE)
        if coord_match and self.page and not self.page.is_closed():
            if not self.is_logged_in and not self._is_master(event):
                yield event.plain_result("😾 当前处于登录页面，只有主人才能操作坐标点击喵~🐾")
                event.stop_event()
                return
            x, y = int(coord_match.group(1)), int(coord_match.group(2))
            try:
                async with self._page_op_lock:
                    await self.page.mouse.move(x, y, steps=12)
                    await asyncio.sleep(0.15)
                    await self.page.mouse.down()
                    await asyncio.sleep(random.uniform(0.06, 0.14))
                    await self.page.mouse.up()
                    await asyncio.sleep(3.5)
                    self.is_logged_in = await self._check_page_login_state(self.page)
                    if self.is_logged_in:
                        await self._save_live_browser_state()
                    shot_bytes = await self._screenshot_with_ruler(self.page, click_point=(x, y))
                b64_str = base64.b64encode(shot_bytes).decode("utf-8")
                img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                status_tip = f"🖱️ 已点击坐标 ({x}, {y}) 喵（红点处）！若已进入历史对话，发送 `hajimi 发送` 即可提取里面的作品发送到 QQ 哦~🐾"
                yield event.chain_result([img_comp, Plain(status_tip)])
            except Exception as e:
                yield event.plain_result(f"😿 坐标点击失败喵: {e}")
            event.stop_event()
            return

        # ==================== 3.7 远程文字点击指令: hajimi 点击 <文字> ====================
        click_match = re.match(r"^(?:点击|click)\s+(.+)$", body, re.IGNORECASE)
        if click_match and self.page and not self.page.is_closed():
            if not self.is_logged_in and not self._is_master(event):
                yield event.plain_result("😾 当前处于登录页面，只有主人才能操作点击喵~🐾")
                event.stop_event()
                return
            target_text = click_match.group(1).strip()
            try:
                async with self._page_op_lock:
                    if target_text.lower() in {"人机", "人机验证", "机器人", "recaptcha", "checkbox", "复选框"}:
                        clicked_cb = False
                        for frame in self.page.frames:
                            cb = frame.locator('#recaptcha-anchor, .recaptcha-checkbox-border, [role="checkbox"]').first
                            if await cb.count() > 0 and await cb.is_visible():
                                await cb.click()
                                clicked_cb = True
                                break
                        if not clicked_cb:
                            raise ValueError("未检测到可见的人机验证复选框，请看图使用 `hajimi 坐标 X Y` 点击")
                    else:
                        loc = self.page.get_by_text(target_text, exact=False).first
                        await loc.click(timeout=6000)
                    await asyncio.sleep(3.0)
                    self.is_logged_in = await self._check_page_login_state(self.page)
                    if self.is_logged_in:
                        await self._save_live_browser_state()
                        shot_bytes = await self.page.screenshot(full_page=False)
                    else:
                        shot_bytes = await self._screenshot_with_ruler(self.page)
                b64_str = base64.b64encode(shot_bytes).decode("utf-8")
                img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                status_tip = f"🖱️ 已点击「{target_text}」喵！当前画面如上~（如需把该对话里的作品发出来，直接发 `hajimi 发送` 或 `hajimi 发送 gif` 即可喵！）"
                yield event.chain_result([img_comp, Plain(status_tip)])
            except Exception as e:
                yield event.plain_result(f"😿 点击「{target_text}」失败喵: {e}\n（可看截图红字标尺，直接发送 `hajimi 坐标 X Y` 点击对应位置）")
            event.stop_event()
            return

        # ==================== 3.8 远程输入指令（仅限主人登录使用）: hajimi 输入 <内容> ====================
        type_match = re.match(r"^(?:输入|type)\s+(.+)$", body, re.IGNORECASE)
        if type_match and self.page and not self.page.is_closed():
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能使用远程输入指令喵~🐾")
                event.stop_event()
                return
            input_val = type_match.group(1).strip()
            try:
                async with self._page_op_lock:
                    visible_inputs = self.page.locator(
                        'input[type="email"]:visible, input[type="password"]:visible, '
                        'input[type="tel"]:visible, input[type="text"]:visible, '
                        'input[type="number"]:visible, input:not([type="hidden"]):visible'
                    )
                    if await visible_inputs.count() > 0:
                        target_in = visible_inputs.first
                        await target_in.click()
                        await asyncio.sleep(0.2)
                        await target_in.fill("")
                        await target_in.type(input_val, delay=random.randint(45, 95))
                    else:
                        await self.page.keyboard.type(input_val, delay=65)

                    await asyncio.sleep(0.4)
                    await self.page.keyboard.press("Enter")
                    await asyncio.sleep(4.5)

                    self.is_logged_in = await self._check_page_login_state(self.page)
                    if self.is_logged_in:
                        await self._save_live_browser_state()
                        shot_bytes = await self.page.screenshot(full_page=False)
                    else:
                        shot_bytes = await self._screenshot_with_ruler(self.page)
                b64_str = base64.b64encode(shot_bytes).decode("utf-8")
                img_comp = Image.fromBase64(b64_str) if hasattr(Image, "fromBase64") else Image.fromURL(f"base64://{b64_str}")
                if self.is_logged_in:
                    yield event.chain_result([img_comp, Plain("🎉 恭喜喵！Google 网页端原生登录成功，完整的 365 天设备凭证已永久保存在本地浏览器目录中，再也不会隔几小时掉线啦~🐾")])
                else:
                    yield event.chain_result([img_comp, Plain("⌨️ 已输入并按下回车喵！请查看上方最新网页画面继续下一步~")])
            except Exception as e:
                yield event.plain_result(f"😿 输入失败喵: {e}")
            event.stop_event()
            return

        # ==================== 4. 在线注入 Cookie 并重启浏览器（仅限主人）: hajimi cookie <1PSID> [1PSIDTS] ====================
        cookie_match = re.match(r"^cookie\s+(\S+)(?:\s+(\S+))?$", body, re.IGNORECASE)
        if cookie_match:
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能设置 Cookie 喵~（若你是主人，请先发 `hajimi 绑定主人`）🐾")
                event.stop_event()
                return
            self._reload_disk_config()
            self.config["secure_1psid"] = cookie_match.group(1).strip()
            if cookie_match.group(2):
                self.config["secure_1psidts"] = cookie_match.group(2).strip()
            self._save_config()
            await event.send(event.plain_result("🍪 收到新 Cookie 喵！正在注入真实 Chromium 浏览器并打开 Gemini 网页，请稍候约 5~10 秒..."))
            ok, msg = await self._init_browser(force_restart=True, force_reinject_cookies=True)
            if ok:
                yield event.plain_result(f"🎉 真实浏览器登录成功喵！\n{msg}")
            else:
                yield event.plain_result(f"😿 浏览器打开后未检测到输入框喵：{msg}")
            event.stop_event()
            return

        # ==================== 5. 在线更新 Proxy 并重启浏览器（仅限主人）: hajimi proxy <http://ip:port 或 clear> ====================
        proxy_match = re.match(r"^proxy\s+(\S+)$", body, re.IGNORECASE)
        if proxy_match:
            if not self._is_master(event):
                yield event.plain_result("😾 哼！只有姬咪的主人才能修改代理配置喵~🐾")
                event.stop_event()
                return
            self._reload_disk_config()
            p_val = proxy_match.group(1).strip().strip("[]'\"")
            self.config["proxy"] = "" if p_val.lower() in {"clear", "none", "off", "取消", "无"} else p_val
            self._save_config()
            await event.send(event.plain_result(f"🌐 浏览器代理已设为 `{self.config['proxy'] or '直连'}` 喵！正在重启浏览器..."))
            ok, msg = await self._init_browser(force_restart=True)
            if ok:
                yield event.plain_result(f"🎉 代理更新且浏览器连接成功喵！\n{msg}")
            else:
                yield event.plain_result(f"😿 浏览器重连提示：{msg}")
            event.stop_event()
            return

        # ==================== 6. 常驻预设切换指令: hajimi 预设 <预设名/取消> ====================
        preset_cmd_match = re.match(r"^(?:预设|preset)\s+(\S+)$", body, re.IGNORECASE)
        if preset_cmd_match:
            p_arg = preset_cmd_match.group(1).strip().lower()
            if p_arg in {"取消", "无", "none", "off", "clear", "重置"}:
                self.current_preset = ""
                self._save_config()
                yield event.plain_result("🐾 已取消常驻预设喵！现在恢复智能自动识别模式啦~✨")
            elif p_arg in STYLE_PRESETS:
                self.current_preset = p_arg
                self._save_config()
                _, p_title, _ = STYLE_PRESETS[p_arg]
                yield event.plain_result(f"🐾 常驻预设已锁定为【{p_title}】喵！之后发创作内容会自动套用该风格（发 `hajimi 对话 <问题>` 仍可直接文本问答哦）~")
            else:
                yield event.plain_result(f"😿 未找到名为「{p_arg}」的预设喵！请发送「hajimi 菜单」查看支持的预设列表。")
            event.stop_event()
            return

        # ==================== 7. 模型切换指令: hajimi 1/2/3/4 [可选后续内容] ====================
        switch_match = re.match(r"^(?:-m\s+|切换\s*|用\s*)?(\S+)(?:\s+(.*))?$", body, re.DOTALL)
        if switch_match:
            first_token = switch_match.group(1).lower().strip()
            rest_prompt = (switch_match.group(2) or "").strip()
            if first_token in MODEL_ALIASES:
                new_model = MODEL_ALIASES[first_token]
                self.current_model = new_model
                self._save_config()
                matched_label = new_model
                if self.page and not self.page.is_closed() and not self._task_running:
                    async with self._page_op_lock:
                        ok_sw, sw_label = await self._switch_web_model_if_needed(self.page, new_model)
                        if ok_sw:
                            matched_label = f"{new_model} ({sw_label})"
                if not rest_prompt:
                    yield event.plain_result(f"🐾 切换成功喵！以后姬咪在网页端默认都用【{matched_label}】啦~✨")
                    event.stop_event()
                    return
                body = rest_prompt

        # 确保浏览器已启动并处于登录状态
        if not self.page or self.page.is_closed() or not self.is_logged_in:
            ok, msg = await self._init_browser()
            if not ok:
                yield event.plain_result(f"😿 姬咪的真实浏览器还没准备好喵：\n{msg}")
                event.stop_event()
                return

        # ==================== 8. 排队调度机制（上限排队 2 个指令） ====================
        was_queued = False
        if self._task_running:
            if len(self._wait_queue) >= self.MAX_QUEUE_SIZE:
                full_msg = random.choice(QUEUE_FULL_REPLIES).format(max_q=self.MAX_QUEUE_SIZE)
                yield event.plain_result(full_msg)
                event.stop_event()
                return

            my_turn_event = asyncio.Event()
            self._wait_queue.append(my_turn_event)
            q_pos = len(self._wait_queue)
            was_queued = True
            queue_msg = random.choice(QUEUE_WAIT_REPLIES).format(pos=q_pos, max_q=self.MAX_QUEUE_SIZE)
            await event.send(event.plain_result(queue_msg))

            await my_turn_event.wait()
        else:
            self._task_running = True

        temp_files: List[str] = []
        try:
            if was_queued:
                next_msg = random.choice(NEXT_TASK_REPLIES)
                await event.send(event.plain_result(next_msg))

            img_url = self._extract_image_url(event)
            at_targets = self._extract_at_avatars(event, body)
            mode, clean_user_prompt, preset_title, style_instruction = self._parse_preset_and_mode(
                body,
                has_image=bool(img_url),
                has_at=bool(at_targets)
            )

            if mode == "chat":
                wait_msg = random.choice(WAIT_CHAT_REPLIES)
                await event.send(event.plain_result(wait_msg))
            else:
                if mode == "music":
                    wait_msg = random.choice(WAIT_MUSIC_REPLIES)
                elif mode in ("video", "gif"):
                    wait_msg = random.choice(WAIT_VIDEO_REPLIES)
                elif img_url or at_targets:
                    wait_msg = random.choice(WAIT_EDIT_REPLIES)
                else:
                    wait_msg = random.choice(WAIT_DRAW_REPLIES)

                if preset_title:
                    wait_msg = f"✨ 已套用预设【{preset_title}】\n{wait_msg}"

                cost_hint = QUOTA_COST_HINTS.get(mode, QUOTA_COST_HINTS["image"])
                wait_msg = f"{wait_msg}\n{cost_hint}"
                await event.send(event.plain_result(wait_msg))

                # 在每次进行生图/视频等创作指令前，自动打开一个新的对话框 (goto /app) 并确保模型对齐
                if self.page and not self.page.is_closed():
                    try:
                        async with self._page_op_lock:
                            await self.page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=45000)
                            await asyncio.sleep(2)
                            await self._switch_web_model_if_needed(self.page, self.current_model)
                            self.persistent_chat_url = "https://gemini.google.com/app"
                            self._save_config()
                    except Exception as e:
                        logger.warning(f"[Hajimi 浏览器] 每次创作前自动打开新对话框异常: {e}")

            req_timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=req_timeout) as session:
                if img_url and at_targets:
                    target_qq, target_name = at_targets[0]
                    qq_avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
                    avatar_tmp = await self._download_to_tempfile(session, qq_avatar_url)
                    temp_files.append(avatar_tmp)

                    main_tmp = await self._download_to_tempfile(session, img_url)
                    temp_files.append(main_tmp)

                    try:
                        replaced_prompt = re.sub(
                            r"@[^\(\s]+\(\d+\)|@\S+",
                            "the character/person shown in the first image (avatar reference)",
                            clean_user_prompt
                        ).strip() or "Integrate the character from the first image into the second image."

                        base_prompt = (
                            f"{replaced_prompt}\n"
                            f"(Important: The FIRST attached image is the character reference of '{target_name}'. "
                            f"The SECOND attached image is the base target scene. "
                            f"Please extract the face and head features from the FIRST image and seamlessly blend/replace them onto the main person in the SECOND image!)"
                        )
                    except Exception as avatar_err:
                        logger.warning(f"[Hajimi] 获取群友头像失败，退化为单图处理: {avatar_err}")
                        base_prompt = clean_user_prompt
                elif not img_url and at_targets:
                    target_qq, _ = at_targets[0]
                    qq_avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={target_qq}&s=640"
                    avatar_tmp = await self._download_to_tempfile(session, qq_avatar_url)
                    temp_files.append(avatar_tmp)
                    replaced_prompt = re.sub(r"@[^\(\s]+\(\d+\)|@\S+", "the character in this image", clean_user_prompt).strip()
                    base_prompt = replaced_prompt or "Transform the character shown in this attached image."
                elif img_url:
                    main_tmp = await self._download_to_tempfile(session, img_url)
                    temp_files.append(main_tmp)
                    base_prompt = clean_user_prompt or ("请分析并描述这张图片的内容。" if mode == "chat" else "Please process and transform this attached image.")
                else:
                    base_prompt = clean_user_prompt

            mode_hints = {
                "chat": "",
                "gif": " (Important: Please generate an animated GIF or short animation clip, not a static image!)",
                "video": " (Important: Please generate a video using your video generation tool!)",
                "music": " (Important: Please generate an audio/music track using your music generation tool!)",
                "image": " (Important: Please generate or edit the image directly!)"
            }
            prompt_parts = [p for p in [style_instruction, base_prompt, mode_hints.get(mode, "")] if p]
            final_prompt = "\n".join(prompt_parts).strip()

            media_timeout = max(60, int(self.config.get("media_timeout", 240)))
            logger.info(f"🎯 [Hajimi 真实网页操作] 模式={mode} | 预设={preset_title or '无'} | 模型={self.current_model} | 附件数={len(temp_files)} | Prompt={final_prompt[:100]}")

            saved_media_list, reply_text = await self._submit_prompt_and_wait(
                self.page,
                final_prompt,
                temp_files,
                mode=mode,
                timeout_sec=media_timeout
            )

            clean_reply = re.sub(r"<think>.*?</think>", "", reply_text or "", flags=re.DOTALL).strip()

            if mode == "chat":
                # 纯文本对话模式：直接将 Gemini 网页回复全文转发到 QQ
                if clean_reply:
                    for chunk in self._split_long_text(clean_reply, max_len=3000):
                        await event.send(event.plain_result(chunk))
                    if saved_media_list:
                        self.last_generated_files = list(saved_media_list)
                        self.last_generated_mode = "image"
                        await self._send_saved_media_to_qq(event, saved_media_list, mode="image")
                elif saved_media_list:
                    self.last_generated_files = list(saved_media_list)
                    self.last_generated_mode = "image"
                    await self._send_saved_media_to_qq(event, saved_media_list, mode="image")
                else:
                    fail_msg = random.choice(FAIL_REPLIES).format(reason="网页端超时未返回文字回复，可发「hajimi 截图」查看当前画面喵")
                    yield event.plain_result(fail_msg)
            else:
                # 多媒体创作模式：发送生成的图片/GIF/视频/音乐
                if saved_media_list:
                    self.last_generated_files = list(saved_media_list)
                    self.last_generated_mode = mode
                    await self._send_saved_media_to_qq(event, saved_media_list, mode=mode)
                else:
                    if not clean_reply:
                        clean_reply = "网页端超时未返回文字说明，可发「hajimi 截图」查看当前画面喵"
                    fail_msg = random.choice(FAIL_REPLIES).format(reason=clean_reply[:500])
                    yield event.plain_result(fail_msg)

        except Exception as e:
            logger.error(f"[Hajimi 浏览器] 执行异常: {traceback.format_exc()}")
            err_reason = f"{type(e).__name__}: {str(e)}"
            fail_msg = random.choice(FAIL_REPLIES).format(reason=err_reason)
            yield event.plain_result(fail_msg)
        finally:
            for f_path in temp_files:
                if os.path.exists(f_path):
                    try:
                        os.remove(f_path)
                    except Exception:
                        pass
            self._intercepted_media.clear()
            if self.page and not self.page.is_closed():
                try:
                    async with self._page_op_lock:
                        await self.page.evaluate("() => { if (window.gc) window.gc(); }")
                except Exception:
                    pass

            if self._wait_queue:
                next_ev = self._wait_queue.popleft()
                next_ev.set()
            else:
                self._task_running = False

        event.stop_event()