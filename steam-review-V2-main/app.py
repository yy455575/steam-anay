# app.py
# LagoFast 游戏分析辅助
# 本次修复：
# 1. 语言评论数据明细标题靠左对齐
# 2. Tab3 竞品检测逻辑修正（wemod/fling/flyy检测地址和判断条件）

import os
from pathlib import Path
import streamlit as st
import httpx
import json
import pandas as pd
import plotly.graph_objects as go
from openai import OpenAI
import time
import random
import re
from datetime import datetime
from io import BytesIO

from steam_intel.country_metrics import CountryDistribution, MetricStatus
from wishlist_tools import (
    fetch_gamalytic_active_users_regions,
    fetch_gamalytic_game_details,
    fetch_gamalytic_wishlist_country_distribution,
    fetch_popular_wishlist_apps,
    gamalytic_country_data_frame,
    gamalytic_summary_frame,
    search_steam_games,
)

# ============================================================
# 常量配置
# ============================================================
PAGE_PASSWORD = os.environ.get("LAGOFAST_PAGE_PASSWORD", "")
# 代理凭据只从运行环境读取，禁止提交到源码或导出文件。
FIXED_PROXY = os.environ.get("LAGOFAST_PROXY", "")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

STEAM_LANGUAGES = {
    "schinese": "简中", "tchinese": "繁中", "english": "英语",
    "japanese": "日语", "koreana": "韩语", "russian": "俄语",
    "german": "德语", "french": "法语", "spanish": "西语(西班牙)",
    "latam": "西语(拉丁)", "portuguese": "葡语",
    "brazilian": "巴葡", "italian": "意大利语", "polish": "波兰语",
    "turkish": "土耳其语", "thai": "泰语", "dutch": "荷兰语",
    "czech": "捷克语", "hungarian": "匈牙利语", "romanian": "罗马尼亚语",
    "swedish": "瑞典语", "norwegian": "挪威语", "danish": "丹麦语",
    "finnish": "芬兰语", "ukrainian": "乌克兰语", "bulgarian": "保加利亚语",
    "greek": "希腊语", "vietnamese": "越南语", "arabic": "阿拉伯语",
    "indonesian": "印尼语",
}

LANGUAGE_NAME_TO_CODE = {
    "arabic": "arabic", "bulgarian": "bulgarian",
    "simplified chinese": "schinese", "chinese simplified": "schinese",
    "schinese": "schinese", "chinese (simplified)": "schinese",
    "traditional chinese": "tchinese", "chinese traditional": "tchinese",
    "tchinese": "tchinese", "chinese (traditional)": "tchinese",
    "czech": "czech", "danish": "danish", "dutch": "dutch",
    "english": "english", "finnish": "finnish", "french": "french",
    "german": "german", "greek": "greek", "hungarian": "hungarian",
    "indonesian": "indonesian", "italian": "italian", "japanese": "japanese",
    "korean": "koreana", "koreana": "koreana",
    "spanish - latin america": "latam", "spanish-latin america": "latam",
    "spanish (latin america)": "latam", "latam": "latam",
    "norwegian": "norwegian", "polish": "polish",
    "portuguese": "portuguese", "portuguese - portugal": "portuguese",
    "portuguese - brazil": "brazilian", "portuguese-brazil": "brazilian",
    "portuguese (brazil)": "brazilian", "brazilian": "brazilian",
    "romanian": "romanian", "russian": "russian",
    "spanish - spain": "spanish", "spanish-spain": "spanish",
    "spanish (spain)": "spanish", "spanish": "spanish",
    "swedish": "swedish", "thai": "thai",
    "turkish": "turkish", "türkçe": "turkish", "turkce": "turkish",
    "ukrainian": "ukrainian", "vietnamese": "vietnamese",
}

CORE_PROMO_LANGUAGES = {
    "english": "英语", "french": "法语", "italian": "意大利语",
    "german": "德语", "japanese": "日语", "koreana": "韩语",
    "russian": "俄语", "schinese": "简中", "tchinese": "繁中",
    "thai": "泰语", "turkish": "土语", "vietnamese": "越南语",
    "brazilian": "巴葡",
}

COMPETITOR_KEYWORDS = {
    "风灵月影(FLiNG)": ["fling", "风灵月影", "fling trainer"],
    "WeMod": ["wemod", "wand", "we mod"],
}

PAIN_KEYWORDS = {
    "崩溃(Crash)": ["crash", "崩溃", "クラッシュ", "크래시", "вылетает", "abstürzt", "plante", "se bloquea"],
    "翻译(Translation)": [
        "chinese", "translation", "汉化", "翻译", "локализация", "traduction", "traducción", "中文",
        "no language", "language support", "言語", "언어", "简中", "ภาษา ไทย", "ไทย", "Thai",
        "türkçe", "türk", "Turkish", "Vietnamese", "việt hóa", "kor", "한글", "한국어",
        "지역화", "korean", "deutsche", "German", "русский", "язык", "rus", "russian",
        "日本語化", "Japanese", "日本語", "française", "French", "Français",
        "italiana", "lingua italiana",
    ],
    "地图(Map)": ["map", "地图", "マップ", "맵", "карта", "karte", "mapa"],
    "太肝(Grind)": ["grind", "grinding", "肝", "刷", "grindige", "farmear", "фарм", "répétitif"],
    "数值(Broken)": ["overpowered", "op", "nerf", "buff", "broken", "数值", "平衡", "balance"],
    "难度(Hard)": ["too hard", "too difficult", "难", "难度", "difficult", "hard", "слишком сложно", "trop difficile"],
    "Bug": ["bug", "glitch", "issue", "problem", "错误", "バグ", "버그", "баг", "fehler"],
    "优化(Optimization)": ["optimization", "lag", "fps", "performance", "优化", "卡顿", "帧率", "лагает", "optimisation"],
}

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ============================================================
# 页面配置 + CSS
# ============================================================
st.set_page_config(page_title="lago 游戏分析辅助", page_icon="🎮", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp { background-color: #0d1117; color: #c9d1d9; }
[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; border-radius: 8px; padding: 4px; gap: 4px; }
.stTabs [data-baseweb="tab"] { background-color: transparent; color: #8b949e; border-radius: 6px; font-weight: 500; padding: 8px 16px; }
.stTabs [aria-selected="true"] { background-color: #1f6feb !important; color: #ffffff !important; }
.kpi-card { background: linear-gradient(135deg, #161b22 0%, #1c2128 100%); border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
.kpi-title { font-size: 13px; color: #8b949e; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.kpi-value { font-size: 32px; font-weight: 700; color: #58a6ff; line-height: 1; }
.kpi-sub { font-size: 12px; color: #6e7681; margin-top: 6px; }
.kpi-positive { color: #3fb950; } .kpi-negative { color: #f85149; } .kpi-warning { color: #d29922; }
.analysis-card { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px 20px; margin: 8px 0; }
.analysis-card h4 { color: #58a6ff; margin-top: 0; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
.stButton > button { background: linear-gradient(135deg, #1f6feb, #388bfd); color: white; border: none; border-radius: 8px; padding: 10px 24px; font-weight: 600; width: 100%; }
.info-box { background-color: #1c2d3d; border-left: 4px solid #1f6feb; border-radius: 0 8px 8px 0; padding: 12px 16px; margin: 8px 0; font-size: 14px; color: #79c0ff; }
.warning-box { background-color: #2d1e0a; border-left: 4px solid #d29922; border-radius: 0 8px 8px 0; padding: 12px 16px; margin: 8px 0; font-size: 14px; color: #e3b341; }
.brand-header { background: linear-gradient(135deg, #0d1117, #161b22); border: 1px solid #30363d; border-radius: 12px; padding: 20px 24px; margin-bottom: 20px; }
.brand-title { font-size: 24px; font-weight: 700; background: linear-gradient(135deg, #58a6ff, #3fb950); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.brand-subtitle { font-size: 13px; color: #6e7681; margin-top: 4px; }
hr { border-color: #30363d; margin: 16px 0; }
.notice-box { background-color: #1a1a2e; border: 1px dashed #d29922; border-radius: 8px; padding: 10px 16px; margin: 8px 0; font-size: 12px; color: #8b949e; text-align: center; }
.lang-tag-supported { display:inline-block; background:#0d2016; border:1px solid #3fb950; color:#56d364; border-radius:4px; padding:2px 8px; margin:2px; font-size:12px; }
.comp-result-box { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 16px; margin: 6px 0; font-size: 13px; }
#MainMenu { visibility: hidden; } footer { visibility: hidden; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stStatusWidget"] { display: none !important; }
.login-container { max-width: 420px; margin: 80px auto; background: linear-gradient(135deg, #161b22 0%, #1c2128 100%); border: 1px solid #30363d; border-radius: 16px; padding: 40px 36px; box-shadow: 0 8px 32px rgba(0,0,0,0.5); }
.login-title { font-size: 22px; font-weight: 700; color: #58a6ff; text-align: center; margin-bottom: 8px; }
.login-subtitle { font-size: 13px; color: #6e7681; text-align: center; margin-bottom: 24px; }
/* ★ 修复1: 数据明细标题靠左对齐 */
.left-align-title { text-align: left !important; margin-bottom: 8px; }
</style>
<script>
(function () {
  const doc = window.parent.document || document;
  function stopClearCacheOnCopy(e) {
    const key = (e.key || "").toLowerCase();
    if (key !== "c") return;
    if (e.ctrlKey || e.metaKey) {
      e.stopPropagation();
      e.stopImmediatePropagation();
      return;
    }
    const sel = doc.getSelection && doc.getSelection();
    if (sel && String(sel).trim()) {
      e.stopPropagation();
      e.stopImmediatePropagation();
    }
  }
  doc.addEventListener("keydown", stopClearCacheOnCopy, true);
})();
</script>
""", unsafe_allow_html=True)

# ============================================================
# 密码保护
# ============================================================
def show_login_page():
    _, center_col, _ = st.columns([1, 1.2, 1])
    with center_col:
        st.markdown('<div class="login-container"><div class="login-title">🎮 LagoFast</div><div class="login-subtitle">游戏分析辅助 · 内部工具</div></div>', unsafe_allow_html=True)
        st.markdown("### 🔐 请输入访问密码")
        pwd_input = st.text_input("访问密码", type="password", placeholder="请输入访问密码...", key="pwd_input")
        if st.button("进入系统", type="primary"):
            if PAGE_PASSWORD and pwd_input == PAGE_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ 密码错误")
        st.markdown('<div style="text-align:center;color:#6e7681;font-size:11px;margin-top:24px;">⚠️ 仅供内部使用<br>by: Yanghao（from lijiaqi）</div>', unsafe_allow_html=True)

# 已关闭访问密码，默认直接进入页面
# 如需恢复密码访问，可还原下方注释代码
# if "authenticated" not in st.session_state:
#     st.session_state["authenticated"] = False
# if not st.session_state["authenticated"]:
#     show_login_page()
#     st.stop()

# ============================================================
# 工具函数
# ============================================================
def render_kpi_card(title, value, sub="", color_class=""):
    vc = f"kpi-value {color_class}" if color_class else "kpi-value"
    st.markdown(f'<div class="kpi-card"><div class="kpi-title">{title}</div><div class="{vc}">{value}</div><div class="kpi-sub">{sub}</div></div>', unsafe_allow_html=True)

def get_plotly_layout(title=""):
    return dict(title=dict(text=title, font=dict(color="#c9d1d9", size=15)), paper_bgcolor="#161b22", plot_bgcolor="#0d1117", font=dict(color="#8b949e", size=12), margin=dict(t=50, l=20, r=20, b=20), legend=dict(bgcolor="#1c2128", bordercolor="#30363d", borderwidth=1, font=dict(color="#c9d1d9")), xaxis=dict(gridcolor="#21262d", color="#8b949e"), yaxis=dict(gridcolor="#21262d", color="#8b949e"))

def style_apply(styler, func, subset=None):
    pv = tuple(int(x) for x in pd.__version__.split(".")[:2])
    return styler.map(func, subset=subset) if pv >= (2, 1) else styler.applymap(func, subset=subset)

def build_proxy_config(proxy_url):
    if not proxy_url or not proxy_url.strip(): return {}
    url = proxy_url.strip()

    # 代理地址容错：必须包含 http/https 协议头，否则忽略该代理配置，避免 httpx 抛出 Unknown scheme 异常
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return {}

    try: vp = tuple(int(x) for x in httpx.__version__.split(".")[:2])
    except: vp = (0, 99)
    return {"proxy": url} if vp >= (0, 23) else {"proxies": {"http://": url, "https://": url}}

def get_proxy():
    return FIXED_PROXY if FIXED_PROXY and FIXED_PROXY.strip() else ""

# ============================================================
# 游戏名称转URL slug的工具函数
# ============================================================
def game_name_to_slug(name: str) -> str:
    """
    ★ 修复2核心：将游戏英文名转为URL slug
    规则：小写 + 空格转连字符 + 去掉特殊字符
    例如：Fracture Field -> fracture-field
    """
    slug = name.lower().strip()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug

# ============================================================
# Steam 数据获取
# ============================================================
def fetch_game_info(app_id, proxy_url=None):
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=english"
    pk = build_proxy_config(proxy_url or get_proxy())
    try:
        with httpx.Client(headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30.0, follow_redirects=True, **pk) as c:
            r = c.get(url); r.raise_for_status(); d = r.json()
            if d and str(app_id) in d and d[str(app_id)].get("success"): return d[str(app_id)].get("data", {})
    except Exception as e: st.warning(f"获取游戏信息失败: {e}")
    return {}

def parse_supported_languages(html_str):
    if not html_str: return set()
    clean = re.sub(r'<[^>]+>', '', html_str).replace('*', '').replace('\n', ',').replace('\r', ',')
    clean = re.sub(r'\s+', ' ', clean).strip()
    raw_names = [n.strip() for n in clean.split(',') if n.strip()]
    codes = set()
    for raw_name in raw_names:
        nl = raw_name.lower().strip()
        if nl in LANGUAGE_NAME_TO_CODE: codes.add(LANGUAGE_NAME_TO_CODE[nl]); continue
        matched = False
        for key, code in LANGUAGE_NAME_TO_CODE.items():
            if key in nl or nl in key: codes.add(code); matched = True; break
        if not matched:
            normalized = nl
            for o, r in {'ü':'u','ö':'o','ä':'a','ç':'c','ş':'s','ğ':'g','ı':'i','é':'e','è':'e','ê':'e','à':'a','â':'a'}.items():
                normalized = normalized.replace(o, r)
            if normalized in LANGUAGE_NAME_TO_CODE: codes.add(LANGUAGE_NAME_TO_CODE[normalized])
            else:
                for key, code in LANGUAGE_NAME_TO_CODE.items():
                    if key in normalized or normalized in key: codes.add(code); break
    return codes

def parse_all_supported_languages_text(html_str):
    if not html_str: return []
    clean = re.sub(r'<[^>]+>', '', html_str).replace('*', '').strip()
    return [n.strip() for n in clean.split(',') if n.strip()]

def steam_lang_name_to_chinese(raw_name):
    nl = raw_name.lower().strip()
    if nl in LANGUAGE_NAME_TO_CODE:
        return STEAM_LANGUAGES.get(LANGUAGE_NAME_TO_CODE[nl], raw_name)
    for key, code in LANGUAGE_NAME_TO_CODE.items():
        if key in nl or nl in key:
            return STEAM_LANGUAGES.get(code, raw_name)
    normalized = nl
    for o, r in {'ü':'u','ö':'o','ä':'a','ç':'c','ş':'s','ğ':'g','ı':'i','é':'e','è':'e','ê':'e','à':'a','â':'a'}.items():
        normalized = normalized.replace(o, r)
    if normalized in LANGUAGE_NAME_TO_CODE:
        return STEAM_LANGUAGES.get(LANGUAGE_NAME_TO_CODE[normalized], raw_name)
    for key, code in LANGUAGE_NAME_TO_CODE.items():
        if key in normalized or normalized in key:
            return STEAM_LANGUAGES.get(code, raw_name)
    return raw_name

def get_supported_languages_chinese(game_info):
    """从 Steam Store API (appdetails) 的 supported_languages 解析界面语言，返回中文名称列表。"""
    sh = (game_info or {}).get("supported_languages", "")
    if not sh:
        return []
    zh_list, seen = [], set()
    for raw in parse_all_supported_languages_text(sh):
        zh = steam_lang_name_to_chinese(raw)
        if zh not in seen:
            zh_list.append(zh)
            seen.add(zh)
    if zh_list:
        return zh_list
    return [STEAM_LANGUAGES.get(c, c) for c in sorted(parse_supported_languages(sh))]

def _coalesce_api_key(val):
    if val is None:
        return ""
    s = str(val).strip()
    return s if s and s.lower() not in ("none", "your_api_key_here", "") else ""

def _load_local_secrets_toml():
    path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        try:
            import tomllib
            return tomllib.loads(text)
        except ImportError:
            out = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
            return out
    except Exception:
        return {}

def _load_streamlit_secrets():
    app_secrets = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    user_secrets = Path.home() / ".streamlit" / "secrets.toml"
    if not app_secrets.is_file() and not user_secrets.is_file():
        return {}
    try:
        return st.secrets
    except Exception:
        return {}

def get_deepseek_api_key():
    """读取 DeepSeek API Key：环境变量 → Streamlit Secrets → 本地 secrets.toml"""
    key = _coalesce_api_key(os.environ.get("DEEPSEEK_API_KEY"))
    if key:
        return key
    secrets = _load_streamlit_secrets()
    if secrets:
        key = _coalesce_api_key(secrets.get("DEEPSEEK_API_KEY"))
        if key:
            return key
        block = secrets.get("deepseek", {})
        if hasattr(block, "get"):
            key = _coalesce_api_key(block.get("api_key") or block.get("API_KEY"))
            if key:
                return key
    local = _load_local_secrets_toml()
    key = _coalesce_api_key(local.get("DEEPSEEK_API_KEY"))
    if key:
        return key
    deepseek_block = local.get("deepseek")
    if isinstance(deepseek_block, dict):
        key = _coalesce_api_key(deepseek_block.get("api_key") or deepseek_block.get("API_KEY"))
        if key:
            return key
    return ""

def _empty_result(language, error="无数据"):
    return {"language": language, "display_name": STEAM_LANGUAGES.get(language, language), "total": 0, "positive": 0, "negative": 0, "review_score": "N/A", "reviews": [], "error": error}

def fetch_review_summary_for_language(client, app_id, language, review_type="all", purchase_type="all", filter_type="all", day_range="all"):
    url = f"https://store.steampowered.com/appreviews/{app_id}"
    params = {"json": "1", "language": language, "num_per_page": "100", "review_type": review_type, "purchase_type": purchase_type, "filter": filter_type, "cursor": "*"}
    if filter_type == "recent" and day_range != "all": params["day_range"] = day_range
    for retry in range(3):
        try:
            client.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = client.get(url, params=params); resp.raise_for_status(); data = resp.json()
            if data.get("success") != 1:
                if retry < 2: time.sleep(1); continue
                return None
            summary = data.get("query_summary", {}); reviews_raw = data.get("reviews", [])
            review_texts = [{"text": r.get("review","").strip()[:500], "voted_up": r.get("voted_up", False), "language": language} for r in reviews_raw if r.get("review","").strip()]
            return {"language": language, "display_name": STEAM_LANGUAGES.get(language, language), "total": summary.get("total_reviews", 0), "positive": summary.get("total_positive", 0), "negative": summary.get("total_negative", 0), "review_score": summary.get("review_score_desc", "N/A"), "reviews": review_texts, "error": None}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429: time.sleep((retry+1)*3)
            elif retry < 2: time.sleep(1); continue
            else: return _empty_result(language, error=f"HTTP {e.response.status_code}")
        except httpx.TimeoutException:
            if retry < 2: time.sleep(2); continue
            return _empty_result(language, error="请求超时")
        except Exception as e:
            if retry < 2: time.sleep(2); continue
            return _empty_result(language, error=str(e)[:80])
    return _empty_result(language, error="重试3次均失败")

def fetch_all_languages(app_id, proxy=None, selected_langs=None):
    if selected_langs is None: selected_langs = list(STEAM_LANGUAGES.keys())
    ep = proxy if proxy and proxy.strip() else get_proxy()
    pk = build_proxy_config(ep); results = []; pb = st.progress(0, text="准备开始抓取..."); total = len(selected_langs); st_time = time.time()
    with httpx.Client(headers={"User-Agent": random.choice(USER_AGENTS)}, timeout=30.0, follow_redirects=True, limits=httpx.Limits(max_connections=10, max_keepalive_connections=5), **pk) as client:
        for i, lang in enumerate(selected_langs):
            display = STEAM_LANGUAGES.get(lang, lang); elapsed = time.time() - st_time
            eta = f"预计剩余 {(elapsed/i)*(total-i):.0f}秒" if i > 0 else "计算中..."
            pb.progress((i+1)/total, text=f"[{i+1}/{total}] 正在抓取: {display} | {eta}")
            result = fetch_review_summary_for_language(client=client, app_id=app_id, language=lang)
            if result is None: result = _empty_result(lang, error="返回数据异常")
            results.append(result)
            time.sleep(random.uniform(0.15, 0.35) if ep else random.uniform(0.25, 0.55))
    pb.empty(); return results


def fetch_all_reviews_for_export(app_id, language, proxy=None, max_pages=200):
    """
    导出专用：分页抓取某语言下的尽可能完整评论，避免仅导出首批100条。
    """
    ep = proxy if proxy and proxy.strip() else get_proxy()
    pk = build_proxy_config(ep)
    url = f"https://store.steampowered.com/appreviews/{app_id}"
    cursor = "*"
    all_reviews = []
    total_expected = 0
    page_count = 0

    with httpx.Client(
        headers={"User-Agent": random.choice(USER_AGENTS)},
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        **pk
    ) as client:
        while page_count < max_pages:
            params = {
                "json": "1",
                "language": language,
                "num_per_page": "100",
                "review_type": "all",
                "purchase_type": "all",
                "filter": "all",
                "cursor": cursor,
            }
            try:
                client.headers["User-Agent"] = random.choice(USER_AGENTS)
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                # 导出阶段遇到单页异常时，保留已抓到内容并终止该语言抓取
                break

            if data.get("success") != 1:
                break

            summary = data.get("query_summary", {})
            total_expected = max(total_expected, int(summary.get("total_reviews", 0) or 0))
            reviews_raw = data.get("reviews", []) or []
            if not reviews_raw:
                break

            for r in reviews_raw:
                review_text = (r.get("review") or "").strip()
                if review_text:
                    all_reviews.append(
                        {
                            "language": language,
                            "voted_up": bool(r.get("voted_up", False)),
                            "text": review_text,
                            "timestamp_created": r.get("timestamp_created", 0),
                            "steamid": r.get("author", {}).get("steamid", ""),
                        }
                    )

            next_cursor = data.get("cursor")
            if not next_cursor or next_cursor == cursor:
                break

            cursor = next_cursor
            page_count += 1

            # 已达到该语言总评论数时提前结束，减少无效请求
            if total_expected > 0 and len(all_reviews) >= total_expected:
                break

            time.sleep(random.uniform(0.08, 0.2))

    return all_reviews, total_expected

def results_to_dataframe(results, supported_lang_codes=None):
    rows = []; grand_total = sum(r["total"] for r in results)
    for r in results:
        total = r["total"]; positive = r["positive"]; negative = r["negative"]
        rate = round(positive/total*100, 1) if total > 0 else 0.0
        pct = round(total/grand_total*100, 2) if grand_total > 0 else 0.0
        lang_match = "⏳ 未检测"
        if supported_lang_codes is None: lang_match = "⏳ 未检测"
        elif len(supported_lang_codes) == 0: lang_match = "⚠️ 无数据"
        elif r["language"] in supported_lang_codes: lang_match = "✅ 已支持"
        else: lang_match = "❌ 未支持"
        rows.append({"语言代码": r["language"], "语言": r["display_name"], "总评论数": total, "占比(%)": pct, "好评数": positive, "差评数": negative, "好评率(%)": rate, "评分描述": r["review_score"], "游戏界面支持": lang_match})
    if not rows: return pd.DataFrame(columns=["语言代码","语言","总评论数","占比(%)","好评数","差评数","好评率(%)","评分描述","游戏界面支持"])
    return pd.DataFrame(rows).sort_values("总评论数", ascending=False).reset_index(drop=True)

# ============================================================
# AI + 分析函数
# ============================================================
def call_ai(prompt, system_prompt=None, model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL):
    api_key = get_deepseek_api_key()
    if not api_key:
        return (
            "❌ 未检测到 DEEPSEEK_API_KEY。\n\n"
            "**说明：** GitHub「Settings → Secrets and variables → **Actions**」中的 Repository secrets "
            "**不会**自动注入 Streamlit 页面，因此仅在那里配置无法让本工具读取。\n\n"
            "**请按你的运行方式配置：**\n"
            "- **Streamlit Cloud 部署**：打开 [share.streamlit.io](https://share.streamlit.io) → 你的应用 → "
            "**Settings → Secrets**，粘贴：\n"
            "  ```\n  DEEPSEEK_API_KEY = \"你的密钥\"\n  ```\n"
            "  保存后点击 **Reboot app** 重启应用。\n"
            "- **本地运行**：在项目目录创建 `.streamlit/secrets.toml`（勿提交到 Git），内容同上；"
            "或在终端设置环境变量 `DEEPSEEK_API_KEY` 后重新启动 `streamlit run app.py`。"
        )
    client = OpenAI(api_key=api_key, base_url=base_url); msgs = []
    if system_prompt: msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(model=model, messages=msgs, max_tokens=4096, temperature=0.7, stream=False)
        return resp.choices[0].message.content
    except Exception as e: return f"❌ AI 调用失败：{str(e)}"

def build_review_summary(results, max_reviews_per_lang=15):
    lines = []
    for r in results:
        if r["total"] == 0: continue
        rate = round(r["positive"]/r["total"]*100, 1) if r["total"] > 0 else 0
        lines.append(f"\n### {r['display_name']} (总评论:{r['total']}, 好评率:{rate}%)")
        neg = [rv for rv in r["reviews"] if not rv["voted_up"]][:max_reviews_per_lang//2]
        pos = [rv for rv in r["reviews"] if rv["voted_up"]][:max_reviews_per_lang//2]
        for rv in neg + pos: lines.append(f"  {'👎' if not rv['voted_up'] else '👍'} {rv['text'][:200]}")
    return "\n".join(lines)

def analyze_pain_keywords(results):
    ps = {p: {} for p in PAIN_KEYWORDS}
    for r in results:
        if not r["reviews"]: continue
        for pain, kws in PAIN_KEYWORDS.items():
            cnt = sum(1 for rv in r["reviews"] if any(kw.lower() in rv["text"].lower() for kw in kws))
            if cnt > 0: ps[pain][r["display_name"]] = cnt
    return ps

def analyze_competitor_mentions(results):
    cs = {c: 0 for c in COMPETITOR_KEYWORDS}
    for r in results:
        for rv in r["reviews"]:
            tl = rv["text"].lower()
            for comp, kws in COMPETITOR_KEYWORDS.items():
                if any(kw.lower() in tl for kw in kws): cs[comp] += 1
    return cs

def fetch_url_content(url, proxy_url=None):
    ep = proxy_url if proxy_url and proxy_url.strip() else get_proxy(); pk = build_proxy_config(ep)
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True, headers={"User-Agent": random.choice(USER_AGENTS)}, **pk) as c:
            resp = c.get(url); resp.raise_for_status()
            text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text); return re.sub(r'\s+', ' ', text).strip()[:5000]
    except Exception as e: return f"[抓取失败: {e}]"

def fetch_url_raw_html(url, proxy_url=None):
    ep = proxy_url if proxy_url and proxy_url.strip() else get_proxy(); pk = build_proxy_config(ep)
    try:
        with httpx.Client(timeout=25.0, follow_redirects=True, headers={"User-Agent": random.choice(USER_AGENTS)}, **pk) as c:
            resp = c.get(url); resp.raise_for_status(); return resp.text
    except Exception as e: return f"[抓取失败: {e}]"


def build_competitor_export_dataframe(comp_res, game_name, app_id):
    """
    将 Tab3 竞品检测结果整理为可导出的表格数据。
    """
    rows = []
    platform_map = {
        "wemod": "WeMod",
        "fling": "风灵月影（网页版）",
        "flyy": "风灵月影（客户端版）",
    }

    for key, platform_name in platform_map.items():
        item = comp_res.get(key, {}) if comp_res else {}
        covered = "已覆盖" if item.get("covered", False) else "未覆盖"
        if key == "wemod":
            detect_url = item.get("cheats_url", "")
            details = item.get("cheat_list", [])
        elif key == "fling":
            detect_url = item.get("search_url", "")
            details = item.get("options", [])
        else:
            detect_url = item.get("search_url", "")
            details = item.get("options", [])

        rows.append(
            {
                "游戏名称": game_name,
                "游戏AppID": app_id,
                "检测时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "竞品平台": platform_name,
                "覆盖状态": covered,
                "检测地址": detect_url,
                "修改项/功能详情": " | ".join(details) if details else "",
                "详情数量": len(details),
                "原始片段": item.get("raw_snippet", ""),
            }
        )

    return pd.DataFrame(rows)


def dataframe_to_excel_bytes(df, sheet_name="数据导出"):
    """
    将 DataFrame 转为 Excel 二进制，供 Streamlit 下载按钮使用。
    """
    output = BytesIO()
    # 先尝试 xlsxwriter（写入速度快），若环境未安装则回退 openpyxl
    try:
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    except ModuleNotFoundError:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)
    return output.getvalue()

def render_global_wishlist_tab():
    st.markdown("#### 💙 Steam 全站愿望单榜单")
    st.markdown(
        '<div class="info-box">这里抓取 Steam 商店公开的 popularwishlist 榜单，适合做全站热门未发售游戏、竞品热度和选题方向分析。Steam 不公开全站真实愿望单数量，因此这里展示的是公开排名，不是真实 wishlist count。</div>',
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        limit = st.selectbox("抓取数量", [10, 20, 30, 50, 100, 200, 300, 500], index=0, key="global_wishlist_limit")
    with c2:
        country = st.selectbox("商店地区", ["ALL", "US", "CN", "JP", "KR", "DE", "FR", "GB"], index=0, key="global_wishlist_country")
    with c3:
        st.caption("榜单来自 Steam Store 公开搜索筛选 popularwishlist；数量越大请求越久。")

    if st.button("抓取 Steam 全站愿望单榜单", type="primary", key="btn_fetch_global_wishlist"):
        with st.spinner("正在抓取 Steam popularwishlist 榜单..."):
            try:
                df, total_count = fetch_popular_wishlist_apps(limit=limit, country=country)
                st.session_state.global_wishlist_df = df
                st.session_state.global_wishlist_total = total_count
                if df.empty:
                    st.warning("没有抓取到榜单数据，请稍后重试或检查网络。")
                else:
                    st.success(f"成功获取 Top {len(df)}，Steam 当前公开榜单总量约 {total_count:,} 个条目")
            except Exception as exc:
                st.error(f"全站愿望单榜单抓取失败：{exc}")

    df = st.session_state.get("global_wishlist_df")
    total_count = st.session_state.get("global_wishlist_total", 0)
    if df is None or df.empty:
        st.markdown('<div class="info-box">点击抓取后，会展示 Steam 全站愿望单排名、Top 游戏、发售状态和导出表格。</div>', unsafe_allow_html=True)
        render_single_game_distribution_section()
        return

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi_card("已抓取条目", f"{len(df):,}", "公开榜单 Top N")
    with k2:
        render_kpi_card("榜单总量", f"{int(total_count):,}" if total_count else "N/A", "Steam 返回 total_count")
    with k3:
        top_name = df.iloc[0]["游戏名称"] if len(df) else "N/A"
        render_kpi_card("榜首游戏", top_name, f"AppID {df.iloc[0]['AppID']}" if len(df) else "")
    with k4:
        tba_count = int(df["发售状态/日期"].astype(str).str.contains("announce|soon|coming|待定|即将", case=False, na=False).sum())
        render_kpi_card("未定/即将发售", f"{tba_count:,}", "按发售文本粗略判断")

    st.markdown("---")
    top_chart = df.head(25).copy()
    fig = go.Figure(
        data=[
            go.Bar(
                x=(top_chart["愿望单排名"].max() + 1 - top_chart["愿望单排名"]),
                y=top_chart["游戏名称"],
                orientation="h",
                marker_color="#58a6ff",
                text=top_chart["愿望单排名"].map(lambda x: f"#{x}"),
                textposition="auto",
            )
        ]
    )
    layout = get_plotly_layout("Steam 全站愿望单 Top25（排名越靠前热度越高）")
    layout.update(height=620, yaxis=dict(autorange="reversed", color="#8b949e"), xaxis=dict(visible=False))
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 📋 全站愿望单榜单明细")
    display_cols = ["愿望单排名", "AppID", "游戏名称", "发售状态/日期", "评价摘要", "平台", "商店链接"]
    display_df = df[[c for c in display_cols if c in df.columns]].copy()
    st.dataframe(
        display_df,
        use_container_width=True,
        height=520,
        column_config={
            "商店链接": st.column_config.LinkColumn("商店链接"),
        },
    )

    st.download_button(
        "下载全站愿望单榜单 Excel",
        dataframe_to_excel_bytes(display_df, sheet_name="Steam全站愿望单榜单"),
        f"steam_global_wishlist_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_global_wishlist_excel",
    )

    st.markdown(
        '<div class="warning-box">说明：Gamalytic 这类站点展示的 wishlist 数量通常来自私有模型或第三方估算。Steam 公开页面能提供全站排名，但不能提供每个游戏真实愿望单人数。</div>',
        unsafe_allow_html=True,
    )
    render_single_game_distribution_section()


def render_wishlist_region_interest_section(base_df):
    st.markdown("---")
    st.markdown("#### 🌐 愿望单区域兴趣分布")
    st.markdown(
        '<div class="info-box">对多个 Steam 商店地区的 popularwishlist 榜单做交叉排名，估算每个游戏在哪些地区更受愿望单用户关注。它是公开排名代理，不是真实 wishlister 国家占比。</div>',
        unsafe_allow_html=True,
    )
    regions = st.multiselect(
        "对比地区",
        ["US", "CN", "JP", "KR", "DE", "FR", "GB", "BR", "RU", "TR"],
        default=["US", "CN", "JP", "KR", "DE", "FR", "GB"],
        key="wishlist_interest_regions",
    )
    limit_per_region = st.selectbox("每个地区抓取 Top N", [10, 20, 30, 50, 100, 200, 300, 500], index=0, key="wishlist_interest_limit")
    if st.button("计算愿望单区域兴趣", key="btn_wishlist_region_interest"):
        with st.spinner("正在抓取多地区 wishlist 榜单并计算兴趣占比..."):
            try:
                long_df, wide_df = fetch_regional_wishlist_interest(regions=regions, limit_per_region=limit_per_region)
                st.session_state.wishlist_region_interest_long = long_df
                st.session_state.wishlist_region_interest_wide = wide_df
                if wide_df.empty:
                    st.warning("没有得到区域兴趣数据，请减少地区或稍后重试。")
                else:
                    st.success(f"完成：覆盖 {len(wide_df):,} 个游戏，{len(regions)} 个地区")
            except Exception as exc:
                st.error(f"区域兴趣计算失败：{exc}")

    wide_df = st.session_state.get("wishlist_region_interest_wide")
    long_df = st.session_state.get("wishlist_region_interest_long")
    if wide_df is None or wide_df.empty:
        return

    st.dataframe(wide_df.head(100), use_container_width=True, height=420)
    signal_df = wide_df[wide_df.get("区域信号状态", "") == "有地区差异"].copy() if "区域信号状态" in wide_df.columns else wide_df
    if signal_df.empty:
        st.warning("当前 Steam 公开 popularwishlist 榜单在所选地区没有排名差异，因此无法计算真实有效的区域市场占比。这里不能把相同榜单硬算成各地区均分。")
        return

    top = signal_df.head(20)
    region_cols = [c for c in top.columns if c not in ["AppID", "游戏名称", "覆盖地区数", "总兴趣分", "地区排名差异数", "区域信号状态"]]
    if region_cols:
        fig = go.Figure()
        for col in region_cols:
            fig.add_trace(go.Bar(name=col, x=top["游戏名称"], y=top[col]))
        layout = get_plotly_layout("Top20 游戏愿望单区域兴趣占比")
        layout.update(height=460, barmode="stack", xaxis=dict(tickangle=-35, color="#8b949e"))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)

    if long_df is not None and not long_df.empty:
        st.download_button(
            "下载愿望单区域兴趣 Excel",
            dataframe_to_excel_bytes(wide_df, sheet_name="愿望单区域兴趣"),
            f"wishlist_region_interest_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_wishlist_region_interest",
        )


def render_purchase_region_estimate_section(base_df):
    st.markdown("---")
    st.markdown("#### 🧭 购买玩家区域估算")
    st.markdown(
        '<div class="info-box">抓取榜单游戏的 Steam 购买评论语言 summary，用语言市场作为购买玩家区域代理。它更接近“购买用户评论样本分布”，不等同于真实销售地区。</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([1, 2])
    with c1:
        top_n = st.selectbox("分析榜单前 N 个游戏", [1, 3, 5, 10, 20, 30], index=3, key="purchase_region_top_n")
        purchase_type = st.selectbox("评论购买口径", ["all", "steam", "non_steam_purchase"], index=0, key="purchase_region_purchase_type")
    with c2:
        languages = st.multiselect(
            "评论语言市场",
            ["english", "schinese", "tchinese", "japanese", "koreana", "russian", "german", "french", "spanish", "latam", "brazilian", "turkish", "thai", "vietnamese", "polish", "italian"],
            default=["english", "schinese", "japanese", "koreana", "russian", "german", "french", "spanish", "brazilian"],
            key="purchase_region_languages",
        )
    if st.button("估算购买玩家区域", key="btn_purchase_region_estimate"):
        with st.spinner("正在抓取 Steam 购买评论语言 summary..."):
            try:
                long_df, wide_df = fetch_purchase_language_distribution(base_df, languages=languages, top_n=top_n, purchase_type=purchase_type)
                st.session_state.purchase_region_long = long_df
                st.session_state.purchase_region_wide = wide_df
                if wide_df.empty:
                    st.warning("没有得到购买玩家区域估算数据。未发售游戏或评论很少的游戏通常没有足够样本。")
                else:
                    st.success(f"完成：分析 {len(wide_df):,} 个游戏，{len(languages)} 个语言市场")
            except Exception as exc:
                st.error(f"购买玩家区域估算失败：{exc}")

    wide_df = st.session_state.get("purchase_region_wide")
    if wide_df is None or wide_df.empty:
        return

    st.dataframe(wide_df, use_container_width=True, height=420)
    market_cols = [c for c in wide_df.columns if c not in ["愿望单排名", "AppID", "游戏名称", "购买评论总样本"]]
    chart_df = wide_df[wide_df["购买评论总样本"] > 0].head(15)
    if not chart_df.empty and market_cols:
        fig = go.Figure()
        for col in market_cols:
            fig.add_trace(go.Bar(name=col, x=chart_df["游戏名称"], y=chart_df[col]))
        layout = get_plotly_layout("购买玩家区域估算占比（Steam 购买评论语言代理）")
        layout.update(height=460, barmode="stack", xaxis=dict(tickangle=-35, color="#8b949e"))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)

    st.download_button(
        "下载购买玩家区域估算 Excel",
        dataframe_to_excel_bytes(wide_df, sheet_name="购买玩家区域估算"),
        f"purchase_region_estimate_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_purchase_region_estimate",
    )


def _render_country_distribution(result: CountryDistribution, value_label: str, title: str, color: str) -> None:
    st.markdown(f"##### {title}")
    if not result.available:
        state_labels = {
            MetricStatus.FORBIDDEN: "无权限",
            MetricStatus.RATE_LIMITED: "请求受限",
            MetricStatus.SCHEMA_CHANGED: "等待接口契约验证",
            MetricStatus.INVALID_DATA: "数据校验失败",
            MetricStatus.UNAVAILABLE: "暂不可用",
        }
        st.info(f"{state_labels.get(result.status, '暂不可用')}：{result.message}")
        return

    frame = result.to_frame(value_label)
    st.dataframe(frame, use_container_width=True, hide_index=True)
    figure = go.Figure(
        data=[
            go.Bar(
                x=frame["国家/地区"],
                y=frame[value_label],
                marker_color=color,
                text=frame[value_label].map(lambda value: f"{value:.1f}%"),
                textposition="auto",
            )
        ]
    )
    layout = get_plotly_layout(title)
    layout.update(height=400, xaxis=dict(tickangle=-35, color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
    figure.update_layout(**layout)
    st.plotly_chart(figure, use_container_width=True)
    if not result.is_complete:
        st.caption(f"当前来源明确披露了 {result.reported_share_percent:.1f}% 的国家份额；未披露部分不会被自动拆分。")
    st.caption(f"来源：{result.source} | 状态：{result.status} | UTC 抓取时间：{result.fetched_at:%Y-%m-%d %H:%M}")


def render_single_game_distribution_section():
    st.markdown("---")
    st.markdown("#### 🔎 单个游戏市场数据")
    st.markdown(
        '<div class="info-box">先按名称搜索或直接输入 AppID。Players、Buyers、Wishlists 使用独立数据口径；没有经验证来源时会明确显示不可用，不会用榜单或评论语言代替。</div>',
        unsafe_allow_html=True,
    )

    search_col, app_col = st.columns([2, 1])
    with search_col:
        search_query = st.text_input("搜索 Steam 游戏", placeholder="例如：Fable", key="market_game_search_query")
        if st.button("搜索游戏", key="market_game_search_button"):
            try:
                st.session_state.market_game_search_results = search_steam_games(search_query)
                st.session_state.market_game_search_error = ""
            except Exception as exc:
                st.session_state.market_game_search_results = pd.DataFrame()
                st.session_state.market_game_search_error = str(exc)
    with app_col:
        st.caption("可直接查询数字 AppID")

    search_results = st.session_state.get("market_game_search_results")
    if st.session_state.get("market_game_search_error"):
        st.warning(f"Steam 游戏搜索失败：{st.session_state.market_game_search_error}")
    if search_results is not None and not search_results.empty:
        st.dataframe(
            search_results[[column for column in ["AppID", "游戏名称", "发售状态/日期", "商店链接"] if column in search_results.columns]],
            use_container_width=True,
            hide_index=True,
        )
        selected_app_id = st.selectbox(
            "选择搜索结果",
            search_results["AppID"].tolist(),
            format_func=lambda app_id: f"{app_id} - {search_results.loc[search_results['AppID'] == app_id, '游戏名称'].iloc[0]}",
            key="market_selected_search_app_id",
        )
        if st.button("使用选中的 AppID", key="market_use_selected_app_id"):
            st.session_state.market_game_app_id = str(selected_app_id)

    settings_col, key_col = st.columns([1, 1])
    with settings_col:
        app_id = st.text_input("游戏 AppID", placeholder="例如：2769570", key="market_game_app_id")
    with key_col:
        gamalytic_api_key = st.text_input(
            "Gamalytic API Key（可选）",
            type="password",
            key="market_gamalytic_api_key",
            help="仅用于有明确接口契约的授权端点；密钥不会显示在页面或诊断信息中。",
        )

    if st.button("加载游戏市场数据", type="primary", key="market_load_game"):
        if not app_id.strip().isdigit():
            st.error("请输入有效的数字 AppID，或先从搜索结果中选择游戏。")
        else:
            result: dict[str, object] = {"appid": app_id.strip(), "loaded_at": datetime.utcnow()}
            try:
                game_data = fetch_gamalytic_game_details(app_id.strip())
                result["summary"] = gamalytic_summary_frame(game_data)
                result["public_players"] = gamalytic_country_data_frame(game_data)
                result["game_error"] = ""
            except Exception as exc:
                result["summary"] = pd.DataFrame()
                result["public_players"] = pd.DataFrame()
                result["game_error"] = str(exc)

            if gamalytic_api_key.strip():
                result["active_users"] = fetch_gamalytic_active_users_regions(app_id.strip(), gamalytic_api_key)
                result["wishlists"] = fetch_gamalytic_wishlist_country_distribution(app_id.strip(), gamalytic_api_key)
            else:
                result["active_users"] = None
                result["wishlists"] = None
            st.session_state.market_game_result = result

    result = st.session_state.get("market_game_result")
    if not result:
        return

    if result.get("game_error"):
        st.warning(f"游戏概览暂时不可用：{result['game_error']}")
    summary = result.get("summary")
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        st.markdown("##### 游戏概览（供应商估算）")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.caption("此概览来自公开 Gamalytic 页面接口，可能限流或变更；不作为国家分布的唯一来源。")

    players_tab, buyers_tab, wishlists_tab, quality_tab = st.tabs(["Players", "Buyers", "Wishlists", "数据质量"])
    with players_tab:
        active_users = result.get("active_users")
        if isinstance(active_users, CountryDistribution):
            _render_country_distribution(active_users, "活跃用户占比(%)", "Active users by country", "#58a6ff")
        else:
            public_players = result.get("public_players")
            if isinstance(public_players, pd.DataFrame) and not public_players.empty:
                st.markdown("##### Players by country（公开 Top3 + 未披露剩余）")
                st.dataframe(public_players, use_container_width=True, hide_index=True)
                st.caption("公开 countryData 是玩家估算。除已披露国家外，其余份额只显示为未披露剩余，不能展开为 Top20。")
            else:
                st.info("没有可用的 Players 国家分布。可使用有权限的 active-users-regions，或稍后重试公开数据源。")

    with buyers_tab:
        st.info("全站 Buyers by country 需要授权的区域销售数据或经官方样本校准的模型。当前未接入可验证来源，因此不显示估算值。")

    with wishlists_tab:
        wishlist_result = result.get("wishlists")
        if isinstance(wishlist_result, CountryDistribution):
            _render_country_distribution(wishlist_result, "愿望单占比(%)", "Wishlists by country", "#3fb950")
        else:
            st.info("全站 Wishlists by country 需要经过字段验证的供应商数据；Steam 公共榜单不能推导此分布。")

    with quality_tab:
        active_users = result.get("active_users")
        wishlist_result = result.get("wishlists")
        quality_rows = [
            {"指标": "Players（公开）", "状态": "estimated" if isinstance(result.get("public_players"), pd.DataFrame) and not result["public_players"].empty else "unavailable", "来源": "Gamalytic public countryData", "说明": "公开结果通常仅披露 Top3 + 未披露剩余"},
            {"指标": "Active users", "状态": active_users.status if isinstance(active_users, CountryDistribution) else "not_requested", "来源": "Gamalytic active-users-regions", "说明": active_users.message if isinstance(active_users, CountryDistribution) else "未填写 API Key"},
            {"指标": "Buyers", "状态": "unavailable", "来源": "需要区域销售数据", "说明": "评论语言与商店榜单不会被用作购买国家代理"},
            {"指标": "Wishlists", "状态": wishlist_result.status if isinstance(wishlist_result, CountryDistribution) else "not_requested", "来源": "Gamalytic wishlist-insights", "说明": wishlist_result.message if isinstance(wishlist_result, CountryDistribution) else "未填写 API Key"},
        ]
        st.dataframe(pd.DataFrame(quality_rows), use_container_width=True, hide_index=True)


def _legacy_render_single_game_distribution_section():
    st.markdown("---")
    st.markdown("#### 🔎 单个游戏 Gamalytic 区域查询")
    st.markdown(
        '<div class="info-box">输入 Steam AppID 后，公开数据只能展示 Players by country 的 Top3+Other；如果填写有 Pro 权限的 Gamalytic API Key，会优先读取 wishlist-insights 并展示愿望单国家分布 Top20 明细。</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([1, 2])
    with c1:
        single_app_id = st.text_input("单个游戏 AppID", placeholder="例如: 730", key="single_game_app_id")
        single_purchase_type = st.selectbox("单游戏评论口径", ["all", "steam", "non_steam_purchase"], index=0, key="single_purchase_type")
        single_scan_limit = st.selectbox("愿望单榜单扫描 Top N", [10, 20, 30, 50, 100, 200, 300, 500], index=0, key="single_wishlist_scan_limit")
        gamalytic_api_key = st.text_input(
            "Gamalytic API Key（可选，用于 Top20 国家分布）",
            type="password",
            key="single_gamalytic_api_key",
            help="公开页面通常只返回 Top3+Other；Top20 玩家国家分布和愿望单国家分布需要 Gamalytic Pro API 权限。",
        )
    with c2:
        single_regions = st.multiselect(
            "单游戏愿望单地区",
            ["US", "CN", "JP", "KR", "DE", "FR", "GB", "BR", "RU", "TR"],
            default=["US", "CN", "JP", "KR", "DE", "FR", "GB"],
            key="single_wishlist_regions",
        )
        single_languages = st.multiselect(
            "单游戏评论语言市场",
            ["english", "schinese", "tchinese", "japanese", "koreana", "russian", "german", "french", "spanish", "latam", "brazilian", "turkish", "thai", "vietnamese", "polish", "italian"],
            default=["english", "schinese", "japanese", "koreana", "russian", "german", "french", "spanish", "brazilian"],
            key="single_purchase_languages",
        )

    if st.button("查询单个游戏区域分布", key="btn_single_game_distribution"):
        if not single_app_id.strip().isdigit():
            st.error("请输入有效的数字 AppID。")
        else:
            with st.spinner("正在查询单个游戏的购买区域与愿望单区域信号..."):
                gamalytic_data = None
                try:
                    gamalytic_data = fetch_gamalytic_game_details(single_app_id.strip())
                    gamalytic_country_df = gamalytic_country_data_frame(gamalytic_data)
                    gamalytic_summary_df = gamalytic_summary_frame(gamalytic_data)
                    st.session_state.single_gamalytic_data = gamalytic_data
                    st.session_state.single_gamalytic_country_df = gamalytic_country_df
                    st.session_state.single_gamalytic_summary_df = gamalytic_summary_df
                    st.session_state.single_gamalytic_error = ""
                except Exception as exc:
                    st.session_state.single_gamalytic_error = str(exc)
                st.session_state.single_gamalytic_active_regions_df = None
                st.session_state.single_gamalytic_wishlist_country_df = None
                st.session_state.single_gamalytic_pro_error = ""
                if gamalytic_api_key.strip():
                    pro_errors = []
                    try:
                        st.session_state.single_gamalytic_active_regions_df = fetch_gamalytic_active_users_regions(
                            single_app_id.strip(),
                            gamalytic_api_key,
                        )
                    except Exception as exc:
                        pro_errors.append(f"active-users-regions：{exc}")
                    try:
                        st.session_state.single_gamalytic_wishlist_country_df = fetch_gamalytic_wishlist_country_distribution(
                            single_app_id.strip(),
                            gamalytic_api_key,
                        )
                    except Exception as exc:
                        pro_errors.append(f"wishlist-insights：{exc}")
                    st.session_state.single_gamalytic_pro_error = "；".join(pro_errors)
                app_df = app_row(single_app_id.strip())
                purchase_long, purchase_wide = fetch_purchase_language_distribution(
                    app_df,
                    languages=single_languages,
                    top_n=1,
                    purchase_type=single_purchase_type,
                )
                wishlist_region_df = find_app_in_regional_wishlists(
                    single_app_id.strip(),
                    regions=single_regions,
                    scan_limit=single_scan_limit,
                )
                st.session_state.single_purchase_wide = purchase_wide
                st.session_state.single_purchase_long = purchase_long
                st.session_state.single_wishlist_region = wishlist_region_df

    gamalytic_error = st.session_state.get("single_gamalytic_error")
    if gamalytic_error:
        st.warning(f"Gamalytic countryData 暂时不可用：{gamalytic_error}")
    gamalytic_pro_error = st.session_state.get("single_gamalytic_pro_error")
    if gamalytic_pro_error:
        st.warning(f"Gamalytic Pro Top20 数据暂时不可用：{gamalytic_pro_error}")

    gamalytic_country_df = st.session_state.get("single_gamalytic_country_df")
    gamalytic_summary_df = st.session_state.get("single_gamalytic_summary_df")
    gamalytic_active_regions_df = st.session_state.get("single_gamalytic_active_regions_df")
    gamalytic_wishlist_country_df = st.session_state.get("single_gamalytic_wishlist_country_df")
    if gamalytic_summary_df is not None and not gamalytic_summary_df.empty:
        st.markdown("##### Gamalytic Stats 摘要")
        st.dataframe(gamalytic_summary_df, use_container_width=True, height=320)

    if gamalytic_wishlist_country_df is not None and not gamalytic_wishlist_country_df.empty:
        st.markdown("##### Wishlists by country Top20（Gamalytic Pro，愿望单国家分布）")
        st.dataframe(gamalytic_wishlist_country_df, use_container_width=True)
        fig = go.Figure(
            data=[
                go.Bar(
                    x=gamalytic_wishlist_country_df["国家/地区"],
                    y=gamalytic_wishlist_country_df["愿望单占比(%)"],
                    marker_color="#3fb950",
                    text=gamalytic_wishlist_country_df["愿望单占比(%)"].map(lambda x: f"{x:.1f}%"),
                    textposition="auto",
                )
            ]
        )
        layout = get_plotly_layout("Gamalytic Wishlists by country Top20")
        layout.update(height=420, xaxis=dict(tickangle=-35, color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("说明：该表来自 Gamalytic Pro 的 wishlist-insights 接口，展示愿望单国家分布 Top20；不会把 Top3 之外的国家合并成 Other。")
    elif st.session_state.get("single_gamalytic_api_key", "").strip():
        st.warning("已填写 Gamalytic API Key，但 wishlist-insights 没有返回可解析的国家愿望单 Top20。请确认该 Key 具备 Pro 权限。")
    else:
        st.info("愿望单国家 Top20 需要 Gamalytic Pro API Key。未填写 Key 时不会用公开 Top3+Other 伪造成愿望单国家分布。")

    if gamalytic_active_regions_df is not None and not gamalytic_active_regions_df.empty:
        st.markdown("##### Players by country Top20（Gamalytic Pro）")
        st.dataframe(gamalytic_active_regions_df, use_container_width=True)
        fig = go.Figure(
            data=[
                go.Bar(
                    x=gamalytic_active_regions_df["国家/地区"],
                    y=gamalytic_active_regions_df["玩家占比(%)"],
                    marker_color="#58a6ff",
                    text=gamalytic_active_regions_df["玩家占比(%)"].map(lambda x: f"{x:.1f}%"),
                    textposition="auto",
                )
            ]
        )
        layout = get_plotly_layout("Gamalytic Players by country Top20")
        layout.update(height=420, xaxis=dict(tickangle=-35, color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("说明：该数据来自 Gamalytic Pro 的 active-users-regions 接口，口径为 MAU 国家占比。")
    elif gamalytic_country_df is not None and not gamalytic_country_df.empty:
        st.markdown("##### Players by country（公开 Top3 + Other）")
        st.dataframe(gamalytic_country_df, use_container_width=True)
        fig = go.Figure(
            data=[
                go.Bar(
                    x=gamalytic_country_df["国家/地区"],
                    y=gamalytic_country_df["玩家占比(%)"],
                    marker_color="#58a6ff",
                    text=gamalytic_country_df["玩家占比(%)"].map(lambda x: f"{x:.1f}%"),
                    textposition="auto",
                )
            ]
        )
        layout = get_plotly_layout("Gamalytic Players by country")
        layout.update(height=380, xaxis=dict(color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("说明：该数据来自 Gamalytic 页面公开接口 game-details 的 countryData 字段，公开页面通常只给 Top3 + Other；不是 Top20。要展示至少 Top20，需要输入有 Pro 权限的 Gamalytic API Key。")
    elif gamalytic_country_df is not None:
        st.warning("Gamalytic 页面公开接口没有返回 countryData，无法展示 Players by country。")

    purchase_wide = st.session_state.get("single_purchase_wide")
    wishlist_region_df = st.session_state.get("single_wishlist_region")
    if purchase_wide is not None and not purchase_wide.empty:
        st.markdown("##### Steam 评论语言分布参考")
        st.dataframe(purchase_wide, use_container_width=True)
        market_cols = [c for c in purchase_wide.columns if c not in ["愿望单排名", "AppID", "游戏名称", "购买评论总样本"]]
        if float(purchase_wide.iloc[0].get("购买评论总样本", 0)) <= 0:
            st.warning("该游戏在所选评论口径和语言市场下没有评论样本。可以把口径切到 all，或增加语言市场。")
        elif market_cols:
            fig = go.Figure(data=[go.Bar(x=market_cols, y=[purchase_wide.iloc[0][c] for c in market_cols], marker_color="#58a6ff")])
            layout = get_plotly_layout("Steam 评论语言分布参考")
            layout.update(height=360, xaxis=dict(tickangle=-25, color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True)

    if wishlist_region_df is not None and not wishlist_region_df.empty:
        st.markdown("##### Steam 地区愿望单公开榜单诊断")
        st.dataframe(wishlist_region_df, use_container_width=True)
        if "区域信号状态" in wishlist_region_df.columns and (wishlist_region_df["区域信号状态"] == "无地区差异").all():
            st.warning("Steam popularwishlist 地区榜单没有可用排名差异，不能据此估算真实愿望单玩家区域占比。Gamalytic 的 WISHLISTS BY COUNTRY 属于更深的 wishlist insights 数据，公开接口当前没有返回。")
        chart_df = wishlist_region_df[wishlist_region_df.get("愿望单区域兴趣占比(%)", 0) > 0].copy()
        if not chart_df.empty:
            fig = go.Figure(data=[go.Bar(x=chart_df["地区"], y=chart_df["愿望单区域兴趣占比(%)"], marker_color="#3fb950")])
            layout = get_plotly_layout("单游戏愿望单区域兴趣信号")
            layout.update(height=360, xaxis=dict(color="#8b949e"), yaxis=dict(range=[0, 100], color="#8b949e"))
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# ★ 修复2：竞品覆盖检测函数（修正检测地址和判断逻辑）
# ============================================================

def check_wemod_coverage(game_name_en: str) -> dict:
    """
    ★ 修复2：WeMod覆盖检测
    检测地址：https://www.wemod.com/cheats/{slug}-trainers
    slug规则：游戏英文名小写，空格转连字符
    判断条件：页面有 mod-list → 已覆盖；页面显示 Unavailable → 未覆盖
    """
    slug = game_name_to_slug(game_name_en)
    cheats_url = f"https://www.wemod.com/cheats/{slug}-trainers"
    html = fetch_url_raw_html(cheats_url)

    result = {"covered": False, "cheats_url": cheats_url, "cheat_list": [], "raw_snippet": ""}

    if "[抓取失败" in html:
        result["raw_snippet"] = html
        return result

    html_lower = html.lower()
    # 判断条件：mod-list 存在则已覆盖，Unavailable 则未覆盖
    if "unavailable" in html_lower and "mod-list" not in html_lower:
        result["covered"] = False
        result["raw_snippet"] = "页面显示 Unavailable（未覆盖）"
    elif "mod-list" in html_lower:
        result["covered"] = True
        # 提取修改项名称
        patterns = [
            r'class="[^"]*cheat[^"]*name[^"]*"[^>]*>([^<]+)<',
            r'class="[^"]*mod[^"]*name[^"]*"[^>]*>([^<]+)<',
            r'"name"\s*:\s*"([^"]{3,60})"',
            r'data-cheat-name="([^"]+)"',
            r'class="cheat-name[^"]*">([^<]+)<',
        ]
        for pattern in patterns:
            for m in re.findall(pattern, html, re.IGNORECASE):
                m = m.strip()
                if m and len(m) > 2 and m not in result["cheat_list"]:
                    result["cheat_list"].append(m)
        result["raw_snippet"] = html[:500]
    else:
        result["covered"] = False
        result["raw_snippet"] = "未找到 mod-list 标识"

    return result


def check_fling_coverage(game_name_en: str) -> dict:
    """
    ★ 修复2：风灵月影网页版覆盖检测
    检测地址：https://flingtrainer.com/?s={slug}
    slug规则：游戏英文名，空格转+
    判断条件：页面有 Options → 已覆盖；页面显示 Error 404 → 未覆盖
    """
    search_url = f"https://flingtrainer.com/?s={game_name_en.replace(' ', '+')}"
    html = fetch_url_raw_html(search_url)

    result = {"covered": False, "search_url": search_url, "trainer_url": "", "options": [], "raw_snippet": ""}

    if "[抓取失败" in html:
        result["raw_snippet"] = html
        return result

    html_lower = html.lower()
    # 判断条件：Error 404 → 未覆盖；Options → 已覆盖
    if "error 404" in html_lower or "nothing found" in html_lower or "0 search results" in html_lower:
        result["covered"] = False
        result["raw_snippet"] = "页面显示 Error 404 或无搜索结果（未覆盖）"
    elif "options" in html_lower:
        result["covered"] = True
        slug = game_name_to_slug(game_name_en)
        trainer_url = f"https://flingtrainer.com/trainer/{slug}-trainer/"
        result["trainer_url"] = trainer_url
        # 尝试从搜索结果或trainer页面提取Options
        trainer_html = fetch_url_raw_html(trainer_url)
        if "[抓取失败" not in trainer_html:
            entry_match = re.search(r'<div[^>]*class="[^"]*entry[^"]*"[^>]*>(.*?)</div>', trainer_html, re.DOTALL | re.IGNORECASE)
            entry_html = entry_match.group(1) if entry_match else trainer_html
            p_texts = re.findall(r'<p[^>]*>(.*?)</p>', entry_html, re.DOTALL | re.IGNORECASE)
            for pt in p_texts:
                clean = re.sub(r'<[^>]+>', '', pt).strip()
                if clean and 2 < len(clean) < 200 and clean not in result["options"]:
                    result["options"].append(clean)
        result["raw_snippet"] = html[:500]
    else:
        result["covered"] = False
        result["raw_snippet"] = "未找到 Options 标识"

    return result


def check_flyy_coverage(game_name_en: str, game_name_cn: str = "") -> dict:
    """
    ★ 修复2：风灵月影客户端版覆盖检测
    检测地址：https://www.flyy.cn/librarys?search={game_name}
    game_name 直接使用原始游戏英文名（空格保留）
    判断条件：有搜索结果 → 已覆盖；显示"该游戏暂无修改器~" → 未覆盖
    """
    search_url = f"https://www.flyy.cn/librarys?search={game_name_en.replace(' ', '+')}"
    html = fetch_url_raw_html(search_url)

    result = {"covered": False, "search_url": search_url, "options": [], "raw_snippet": ""}

    if "[抓取失败" in html and game_name_cn:
        search_url_cn = f"https://www.flyy.cn/librarys?search={game_name_cn.replace(' ', '+')}"
        html = fetch_url_raw_html(search_url_cn)
        result["search_url"] = search_url_cn

    if "[抓取失败" in html:
        result["raw_snippet"] = html
        return result

    html_lower = html.lower()
    no_result_kws = ["该游戏暂无修改器", "暂无修改器", "暂无数据", "没有找到"]
    has_no_result = any(kw.lower() in html_lower for kw in no_result_kws)

    game_card_indicators = ["lib-item", "game-item", "game-card", "trainer", "game-name", "game-cover", "txtover", "librarys-item"]
    has_card = any(ind in html_lower for ind in game_card_indicators)
    has_name = game_name_en.lower() in html_lower
    clean_text = re.sub(r'<[^>]+>', '', html).strip()

    if has_no_result and not has_card and not has_name:
        result["raw_snippet"] = "该游戏暂无修改器~（未覆盖）"
        return result

    if has_card or has_name or len(clean_text) > 500:
        result["covered"] = True
        # 提取修改详情
        txtover_match = re.search(r'txtover.*?(<div[^>]*>.*?</div>)', html, re.DOTALL | re.IGNORECASE)
        if txtover_match:
            div_texts = re.findall(r'<div[^>]*>(.*?)</div>', txtover_match.group(1), re.DOTALL | re.IGNORECASE)
            for dt in div_texts:
                clean = re.sub(r'<[^>]+>', '', dt).strip()
                clean = re.sub(r'\s+', ' ', clean)
                if clean and 2 < len(clean) < 300 and clean not in result["options"]:
                    result["options"].append(clean)
        result["raw_snippet"] = html[:300]
        return result

    result["raw_snippet"] = f"无法确定（{len(clean_text)}字符）"
    return result


# ============================================================
# Session State 初始化
# ============================================================
for _k in ["fetch_results", "fetch_df", "last_app_id", "game_info", "supported_lang_codes", "all_supported_langs_text", "global_wishlist_df", "global_wishlist_total"]:
    if _k not in st.session_state: st.session_state[_k] = None
if "ai_results" not in st.session_state: st.session_state["ai_results"] = {}
if "comp_check_results" not in st.session_state: st.session_state["comp_check_results"] = {}
for _k, _v in [("cfg_app_id","892970"),("cfg_preset","主流10语言"),("cfg_custom_langs",["schinese","english","russian","japanese"])]:
    if _k not in st.session_state: st.session_state[_k] = _v
for _legacy_key in ["wishlist_df", "wishlist_country_df", "wishlist_errors", "wishlist_diagnosis", "cfg_steam_financial_api_key"]:
    st.session_state.pop(_legacy_key, None)

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:16px 0;border-bottom:1px solid #30363d;margin-bottom:16px;"><div style="font-size:28px;">🎮</div><div style="font-size:16px;font-weight:700;color:#58a6ff;margin-top:4px;">LagoFast</div><div style="font-size:11px;color:#6e7681;">游戏分析辅助 v2.0</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="notice-box">⚠️ 该AI工具输出结论仅做辅助参考</div>', unsafe_allow_html=True)
    st.markdown("### 🔧 基础配置")
    st.markdown('<div style="font-size:12px;color:#8b949e;margin-bottom:6px;"><b>如何查找 Steam AppID：</b><br>方式1：游戏 Steam 商店页面 URL 中的数字<br>方式2：在 <a href="https://www.steamdb.info" target="_blank" style="color:#58a6ff;">SteamDB</a> 搜索</div>', unsafe_allow_html=True)
    app_id = st.text_input("Steam AppID", placeholder="例如: 892970", key="cfg_app_id")
    lang_options = list(STEAM_LANGUAGES.keys())
    PRESETS = {"主流10语言": ["schinese","english","russian","japanese","koreana","german","french","spanish","brazilian","turkish"], "亚洲语言": ["schinese","tchinese","japanese","koreana","thai","vietnamese","indonesian","arabic"], "欧洲语言": ["english","russian","german","french","spanish","italian","polish","turkish","dutch","czech","hungarian","romanian","swedish","norwegian","danish","finnish","ukrainian","bulgarian","greek"], "全部30语言": lang_options}
    preset = st.selectbox("快速选择预设", ["主流10语言","亚洲语言","欧洲语言","全部30语言","自定义"], key="cfg_preset")
    if preset != "自定义": selected_langs = PRESETS.get(preset, PRESETS["主流10语言"]); st.info(f"已选 {len(selected_langs)} 种语言")
    else:
        selected_langs = st.multiselect("选择语言", options=lang_options, format_func=lambda x: STEAM_LANGUAGES.get(x,x), key="cfg_custom_langs")
        if not selected_langs: selected_langs = ["english"]
    st.markdown("---"); st.markdown("### 🤖 AI 配置")
    st.markdown('<div style="font-size:12px;color:#8b949e;background:#161b22;border:1px dashed #30363d;border-radius:6px;padding:8px 12px;line-height:1.6;">默认调用deepseek API进行评论文本分析，无需再次输入</div>', unsafe_allow_html=True)
    st.markdown("---"); start_btn = st.button("🚀 开始分析", type="primary")
    st.markdown("---"); st.markdown('<div style="font-size:11px;color:#6e7681;text-align:center;">© 2025 LagoFast<br><span style="color:#444;">by: Yanghao（from lijiaqi）</span></div>', unsafe_allow_html=True)

# 品牌头部
st.markdown(f'<div class="brand-header"><div><div class="brand-title">🎮 LagoFast 游戏分析辅助</div><div class="brand-subtitle">Steam 玩家评论挖掘 · 需求发现 · 竞品分析 · 推广策略 | {datetime.now().strftime("%Y-%m-%d %H:%M")}</div></div><div style="text-align:right;color:#8b949e;font-size:13px;">AppID: <span style="color:#58a6ff;font-weight:600;">{app_id or "未设置"}</span><br>语言: <span style="color:#3fb950;">{len(selected_langs)} 种</span> | AI: <span style="color:#d29922;">DeepSeek</span></div></div>', unsafe_allow_html=True)
st.markdown('<div class="notice-box">⚠️ 该AI工具输出结论仅做辅助参考，请结合实际业务判断</div>', unsafe_allow_html=True)
st.markdown('<div class="info-box">📌 工具说明：仅针对 Steam 有评论数据的游戏进行分析；该工具使用实时数据，每次查询结果可能存在差异；该工具输出内容仅辅助参考，请结合业务实际情况进行决策。</div>', unsafe_allow_html=True)

# 抓取逻辑
if start_btn:
    if not app_id or not app_id.strip().isdigit(): st.error("❌ 请输入有效的 Steam AppID")
    else:
        st.session_state.ai_results = {}; st.session_state.comp_check_results = {}
        with st.status("🔄 正在抓取 Steam 数据...", expanded=True) as status:
            st.write("📋 正在获取游戏基本信息...")
            gi = fetch_game_info(app_id.strip()); st.session_state.game_info = gi
            gn = gi.get("name", f"AppID {app_id}"); sh = gi.get("supported_languages", "")
            slc = parse_supported_languages(sh); alt = parse_all_supported_languages_text(sh)
            st.session_state.supported_lang_codes = slc; st.session_state.all_supported_langs_text = alt
            if gn: st.write(f"🎮 游戏名称: **{gn}**")
            if slc: st.write(f"🌐 游戏界面支持语言: **{len(alt)}** 种")
            st.write(f"💬 正在抓取 {len(selected_langs)} 种语言评论...")
            results = fetch_all_languages(app_id.strip(), None, selected_langs)
            df = results_to_dataframe(results, slc)
            st.session_state.fetch_results = results; st.session_state.fetch_df = df; st.session_state.last_app_id = app_id.strip()
            vc = len([r for r in results if r["total"] > 0]); tr = int(df["总评论数"].sum())
            if tr == 0: st.warning("⚠️ 所有语言均返回0评论")
            else: st.success(f"✅ 成功获取 {tr:,} 条评论，覆盖 {vc} 种语言")
            status.update(label=f"{'✅' if tr>0 else '⚠️'} 抓取完成！{tr:,} 条 / {vc} 语言", state="complete", expanded=False)

# Tab 布局
tab1, tab2, tab3, tab4 = st.tabs(["📊 Tab1 基础评论分析", "🔍 Tab2 AI 需求挖掘", "📣 Tab3 推广策略辅助", "💙 Tab4 全站愿望单榜单"])

# ============================================================
# Tab 1
# ============================================================
with tab1:
    if st.session_state.fetch_df is None:
        st.markdown('<div class="info-box">👈 请在左侧配置参数，点击「🚀 开始分析」</div>', unsafe_allow_html=True)
    else:
        df = st.session_state.fetch_df; results = st.session_state.fetch_results
        gi = st.session_state.game_info or {}; slc = st.session_state.supported_lang_codes or set(); alt = st.session_state.all_supported_langs_text or []
        gn = gi.get("name", f"AppID {st.session_state.last_app_id}")
        if gn: st.markdown(f"### 🎮 {gn}")
        tr = int(df["总评论数"].sum()); tp = int(df["好评数"].sum()); tn = int(df["差评数"].sum())
        oar = round(tp/tr*100, 1) if tr > 0 else 0.0; vl = len(df[df["总评论数"]>0]); tl = df.iloc[0]["语言"] if len(df)>0 else "N/A"
        st.markdown("#### 📈 核心指标总览"); kc = st.columns(6)
        with kc[0]: render_kpi_card("总评论数", f"{tr:,}", "全语言汇总")
        with kc[1]: render_kpi_card("综合好评率", f"{oar}%", "多语言加权", "kpi-positive" if oar>=70 else ("kpi-warning" if oar>=50 else "kpi-negative"))
        with kc[2]: render_kpi_card("好评总数", f"{tp:,}", "累计好评", "kpi-positive")
        with kc[3]: render_kpi_card("差评总数", f"{tn:,}", "需关注", "kpi-negative")
        with kc[4]: render_kpi_card("覆盖语言", str(vl), f"共 {len(selected_langs)} 种")
        with kc[5]: render_kpi_card("最大来源", tl, "按评论数排名")
        st.markdown("---"); dv = df[df["总评论数"]>0].head(20)
        if len(dv) > 0:
            pc, ic = st.columns([2, 1])
            with pc:
                st.markdown("#### 🍩 评论来源语言分布"); dt = dv.head(10)
                fig = go.Figure(data=[go.Pie(labels=dt["语言"], values=dt["总评论数"], hole=0.55, textinfo="label+percent", textfont=dict(color="#c9d1d9",size=11), marker=dict(colors=["#1f6feb","#3fb950","#d29922","#f85149","#58a6ff","#56d364","#e3b341","#ff7b72","#79c0ff","#ffa657"], line=dict(color="#0d1117",width=2)))])
                ld = get_plotly_layout("Top10 语言评论来源"); ld.update(height=380, showlegend=True, annotations=[dict(text=f"<b>{tr:,}</b><br>总评论", x=0.5, y=0.5, font=dict(size=14,color="#58a6ff"), showarrow=False)])
                fig.update_layout(**ld); st.plotly_chart(fig, use_container_width=True)
            with ic:
                st.markdown("#### 🌐 游戏界面语言支持")
                st.markdown('<div class="info-box" style="font-size:11px;">ℹ️ 仅根据核心推广区域判断语言支持情况，并非涵盖所有语言</div>', unsafe_allow_html=True)
                if alt: st.markdown(f'<div class="analysis-card" style="margin-bottom:8px;"><h4 style="font-size:13px;">该游戏实际支持的所有语言（{len(alt)} 种）</h4><div style="line-height:2;">{"".join([f"<span class=lang-tag-supported>{l}</span>" for l in alt])}</div></div>', unsafe_allow_html=True)
                st.markdown("**核心推广语言覆盖情况：**")
                if slc:
                    for code, name in CORE_PROMO_LANGUAGES.items(): st.markdown(f"{'✅' if code in slc else '❌'} {name}")

        st.markdown("---")
        st.markdown("#### 🧾 总结")
        main_lang_rows = df[df["占比(%)"] > 1].sort_values("占比(%)", ascending=False)
        if len(main_lang_rows) > 0:
            main_lang_text = "、".join([f"{row['语言']}{row['占比(%)']:.1f}%" for _, row in main_lang_rows.iterrows()])
        else:
            main_lang_text = "暂无占比大于1%的语言"
        st.markdown(f"玩家评论分布主要为：{main_lang_text}")

        unsupported_core = [(code, name) for code, name in CORE_PROMO_LANGUAGES.items() if not slc or code not in slc]
        if unsupported_core:
            lang_pct_lookup = {
                row["语言代码"]: float(row["占比(%)"])
                for _, row in df.iterrows()
                if "语言代码" in df.columns and row.get("总评论数", 0) > 0
            }
            unsupported_sorted = sorted(
                unsupported_core,
                key=lambda x: (
                    0 if x[0] in lang_pct_lookup else 1,
                    -lang_pct_lookup.get(x[0], 0.0),
                    x[1]
                )
            )
            translation_need_text = ">".join([name for _, name in unsupported_sorted])
        else:
            translation_need_text = "核心推广语言已全部支持"
        st.markdown(f"翻译需求为：{translation_need_text}")

        support_langs_zh = get_supported_languages_chinese(gi)
        support_lang_text = "、".join(support_langs_zh) if support_langs_zh else "暂无数据"
        st.markdown(f"游戏内支持语言：{support_lang_text}")

        # ★ 修复1：标题靠左对齐
        st.markdown('<div class="left-align-title"><h4>📋 语言评论数据明细</h4></div>', unsafe_allow_html=True)
        st.markdown('<div class="info-box">「游戏界面支持」列：显示该评论语言是否在游戏官方支持的界面语言列表中（仅核心推广语言）</div>', unsafe_allow_html=True)
        def hr(val):
            if isinstance(val, (int,float)):
                if val >= 80: return "color:#3fb950;font-weight:bold"
                elif val >= 60: return "color:#d29922"
                else: return "color:#f85149"
            return ""
        def hlm(val):
            if "✅" in str(val): return "color:#3fb950"
            if "❌" in str(val): return "color:#f85149"
            return "color:#8b949e"
        ddf = df.drop(columns=[c for c in ["语言代码"] if c in df.columns]); styler = ddf.style
        if "好评率(%)" in ddf.columns: styler = style_apply(styler, hr, subset=["好评率(%)"])
        if "游戏界面支持" in ddf.columns: styler = style_apply(styler, hlm, subset=["游戏界面支持"])
        fmt = {}
        for c, f in [("好评率(%)","{:.1f}%"),("占比(%)","{:.2f}%"),("总评论数","{:,}"),("好评数","{:,}"),("差评数","{:,}")]:
            if c in ddf.columns: fmt[c] = f
        styled_df = styler.format(fmt); cc = {}
        if "好评率(%)" in ddf.columns: cc["好评率(%)"] = st.column_config.ProgressColumn("好评率", min_value=0, max_value=100, format="%.1f%%")
        if "占比(%)" in ddf.columns: cc["占比(%)"] = st.column_config.NumberColumn("占比(%)", format="%.2f%%")
        if "游戏界面支持" in ddf.columns: cc["游戏界面支持"] = st.column_config.TextColumn("游戏界面支持", width="medium")
        st.dataframe(styled_df, use_container_width=True, height=420, column_config=cc)

        # ★ 新增1：翻译推广建议（在语言支持展示之后、数据明细表之前）
        if slc and len(df[df["总评论数"] > 0]) > 0:
            st.markdown("---")
            st.markdown("#### 📣 翻译推广建议")
            st.markdown("""
            <div class="info-box" style="font-size:12px;">
                基于评论量和语言支持情况，自动划分三类市场并给出推广优先级建议
            </div>
            """, unsafe_allow_html=True)

            # 按评论量排序的有效语言数据
            df_promo = df[df["总评论数"] > 0].copy()

            core_market = []      # 核心市场：评论多 + 已支持语言
            high_potential = []   # 高潜力市场：评论多 + 核心推广语言但未支持
            expansion = []        # 拓展市场：评论多 + 非核心目标语言 + 未支持

            for _, row in df_promo.iterrows():
                lang_code = row["语言代码"] if "语言代码" in df_promo.columns else ""
                lang_name = row["语言"]
                review_count = int(row["总评论数"])
                rate = row["好评率(%)"]

                if review_count == 0:
                    continue

                is_supported = lang_code in slc if lang_code else False
                is_core_promo = lang_code in CORE_PROMO_LANGUAGES if lang_code else False

                if is_supported:
                    core_market.append({
                        "语言": lang_name, "评论量": review_count, "好评率": rate,
                        "建议": "加大推广投入，已有语言优势"
                    })
                elif is_core_promo and not is_supported:
                    high_potential.append({
                        "语言": lang_name, "评论量": review_count, "好评率": rate,
                        "建议": "优先开发翻译工具，市场需求明确"
                    })
                elif not is_supported:
                    expansion.append({
                        "语言": lang_name, "评论量": review_count, "好评率": rate,
                        "建议": "中长期拓展，评估ROI后决定"
                    })

            promo_col1, promo_col2, promo_col3 = st.columns(3)

            with promo_col1:
                st.markdown(f"""
                <div class="analysis-card">
                    <h4 style="color:#3fb950;">🟢 核心市场（{len(core_market)} 个）</h4>
                    <p style="color:#8b949e;font-size:12px;">评论量大 + 游戏已支持该语言<br>建议：加大推广投入</p>
                </div>
                """, unsafe_allow_html=True)
                if core_market:
                    for item in core_market[:8]:
                        st.markdown(f"✅ **{item['语言']}** — {item['评论量']:,}条 | 好评率{item['好评率']:.0f}%")
                else:
                    st.caption("暂无")

            with promo_col2:
                st.markdown(f"""
                <div class="analysis-card">
                    <h4 style="color:#d29922;">🟡 高潜力市场（{len(high_potential)} 个）</h4>
                    <p style="color:#8b949e;font-size:12px;">评论量大 + 核心推广语言但未支持<br>建议：优先开发翻译工具</p>
                </div>
                """, unsafe_allow_html=True)
                if high_potential:
                    for idx, item in enumerate(high_potential[:8]):
                        priority = "🥇" if idx == 0 else ("🥈" if idx == 1 else ("🥉" if idx == 2 else f"{idx+1}."))
                        st.markdown(f"{priority} **{item['语言']}** — {item['评论量']:,}条 | 好评率{item['好评率']:.0f}%")
                else:
                    st.markdown("✅ 核心推广语言已全部覆盖，无高潜力缺口")

            with promo_col3:
                st.markdown(f"""
                <div class="analysis-card">
                    <h4 style="color:#8b949e;">⚪ 拓展市场（{len(expansion)} 个）</h4>
                    <p style="color:#8b949e;font-size:12px;">评论量大 + 非核心语言 + 未支持<br>建议：中长期评估ROI</p>
                </div>
                """, unsafe_allow_html=True)
                if expansion:
                    for item in expansion[:8]:
                        st.markdown(f"🔹 **{item['语言']}** — {item['评论量']:,}条 | 好评率{item['好评率']:.0f}%")
                else:
                    st.caption("暂无")

        st.markdown("#### 📥 导出全量评论内容")
        if st.button("📦 准备导出全量评论", key="btn_export"):
            # 导出时按语言进行分页抓取，尽可能贴近总评论规模
            with st.status("正在准备全量评论导出...", expanded=True) as export_status:
                arr = []
                total_expected_all = 0
                langs_to_export = [r for r in results if r.get("total", 0) > 0]
                for idx, lang_item in enumerate(langs_to_export, start=1):
                    lang_code = lang_item.get("language", "")
                    lang_name = lang_item.get("display_name", lang_code)
                    export_status.write(f"[{idx}/{len(langs_to_export)}] 抓取 {lang_name} 评论...")
                    reviews_full, expected = fetch_all_reviews_for_export(
                        app_id=st.session_state.last_app_id,
                        language=lang_code,
                    )
                    total_expected_all += expected
                    arr.extend(
                        [
                            {
                                "语言代码": lang_code,
                                "语言": lang_name,
                                "好评/差评": "好评" if rv["voted_up"] else "差评",
                                "评论内容": rv["text"],
                                "评论时间戳": rv.get("timestamp_created", 0),
                                "用户SteamID": rv.get("steamid", ""),
                                "游戏AppID": st.session_state.last_app_id,
                                "游戏名称": gi.get("name", ""),
                            }
                            for rv in reviews_full
                        ]
                    )

                if arr:
                    edf = pd.DataFrame(arr)
                    excel_data = dataframe_to_excel_bytes(edf, sheet_name="全量评论")
                    export_status.update(label=f"✅ 已准备 {len(arr):,} 条评论（目标约 {total_expected_all:,}）", state="complete", expanded=False)
                    st.download_button(
                        f"📥 下载全量评论 ({len(arr):,} 条)",
                        excel_data,
                        f"all_reviews_{app_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    export_status.update(label="⚠️ 未抓取到可导出的评论内容", state="error", expanded=False)
# ============================================================
# Tab 2 - AI 需求挖掘
# ============================================================
with tab2:
    if st.session_state.fetch_results is None:
        st.markdown('<div class="info-box">👈 请先在 Tab1 完成数据抓取</div>', unsafe_allow_html=True)
    else:
        results = st.session_state.fetch_results; gi = st.session_state.game_info or {}; gn = gi.get("name", f"AppID {st.session_state.last_app_id}"); gne = gn
        st.markdown("#### 🔍 AI 驱动的玩家需求深度挖掘")
        st.markdown("##### 📊 痛点关键词出现频率统计")
        st.markdown('<div class="info-box" style="font-size:12px;">优先级评估说明：根据对游戏可用性、易用性的影响评估优先级（可用性 &gt; 易用性）。</div>', unsafe_allow_html=True)
        ps = analyze_pain_keywords(results); pn = list(ps.keys()); al = sorted(set(l for p in ps.values() for l in p))
        if al:
            hm = [[ps[p].get(l,0) for l in al] for p in pn]
            fh = go.Figure(data=go.Heatmap(z=hm, x=al, y=pn, colorscale=[[0,"#0d1117"],[0.3,"#1f3d6b"],[0.7,"#1f6feb"],[1,"#58a6ff"]], text=[[str(v) if v>0 else "" for v in row] for row in hm], texttemplate="%{text}", textfont=dict(color="white",size=11)))
            lh = get_plotly_layout("痛点关键词 × 语言 热力图"); lh.update(height=380, xaxis=dict(tickangle=-30)); fh.update_layout(**lh); st.plotly_chart(fh, use_container_width=True)
            pcols = st.columns(min(len(pn),4))
            for i, pain in enumerate(pn):
                tm = sum(ps[pain].values())
                top_langs = sorted(ps[pain].items(), key=lambda x: x[1], reverse=True)[:3]
                top_lang_text = "、".join([f"{lang}({cnt})" for lang, cnt in top_langs]) if top_langs else "无"
                with pcols[i%4]: render_kpi_card(pain, str(tm), f"Top3: {top_lang_text}", "kpi-negative" if tm>10 else ("kpi-warning" if tm>5 else ""))
        st.markdown("---"); st.markdown("##### 🤖 AI 智能提取游戏痛点关键词")
        if st.button("🔍 AI 分析提取痛点关键词", key="btn_pain"):
            with st.spinner("AI 分析中..."):
                rs = build_review_summary(results, 15)
                st.session_state.ai_results["pain_extract"] = call_ai(f"请分析Steam游戏「{gn}」的评论，提取高频痛点关键词。\n\n评论样本：\n{rs}\n\n请输出：\n## 高频痛点词（前10）\n| 痛点关键词 | 出现频率 | 主要语言 | 痛点描述 |\n## 按类型分类\n## 最值得关注的3个核心痛点")
        if "pain_extract" in st.session_state.ai_results:
            st.markdown(st.session_state.ai_results["pain_extract"])
        st.markdown("---"); st.markdown("##### ⚙️ 修改器需求分析")
        if st.button("🔮 生成修改器需求表", key="btn_trainer"):
            with st.spinner("正在分析（预计30-60秒）..."):
                rs = build_review_summary(results, 15); pj = json.dumps({k:sum(v.values()) for k,v in ps.items()}, ensure_ascii=False)
                gs = game_name_to_slug(gne)
                wc = fetch_url_content(f"https://www.wemod.com/cheats/{gs}-trainers"); fc = fetch_url_content(f"https://flingtrainer.com/?s={gne.replace(' ','+')}")
                prompt = f"你是修改器产品经理，为「{gn}」制定修改器清单。\n\n痛点统计：{pj}\n评论样本：{rs}\n\nWeMod内容：{wc[:1500]}\nFLiNG内容：{fc[:1000]}\n\n请输出：\n## 修改器功能需求清单\n| 修改项名称（中文） | 修改项名称（英文） | 需求评分(1-10) | 核心依据 |\n（至少10条）\n\n## 分析\n### 1. 需求评分\n### 2. 高优先级目标语言\n### 3. 具体功能建议\n### 4. 开发优先级"
                st.session_state.ai_results["trainer_tri"] = call_ai(prompt)
        if "trainer_tri" in st.session_state.ai_results:
            # 直接按 Markdown 渲染 AI 输出，确保标题和表格格式正常显示
            rt = st.session_state.ai_results["trainer_tri"]; st.markdown(rt)
            st.markdown("**📋 一键复制修改项名称**"); c1, c2 = st.columns(2)
            zh, en = [], []
            for line in rt.split("\n"):
                if "|" in line and "修改项" not in line and "---" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2: zh.append(parts[0]); en.append(parts[1])
            with c1:
                if zh: st.text_area("中文", "\n".join(zh), height=200, key="copy_zh")
            with c2:
                if en: st.text_area("英文", "\n".join(en), height=200, key="copy_en")
        st.markdown("---"); st.markdown("##### 🛠️ 专项工具需求分析")
        slc = st.session_state.supported_lang_codes or set(); ml, cl = [], []
        for code, name in CORE_PROMO_LANGUAGES.items():
            if slc and code not in slc: ml.append(f"❌ {name} ({code})")
            elif slc: cl.append(f"✅ {name} ({code})")
        if ml or cl:
            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("**已支持**")
                for l in cl: st.markdown(l)
            with tc2:
                st.markdown("**缺失（翻译工具需求）**")
                if ml:
                    for l in ml: st.markdown(l)
                else: st.markdown("✅ 核心推广语言已全部覆盖")
        if st.button("🔮 生成专项工具报告", key="btn_tools"):
            with st.spinner("AI 分析中..."):
                rs = build_review_summary(results, 12); pj = json.dumps(ps, ensure_ascii=False, indent=2)
                ms = "、".join([l.replace("❌ ","") for l in ml]) if ml else "无缺失"
                st.session_state.ai_results["tools"] = call_ai(
                    f"""角色：你是一位资深的 Steam 游戏数据分析师与LagoFast游戏辅助工具软件的产品经理。
任务：请分析以下 Excel 导出的 Steam 多语言玩家评论数据，忽略单纯宣泄情绪的无意义字眼，聚焦于玩家的“真实需求”与“痛点”。
LagoFast是什么：LagoFast是一款以steam游戏加速和功能开发为主，针对游戏需求研发相关所需工具（比如游戏翻译、互动资源地图、闪退修复，需分析玩家痛点和需求研发新工具）集合为一体的软件

分析维度要求：
1. 【语言与地区痛点】：不同语区（如俄语、英语、中文）玩家反映的集中问题是什么？是否存在特定地区的网络、本地化（翻译质量）问题？
2. 【软硬件运行环境痛点】：提取所有涉及卡顿（Stuttering）、崩溃（Crash）、闪退（Flashback）、掉帧（FPS Drop）、黑屏、无法启动、报错等问题。请归纳出受灾最严重的硬件配置或游戏阶段（若评论提及）。请专门筛选出文本中包含闪退、崩溃、卡顿、报错、黑屏的评论。分析他们是在什么场景下（如：开图、进背包、打 Boss）触发的，并归纳出可能存在的技术瓶颈，辨别是否为游戏本身的原因导致，列出解决方案。
3. 【玩法内容资源稀缺性】：玩家抱怨最多的游戏内容是什么？（例如：中后期资源太匮乏、某 Boss 难度不合理、缺乏某项功能指引、缺乏联机模式等）。

输出格式：
请以结构清晰的 Markdown 表格和条目化建议输出专项工具报告，并在最后按问题反馈数量从大到小提炼出“Top 5工具需求列表”（按需求优先级排序），每一条工具需求必须以实际的用户评论为依据，并引用完整的用户评论原话，需求分析必须以游戏为前提，仅对游戏进行分析；你可以发挥创意和想象，根据真实的玩家评论输出新的工具需求，包括但不限于游戏翻译、互动资源地图、闪退修复等工具。

数据来源：
根据Tab1中获取到的游戏评论全量文本进行分析

【本次会话中的实际输入数据】
游戏名称：{gn}
AppID：{st.session_state.last_app_id}
核心推广语言缺失（参考）：{ms}
痛点关键词统计（参考 JSON）：{pj}

【评论文本】（与 Tab1 抓取流程一致的多语言评论汇总，请逐条需求引用其中原话）
{rs}"""
                )
        if "tools" in st.session_state.ai_results:
            st.markdown("---\n##### 🛠️ 专项工具报告")
            # 直接按 Markdown 渲染 AI 输出，确保标题和表格格式正常显示
            st.markdown(st.session_state.ai_results["tools"])

# ============================================================
# Tab 3 - 推广策略辅助（原 Tab4）
# ============================================================
with tab3:
    if st.session_state.fetch_results is None:
        st.markdown('<div class="info-box">👈 请先完成数据抓取</div>', unsafe_allow_html=True)
    else:
        results = st.session_state.fetch_results; df = st.session_state.fetch_df
        gi = st.session_state.game_info or {}; gn = gi.get("name", f"AppID {st.session_state.last_app_id}")
        slc = st.session_state.supported_lang_codes or set()
        st.markdown("#### 📣 推广策略辅助")
        st.markdown('<div class="info-box">基于 Tab1/Tab2 数据，给出各语言地区推广重点</div>', unsafe_allow_html=True)
        st.markdown('<div class="notice-box">📌 本工具专注于游戏模式的相关功能推广</div>', unsafe_allow_html=True)
        dv = df[df["总评论数"]>0].head(13)
        if len(dv) > 0:
            fp = go.Figure()
            fp.add_trace(go.Bar(name="好评数", x=dv["语言"], y=dv["好评数"], marker_color="#3fb950"))
            fp.add_trace(go.Bar(name="差评数", x=dv["语言"], y=dv["差评数"], marker_color="#f85149"))
            lp = get_plotly_layout("各语言市场评论规模与口碑"); lp.update(barmode="stack", height=300, xaxis=dict(tickangle=-30)); fp.update_layout(**lp)
            st.plotly_chart(fp, use_container_width=True)
        st.markdown("---")
        if st.button("🚀 生成各语言地区推广重点", key="btn_promo"):
            with st.spinner("AI 生成推广策略（预计30秒）..."):
                dfs = df[df["总评论数"]>0].head(13).to_string(index=False)
                psc = analyze_pain_keywords(results); psm = json.dumps({k:sum(v.values()) for k,v in psc.items()}, ensure_ascii=False)
                csc = analyze_competitor_mentions(results); csm = json.dumps(csc, ensure_ascii=False)
                mll = [f"{name}({code})" for code, name in CORE_PROMO_LANGUAGES.items() if slc and code not in slc]
                ms = "、".join(mll) if mll else "无缺失"
                trr = st.session_state.ai_results.get("trainer_tri","")[:800]; tor = st.session_state.ai_results.get("tools","")[:500]
                sys_p = "你是 LagoFast 单机游戏修改器与单机游戏工具平台的全球推广负责人。竞品为风灵月影、WeMod、Wand；不可与竞品合作。你的目标是制定 LagoFast 自有产品的全球推广策略。不涉及联机、多人合作内容。"
                prompt = f"游戏：「{gn}」\n\n评论数据：\n{dfs}\n\n语言缺失：{ms}\n痛点：{psm}\n需求：{trr}\n{tor}\n\n竞品约束：风灵月影、WeMod、Wand 仅用于竞争分析，不可合作。\n\n请针对评论量前10的语言地区给出推广重点：\n## 各语言地区推广重点\n### [序号]. [语言] 地区\n**单机玩家画像** | **主要痛点** | **推广重点** | **内容方向** | **特别备注（体现差异化，且不出现任何合作方案）**\n\n最后输出总结表格"
                st.session_state.ai_results["promo"] = call_ai(prompt, system_prompt=sys_p)
        if "promo" in st.session_state.ai_results:
            st.markdown("---\n##### 📣 各语言地区推广重点报告")
            st.markdown(f'<div class="analysis-card">{st.session_state.ai_results["promo"]}</div>', unsafe_allow_html=True)

# ============================================================
# Tab 4 - 全站愿望单榜单
# ============================================================
with tab4:
    render_global_wishlist_tab()

# 底部
st.markdown("---")
st.markdown('<div style="text-align:center;color:#6e7681;font-size:12px;padding:16px 0;line-height:2;">🎮 LagoFast 游戏分析辅助 v2.0 &nbsp;|&nbsp; ⚠️ 该AI工具输出结论仅做辅助参考 &nbsp;|&nbsp; <span style="color:#58a6ff;">by: Yanghao（from lijiaqi）</span><br>📝 日志：<br>1、2026年4月24日 修复了导出数据问题、MiniMax API问题；<br>2、2026年4月27日优化了痛点关键词的语言来源；<br>3、2026年5月18日写死了API配置，无需每次重新输入API KEY</div>', unsafe_allow_html=True)
