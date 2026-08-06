from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any, Callable
import re
import json

import httpx
import pandas as pd

from steam_intel.country_metrics import (
    CountryDistribution,
    MetricStatus,
    distribution_from_percent_mapping,
    parse_gamalytic_active_users_regions,
    unavailable_distribution,
    unverified_wishlist_insights_distribution,
)


WISHLIST_API_URL = "https://partner.steam-api.com/IPartnerFinancialsService/GetAppWishlistReporting/v001/"
STEAM_SEARCH_RESULTS_URL = "https://store.steampowered.com/search/results/"
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"
GAMALYTIC_GAME_DETAILS_URL = "https://gamalytic.com/api/game-details/{app_id}"
GAMALYTIC_API_GAME_URL = "https://api.gamalytic.com/game/{app_id}"
GAMALYTIC_API_ACTIVE_USERS_REGIONS_URL = "https://api.gamalytic.com/game/{app_id}/active-users-regions"
GAMALYTIC_API_WISHLIST_INSIGHTS_URL = "https://api.gamalytic.com/game/{app_id}/wishlist-insights"
GAMALYTIC_CACHE_DIR = Path(__file__).resolve().parent / ".cache" / "gamalytic"

REGION_OPTIONS = {
    "US": "美国",
    "CN": "中国",
    "JP": "日本",
    "KR": "韩国",
    "DE": "德国",
    "FR": "法国",
    "GB": "英国",
    "BR": "巴西",
    "RU": "俄罗斯",
    "TR": "土耳其",
}

COUNTRY_NAMES = {
    "us": "美国",
    "gb": "英国",
    "cn": "中国",
    "jp": "日本",
    "kr": "韩国",
    "de": "德国",
    "fr": "法国",
    "br": "巴西",
    "ru": "俄罗斯",
    "tr": "土耳其",
    "ca": "加拿大",
    "au": "澳大利亚",
    "pl": "波兰",
    "it": "意大利",
    "es": "西班牙",
    "mx": "墨西哥",
    "ar": "阿根廷",
    "in": "印度",
    "id": "印度尼西亚",
    "th": "泰国",
    "vn": "越南",
    "nl": "荷兰",
    "se": "瑞典",
    "no": "挪威",
    "dk": "丹麦",
    "fi": "芬兰",
    "be": "比利时",
    "ch": "瑞士",
    "at": "奥地利",
    "pt": "葡萄牙",
    "gr": "希腊",
    "cz": "捷克",
    "hu": "匈牙利",
    "ro": "罗马尼亚",
    "ua": "乌克兰",
    "za": "南非",
    "cl": "智利",
    "co": "哥伦比亚",
    "pe": "秘鲁",
    "my": "马来西亚",
    "sg": "新加坡",
    "ph": "菲律宾",
    "tw": "中国台湾",
    "hk": "中国香港",
    "sa": "沙特阿拉伯",
    "ae": "阿联酋",
    "il": "以色列",
    "eg": "埃及",
}

COUNTRY_CODE_ALIASES = {
    "united states": "us",
    "usa": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "great britain": "gb",
    "china": "cn",
    "mainland china": "cn",
    "taiwan": "tw",
    "hong kong": "hk",
    "south korea": "kr",
    "korea": "kr",
    "russia": "ru",
    "turkiye": "tr",
    "turkey": "tr",
    "czech republic": "cz",
    "japan": "jp",
    "germany": "de",
    "france": "fr",
    "brazil": "br",
    "canada": "ca",
    "australia": "au",
    "poland": "pl",
    "italy": "it",
    "spain": "es",
    "mexico": "mx",
    "argentina": "ar",
    "india": "in",
    "indonesia": "id",
    "thailand": "th",
    "vietnam": "vn",
    "netherlands": "nl",
    "sweden": "se",
    "norway": "no",
    "denmark": "dk",
    "finland": "fi",
    "belgium": "be",
    "switzerland": "ch",
    "austria": "at",
    "portugal": "pt",
    "greece": "gr",
    "hungary": "hu",
    "romania": "ro",
    "ukraine": "ua",
    "south africa": "za",
    "chile": "cl",
    "colombia": "co",
    "peru": "pe",
    "malaysia": "my",
    "singapore": "sg",
    "philippines": "ph",
    "saudi arabia": "sa",
    "united arab emirates": "ae",
    "israel": "il",
    "egypt": "eg",
}

LANGUAGE_MARKETS = {
    "english": "英语市场",
    "schinese": "简中市场",
    "tchinese": "繁中市场",
    "japanese": "日本",
    "koreana": "韩国",
    "russian": "俄语/CIS",
    "german": "德语区",
    "french": "法语区",
    "spanish": "西语欧洲",
    "latam": "拉美西语",
    "brazilian": "巴西/葡语",
    "portuguese": "葡语欧洲",
    "turkish": "土耳其",
    "thai": "泰国",
    "vietnamese": "越南",
    "polish": "波兰",
    "italian": "意大利",
}


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date) -> list[date]:
    if end < start:
        start, end = end, start
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def default_range(days: int) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=max(days - 1, 0)), end


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _match(pattern: str, text: str, default: str = "") -> str:
    found = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
    return unescape(found.group(1)).strip() if found else default


def parse_popular_wishlist_html(results_html: str, start_rank: int = 1) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    blocks = re.findall(
        r'(<a\b[^>]*class="[^"]*search_result_row[^"]*"[^>]*>.*?</a>)',
        results_html or "",
        flags=re.DOTALL | re.IGNORECASE,
    )

    for offset, block in enumerate(blocks):
        app_id = _match(r'data-ds-appid="(\d+)"', block)
        if not app_id:
            href = _match(r'href="([^"]+)"', block)
            app_id = _match(r"/app/(\d+)/", href)
        if not app_id:
            continue

        title = _clean_html_text(_match(r'<span class="title">(.*?)</span>', block))
        release_date = _clean_html_text(_match(r'<div class="search_released[^"]*">(.*?)</div>', block))
        image_url = _match(r'<img src="([^"]+)"', block)
        review = _clean_html_text(_match(r'data-tooltip-html="([^"]+)"', block))
        price_final = _match(r'data-price-final="(\d+)"', block)
        tag_ids = _match(r'data-ds-tagids="\[([^\]]*)\]"', block)
        platforms = []
        for platform, label in [("win", "Windows"), ("mac", "Mac"), ("linux", "Linux")]:
            if f"platform_img {platform}" in block:
                platforms.append(label)

        rows.append(
            {
                "愿望单排名": start_rank + offset,
                "AppID": app_id,
                "游戏名称": title or f"App {app_id}",
                "发售状态/日期": release_date,
                "评价摘要": review,
                "平台": ", ".join(platforms),
                "价格(美分)": int(price_final) if price_final else 0,
                "标签ID": tag_ids,
                "商店链接": f"https://store.steampowered.com/app/{app_id}/",
                "封面图": image_url,
            }
        )
    return rows


def fetch_popular_wishlist_apps(
    limit: int = 100,
    country: str = "ALL",
    language: str = "english",
    timeout: float = 20.0,
) -> tuple[pd.DataFrame, int]:
    limit = max(1, min(int(limit), 500))
    rows: list[dict[str, Any]] = []
    total_count = 0

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for start in range(0, limit, 50):
            count = min(50, limit - start)
            params = {
                "filter": "popularwishlist",
                "start": str(start),
                "count": str(count),
                "infinite": "1",
                "l": language,
            }
            if country and country.upper() != "ALL":
                params["cc"] = country
            resp = client.get(
                STEAM_SEARCH_RESULTS_URL,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            payload = resp.json()
            total_count = int(payload.get("total_count") or total_count or 0)
            rows.extend(parse_popular_wishlist_html(payload.get("results_html", ""), start_rank=start + 1))
            time.sleep(0.15)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["AppID"]).sort_values("愿望单排名").head(limit).reset_index(drop=True)
    return df, total_count


def search_steam_games(
    query: str,
    limit: int = 10,
    country: str = "ALL",
    language: str = "english",
    timeout: float = 20.0,
) -> pd.DataFrame:
    """Search Steam's public store catalogue without inferring any market metric."""

    query = str(query).strip()
    if not query:
        return pd.DataFrame()
    limit = max(1, min(int(limit), 25))
    params = {"term": query, "start": "0", "count": str(limit), "infinite": "1", "l": language}
    if country and country.upper() != "ALL":
        params["cc"] = country
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(
            STEAM_SEARCH_RESULTS_URL,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()
    rows = parse_popular_wishlist_html(payload.get("results_html", ""))
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.drop_duplicates(subset=["AppID"]).head(limit).reset_index(drop=True)
    frame = frame.rename(columns={"愿望单排名": "搜索排序"})
    return frame


def _read_gamalytic_cache(app_id: str, max_age_seconds: int) -> dict[str, Any] | None:
    cache_path = GAMALYTIC_CACHE_DIR / f"{app_id}.json"
    if not cache_path.is_file():
        return None
    if time.time() - cache_path.stat().st_mtime > max_age_seconds:
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_gamalytic_cache(app_id: str, data: dict[str, Any]) -> None:
    try:
        GAMALYTIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (GAMALYTIC_CACHE_DIR / f"{app_id}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def fetch_gamalytic_game_details(app_id: str, timeout: float = 20.0, retries: int = 2, cache_ttl_seconds: int = 86400) -> dict[str, Any]:
    app_id = str(app_id).strip()
    if not app_id.isdigit():
        raise ValueError("AppID 必须是数字")
    cached = _read_gamalytic_cache(app_id, cache_ttl_seconds)
    if cached is not None:
        return cached
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://gamalytic.com/game/{app_id}",
    }
    last_status = None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(max(1, retries + 1)):
            resp = client.get(GAMALYTIC_GAME_DETAILS_URL.format(app_id=app_id), headers=headers)
            last_status = resp.status_code
            if resp.status_code == 429:
                retry_after = resp.headers.get("retry-after")
                wait_seconds = min(10.0, float(retry_after)) if retry_after and retry_after.isdigit() else min(10.0, 2.0 * (attempt + 1))
                if attempt < retries:
                    time.sleep(wait_seconds)
                    continue
                raise RuntimeError(f"Gamalytic 请求被限流（429）。请等待一会儿再试，或减少重复查询。")
            if resp.status_code == 403:
                raise RuntimeError("Gamalytic 拒绝访问该接口（403）。公开接口可能临时限制访问。")
            resp.raise_for_status()
            payload = resp.json()
            break
        else:
            raise RuntimeError(f"Gamalytic 请求失败，HTTP {last_status}")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Gamalytic 未返回游戏详情数据")
    _write_gamalytic_cache(app_id, data)
    return data


def gamalytic_country_data_frame(data: dict[str, Any]) -> pd.DataFrame:
    country_data = data.get("countryData") or {}
    if not isinstance(country_data, dict):
        return pd.DataFrame()
    distribution = distribution_from_percent_mapping(
        country_data,
        metric="players",
        source="Gamalytic public countryData（玩家估算）",
        country_names=COUNTRY_NAMES,
        reported_top_n_only=True,
        add_undisclosed_remainder=True,
    )
    return distribution.to_frame("玩家占比(%)") if distribution.available else pd.DataFrame()


def gamalytic_summary_frame(data: dict[str, Any]) -> pd.DataFrame:
    fields = [
        ("AppID", data.get("steamId")),
        ("游戏名称", data.get("name")),
        ("预计玩家", data.get("players")),
        ("预计拥有者", data.get("owners")),
        ("预计销量", data.get("copiesSold")),
        ("预计收入($)", data.get("revenue")),
        ("愿望单估算", data.get("wishlists")),
        ("Steam全站愿望单排名", data.get("topWish")),
        ("关注者", data.get("followers")),
        ("评论数", data.get("reviews")),
        ("Steam购买占比", data.get("steamPercent")),
    ]
    return pd.DataFrame([{"指标": key, "值": value if value is not None else "N/A"} for key, value in fields])


def _gamalytic_api_headers(api_key: str) -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "api-key": api_key.strip(),
    }


def fetch_gamalytic_api_json(url: str, api_key: str, timeout: float = 30.0) -> Any:
    if not api_key or not api_key.strip():
        raise ValueError("缺少 Gamalytic API key")
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, headers=_gamalytic_api_headers(api_key))
        if resp.status_code == 403:
            raise RuntimeError("Gamalytic API 返回 403：该接口需要有效 API key，部分接口需要 Pro 权限。")
        if resp.status_code == 429:
            raise RuntimeError("Gamalytic API 返回 429：请求过于频繁，请稍后再试。")
        resp.raise_for_status()
        return resp.json()


def _gamalytic_error_distribution(metric: str, source: str, exc: Exception) -> CountryDistribution:
    message = str(exc)
    if "429" in message:
        status = MetricStatus.RATE_LIMITED
    elif "403" in message:
        status = MetricStatus.FORBIDDEN
    else:
        status = MetricStatus.UNAVAILABLE
    return unavailable_distribution(metric, source, status, message)


def fetch_gamalytic_active_users_regions(app_id: str, api_key: str) -> CountryDistribution:
    source = "Gamalytic active-users-regions"
    try:
        payload = fetch_gamalytic_api_json(
            GAMALYTIC_API_ACTIVE_USERS_REGIONS_URL.format(app_id=str(app_id).strip()),
            api_key,
        )
    except Exception as exc:
        return _gamalytic_error_distribution("active_users", source, exc)
    return parse_gamalytic_active_users_regions(payload, COUNTRY_NAMES)


def fetch_gamalytic_wishlist_country_distribution(app_id: str, api_key: str) -> CountryDistribution:
    source = "Gamalytic wishlist-insights"
    try:
        fetch_gamalytic_api_json(
            GAMALYTIC_API_WISHLIST_INSIGHTS_URL.format(app_id=str(app_id).strip()),
            api_key,
        )
    except Exception as exc:
        return _gamalytic_error_distribution("wishlists", source, exc)
    return unverified_wishlist_insights_distribution()


def extract_country_distribution(
    payload: Any,
    value_label: str,
    source: str,
    top_n: int = 20,
    prefer_path_keywords: tuple[str, ...] = (),
) -> pd.DataFrame:
    # Deprecated safety guard: unknown provider schemas must not be guessed.
    return pd.DataFrame(columns=["排名", "国家代码", "国家/地区", value_label, "数据源"])

    candidates: list[dict[str, Any]] = []

    def normalize_country_code(code: Any) -> str:
        code_str = str(code).strip().lower()
        if len(code_str) == 2:
            return code_str
        return COUNTRY_CODE_ALIASES.get(code_str, "")

    def add_country(code: Any, value: Any, path: str = "") -> None:
        code_str = normalize_country_code(code)
        if not code_str:
            return
        try:
            val = float(value)
        except (TypeError, ValueError):
            return
        if val <= 0:
            return
        candidates.append(
            {
                "国家代码": code_str.upper(),
                "国家/地区": COUNTRY_NAMES.get(code_str, code_str.upper()),
                value_label: val,
                "数据源": source,
                "_path": path.lower(),
            }
        )

    def pick_country_value(obj: dict[str, Any]) -> Any:
        for key in (
            "percentage",
            "percent",
            "pct",
            "share",
            "countryShare",
            "wishlistShare",
            "wishlistsShare",
            "wishlistPercent",
            "wishlistPercentage",
            "mauShare",
            "value",
            "count",
            "total",
            "mau",
            "users",
            "wishlists",
            "wishlist",
            "wishlist_count",
            "wishlistCount",
            "additions",
            "adds",
        ):
            if key in obj and obj.get(key) is not None:
                return obj.get(key)
        return None

    def walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            # Shape: {"us": 34.7, "cn": 8.3}
            country_like = [(k, v) for k, v in obj.items() if isinstance(k, str) and len(k.strip()) == 2 and isinstance(v, (int, float))]
            if len(country_like) >= 2:
                for k, v in country_like:
                    add_country(k, v, path)
            # Shape: {"us": {"wishlists": 12345}, "gb": {"wishlists": 4567}}
            for key, value in obj.items():
                code = normalize_country_code(key)
                if not code:
                    continue
                if isinstance(value, dict):
                    picked = pick_country_value(value)
                    if picked is not None:
                        add_country(code, picked, f"{path}.{key}")
                elif isinstance(value, list) and len(value) == 1 and isinstance(value[0], (int, float)):
                    add_country(code, value[0], f"{path}.{key}")
            # Shape: {"country": "us", "percentage": 34.7}
            country = (
                obj.get("country")
                or obj.get("countryCode")
                or obj.get("country_code")
                or obj.get("code")
                or obj.get("iso2")
                or obj.get("iso")
                or obj.get("cc")
                or obj.get("region")
                or obj.get("regionCode")
            )
            value = pick_country_value(obj)
            if country is not None and value is not None:
                add_country(country, value, path)
            for key, value in obj.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(obj, list):
            # Shape: [["us", 34.7], ["gb", 8.6]]
            for item in obj:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    add_country(item[0], item[1], path)
                walk(item, path)

    walk(payload)
    if not candidates:
        return pd.DataFrame()
    df = pd.DataFrame(candidates)
    if prefer_path_keywords:
        preferred = df[df["_path"].apply(lambda p: any(keyword in p for keyword in prefer_path_keywords))].copy()
        if not preferred.empty:
            df = preferred
    df = df.groupby(["国家代码", "国家/地区", "数据源"], as_index=False)[value_label].max()
    total = float(df[value_label].sum())
    max_value = float(df[value_label].max())
    if 0 < total <= 1.05:
        df[value_label] = df[value_label] * 100
    elif max_value > 100 or total > 100.5:
        df[value_label] = df[value_label] / total * 100
    df[value_label] = df[value_label].round(2)
    df = df.sort_values(value_label, ascending=False).head(top_n).reset_index(drop=True)
    df.insert(0, "排名", range(1, len(df) + 1))
    return df


def fetch_regional_wishlist_interest(
    regions: list[str],
    limit_per_region: int = 100,
    language: str = "english",
    timeout: float = 20.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deprecated: public store ranks cannot identify wishlist-country shares."""
    return pd.DataFrame(), pd.DataFrame()

    regions = [r for r in regions if r and r.upper() != "ALL"]
    if not regions:
        regions = ["US", "CN", "JP", "KR", "DE", "FR", "GB"]

    all_rows: list[pd.DataFrame] = []
    for region in regions:
        df, _ = fetch_popular_wishlist_apps(limit=limit_per_region, country=region, language=language, timeout=timeout)
        if df.empty:
            continue
        rank_col = "愿望单排名" if "愿望单排名" in df.columns else df.columns[0]
        app_col = "AppID"
        name_col = "游戏名称" if "游戏名称" in df.columns else df.columns[2]
        region_df = df[[rank_col, app_col, name_col]].copy()
        region_df.columns = ["地区排名", "AppID", "游戏名称"]
        region_df["地区代码"] = region
        region_df["地区"] = REGION_OPTIONS.get(region, region)
        region_df["兴趣分"] = region_df["地区排名"].apply(lambda rank: max(limit_per_region + 1 - int(rank), 0) / limit_per_region)
        all_rows.append(region_df)
        time.sleep(0.15)

    if not all_rows:
        return pd.DataFrame(), pd.DataFrame()

    long_df = pd.concat(all_rows, ignore_index=True)
    rank_variance = (
        long_df.groupby("AppID", as_index=False)["地区排名"]
        .nunique()
        .rename(columns={"地区排名": "地区排名差异数"})
    )
    totals = long_df.groupby("AppID", as_index=False)["兴趣分"].sum().rename(columns={"兴趣分": "总兴趣分"})
    long_df = long_df.merge(totals, on="AppID", how="left")
    long_df = long_df.merge(rank_variance, on="AppID", how="left")
    long_df["区域信号状态"] = long_df["地区排名差异数"].apply(lambda n: "有地区差异" if int(n) > 1 else "无地区差异")
    long_df["区域兴趣占比(%)"] = 0.0
    mask = (long_df["总兴趣分"] > 0) & (long_df["地区排名差异数"] > 1)
    long_df.loc[mask, "区域兴趣占比(%)"] = (
        long_df.loc[mask, "兴趣分"] / long_df.loc[mask, "总兴趣分"] * 100
    ).round(2)

    wide = long_df.pivot_table(
        index=["AppID", "游戏名称"],
        columns="地区",
        values="区域兴趣占比(%)",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide["覆盖地区数"] = long_df.groupby("AppID")["地区"].nunique().reindex(wide["AppID"]).values
    wide["地区排名差异数"] = rank_variance.set_index("AppID").reindex(wide["AppID"])["地区排名差异数"].fillna(0).astype(int).values
    wide["区域信号状态"] = wide["地区排名差异数"].apply(lambda n: "有地区差异" if int(n) > 1 else "无地区差异")
    wide["总兴趣分"] = totals.set_index("AppID").reindex(wide["AppID"])["总兴趣分"].fillna(0).values
    wide = wide.sort_values(["地区排名差异数", "覆盖地区数", "总兴趣分"], ascending=[False, False, False]).reset_index(drop=True)

    return long_df, wide


def app_row(app_id: str, name: str | None = None, rank: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "愿望单排名": int(rank),
                "AppID": str(app_id).strip(),
                "游戏名称": name or f"App {str(app_id).strip()}",
            }
        ]
    )


def find_app_in_regional_wishlists(
    app_id: str,
    regions: list[str],
    scan_limit: int = 500,
    language: str = "english",
) -> pd.DataFrame:
    """Deprecated: a regional store rank is not a wishlist-country distribution."""
    return pd.DataFrame(
        [{"AppID": str(app_id).strip(), "状态": "unavailable", "说明": "公开地区榜单不能推导愿望单国家分布。"}]
    )

    rows: list[dict[str, Any]] = []
    target = str(app_id).strip()
    for region in [r for r in regions if r and r.upper() != "ALL"]:
        df, _ = fetch_popular_wishlist_apps(limit=scan_limit, country=region, language=language)
        if df.empty or "AppID" not in df.columns:
            rows.append({"AppID": target, "地区代码": region, "地区": REGION_OPTIONS.get(region, region), "地区排名": None, "是否进入榜单": False})
            continue
        rank_col = "愿望单排名" if "愿望单排名" in df.columns else df.columns[0]
        name_col = "游戏名称" if "游戏名称" in df.columns else df.columns[2]
        hit = df[df["AppID"].astype(str) == target]
        if hit.empty:
            rows.append({"AppID": target, "地区代码": region, "地区": REGION_OPTIONS.get(region, region), "地区排名": None, "是否进入榜单": False})
        else:
            first = hit.iloc[0]
            rows.append(
                {
                    "AppID": target,
                    "游戏名称": first[name_col],
                    "地区代码": region,
                    "地区": REGION_OPTIONS.get(region, region),
                    "地区排名": int(first[rank_col]),
                    "是否进入榜单": True,
                }
            )
        time.sleep(0.15)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    ranked = out[out["是否进入榜单"] & out["地区排名"].notna()].copy()
    out["愿望单区域兴趣占比(%)"] = 0.0
    if not ranked.empty and ranked["地区排名"].nunique() > 1:
        ranked["兴趣分"] = ranked["地区排名"].apply(lambda rank: max(scan_limit + 1 - int(rank), 0) / scan_limit)
        total = ranked["兴趣分"].sum()
        if total > 0:
            ranked["愿望单区域兴趣占比(%)"] = (ranked["兴趣分"] / total * 100).round(2)
            out = out.drop(columns=["愿望单区域兴趣占比(%)"]).merge(
                ranked[["地区代码", "愿望单区域兴趣占比(%)"]],
                on="地区代码",
                how="left",
            )
            out["愿望单区域兴趣占比(%)"] = out["愿望单区域兴趣占比(%)"].fillna(0)
    out["区域信号状态"] = "有地区差异" if ranked["地区排名"].nunique() > 1 else "无地区差异"
    return out


def fetch_review_summary(
    app_id: str,
    language: str,
    purchase_type: str = "steam",
    timeout: float = 15.0,
) -> dict[str, Any]:
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(
            STEAM_REVIEWS_URL.format(app_id=app_id),
            params={
                "json": "1",
                "language": language,
                "num_per_page": "0",
                "purchase_type": purchase_type,
                "filter": "summary",
            },
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
    summary = payload.get("query_summary") or {}
    return {
        "评论数": int(summary.get("total_reviews") or 0),
        "好评数": int(summary.get("total_positive") or 0),
        "差评数": int(summary.get("total_negative") or 0),
        "评价摘要": summary.get("review_score_desc") or "",
    }


def fetch_purchase_language_distribution(
    apps: pd.DataFrame,
    languages: list[str],
    top_n: int = 20,
    purchase_type: str = "steam",
    timeout: float = 15.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deprecated: review language is not buyer-country data."""
    return pd.DataFrame(), pd.DataFrame()

    if apps is None or apps.empty:
        return pd.DataFrame(), pd.DataFrame()
    if not languages:
        languages = ["english", "schinese", "japanese", "koreana", "russian", "german", "french", "spanish", "brazilian"]

    app_col = "AppID"
    name_col = "游戏名称" if "游戏名称" in apps.columns else apps.columns[2]
    rank_col = "愿望单排名" if "愿望单排名" in apps.columns else apps.columns[0]
    rows: list[dict[str, Any]] = []

    for _, app in apps.head(top_n).iterrows():
        app_id = str(app[app_col])
        app_name = str(app[name_col])
        rank = int(app[rank_col])
        for language in languages:
            try:
                summary = fetch_review_summary(app_id, language, purchase_type=purchase_type, timeout=timeout)
                review_count = summary["评论数"]
                rows.append(
                    {
                        "愿望单排名": rank,
                        "AppID": app_id,
                        "游戏名称": app_name,
                        "语言代码": language,
                        "市场": LANGUAGE_MARKETS.get(language, language),
                        "购买评论数": review_count,
                        "好评数": summary["好评数"],
                        "差评数": summary["差评数"],
                        "评价摘要": summary["评价摘要"],
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "愿望单排名": rank,
                        "AppID": app_id,
                        "游戏名称": app_name,
                        "语言代码": language,
                        "市场": LANGUAGE_MARKETS.get(language, language),
                        "购买评论数": 0,
                        "好评数": 0,
                        "差评数": 0,
                        "评价摘要": f"抓取失败: {str(exc)[:80]}",
                    }
                )
            time.sleep(0.08)

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        return long_df, pd.DataFrame()

    totals = long_df.groupby("AppID", as_index=False)["购买评论数"].sum().rename(columns={"购买评论数": "购买评论总样本"})
    long_df = long_df.merge(totals, on="AppID", how="left")
    long_df["购买玩家区域估算占比(%)"] = 0.0
    mask = long_df["购买评论总样本"] > 0
    long_df.loc[mask, "购买玩家区域估算占比(%)"] = (
        long_df.loc[mask, "购买评论数"] / long_df.loc[mask, "购买评论总样本"] * 100
    ).round(2)

    wide = long_df.pivot_table(
        index=["愿望单排名", "AppID", "游戏名称"],
        columns="市场",
        values="购买玩家区域估算占比(%)",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    wide["购买评论总样本"] = totals.set_index("AppID").reindex(wide["AppID"])["购买评论总样本"].fillna(0).values
    wide = wide.sort_values(["愿望单排名"]).reset_index(drop=True)
    return long_df, wide


def _num(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_wishlist_response(app_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("response") or {}
    has_summary = isinstance(body.get("wishlist_summary"), dict)
    summary = body.get("wishlist_summary") or {}
    countries_raw = body.get("country_summary") or []

    countries = []
    for item in countries_raw:
        actions = item.get("summary_actions") or {}
        countries.append(
            {
                "国家代码": item.get("country_code") or "",
                "国家/地区": item.get("country_name") or item.get("country_code") or "",
                "区域": item.get("region") or "",
                "新增愿望单": _num(actions.get("wishlist_adds")),
                "删除愿望单": _num(actions.get("wishlist_deletes")),
                "购买转化": _num(actions.get("wishlist_purchases")),
                "礼物转化": _num(actions.get("wishlist_gifts")),
            }
        )

    adds = _num(summary.get("wishlist_adds"))
    deletes = _num(summary.get("wishlist_deletes"))
    purchases = _num(summary.get("wishlist_purchases"))
    gifts = _num(summary.get("wishlist_gifts"))

    return {
        "AppID": str(app_id),
        "日期": body.get("date") or "",
        "报表状态": "有报表" if has_summary else "无报表",
        "新增愿望单": adds,
        "删除愿望单": deletes,
        "购买转化": purchases,
        "礼物转化": gifts,
        "净新增": adds - deletes - purchases - gifts,
        "Windows新增": _num(summary.get("wishlist_adds_windows")),
        "Mac新增": _num(summary.get("wishlist_adds_mac")),
        "Linux新增": _num(summary.get("wishlist_adds_linux")),
        "最早可用日期": body.get("app_min_date") or "",
        "生成时间": body.get("time_generated") or "",
        "国家明细": countries,
        "原始响应": payload,
    }


def fetch_wishlist_for_date(
    app_id: str,
    api_key: str,
    target_date: date,
    proxy_config: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("缺少 Steam Financial API Key")
    if not str(app_id).strip().isdigit():
        raise ValueError("AppID 必须是数字")

    params = {"key": api_key.strip(), "appid": str(app_id).strip(), "date": target_date.isoformat()}
    with httpx.Client(timeout=timeout, follow_redirects=True, **(proxy_config or {})) as client:
        resp = client.get(WISHLIST_API_URL, params=params)
        if resp.status_code in (401, 403):
            raise RuntimeError("Steam Financial API Key 无效或没有该 App 的权限")
        resp.raise_for_status()
        payload = resp.json()

    return normalize_wishlist_response(str(app_id).strip(), payload)


def diagnose_wishlist_request(
    app_id: str,
    api_key: str,
    target_date: date,
    proxy_config: dict[str, Any] | None = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    params = {"key": api_key.strip(), "appid": str(app_id).strip(), "date": target_date.isoformat()}
    url = httpx.URL(WISHLIST_API_URL, params=params)
    safe_url = str(url).replace(api_key.strip(), "***")

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, **(proxy_config or {})) as client:
            resp = client.get(WISHLIST_API_URL, params=params)
            status_code = resp.status_code
            text = resp.text[:1200]
            try:
                payload = resp.json()
            except Exception:
                payload = {}
    except Exception as exc:
        return {
            "请求地址": safe_url,
            "HTTP状态": "请求失败",
            "错误": str(exc),
            "响应字段": [],
            "报表状态": "请求失败",
            "最早可用日期": "",
            "响应预览": "",
        }

    body = payload.get("response") if isinstance(payload, dict) else None
    body = body if isinstance(body, dict) else {}
    has_summary = isinstance(body.get("wishlist_summary"), dict)

    return {
        "请求地址": safe_url,
        "HTTP状态": status_code,
        "错误": "" if status_code < 400 else text,
        "响应字段": list(body.keys()),
        "报表状态": "有报表" if has_summary else "空报表",
        "最早可用日期": body.get("app_min_date") or "",
        "返回AppID": body.get("appid") or "",
        "返回日期": body.get("date") or "",
        "响应预览": text,
    }


def fetch_wishlist_range(
    app_id: str,
    api_key: str,
    start: date,
    end: date,
    proxy_config: dict[str, Any] | None = None,
    progress: Callable[[int, int, date], None] | None = None,
    sleep_seconds: float = 0.25,
    timeout: float = 12.0,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    country_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    days = date_range(start, end)

    for idx, day in enumerate(days, start=1):
        if progress:
            progress(idx, len(days), day)
        try:
            report = fetch_wishlist_for_date(app_id, api_key, day, proxy_config=proxy_config, timeout=timeout)
            rows.append({k: v for k, v in report.items() if k not in ("国家明细", "原始响应")})
            if report["报表状态"] != "有报表":
                errors.append(
                    f"{day.isoformat()}: Steam 返回空报表"
                    + (f"，该 App 最早可用日期为 {report['最早可用日期']}" if report["最早可用日期"] else "")
                )
            for country in report["国家明细"]:
                country_rows.append({"日期": report["日期"] or day.isoformat(), **country})
        except Exception as exc:
            errors.append(f"{day.isoformat()}: {exc}")
        time.sleep(sleep_seconds)

    df = pd.DataFrame(rows)
    if not df.empty:
        if "日期" in df.columns:
            df["日期"] = df.apply(lambda row: row["日期"] or "", axis=1)
        df = df.sort_values(["报表状态", "日期"], ascending=[True, True]).reset_index(drop=True)

    country_df = pd.DataFrame(country_rows)
    if not country_df.empty:
        country_df = country_df.sort_values(["日期", "新增愿望单"], ascending=[True, False]).reset_index(drop=True)

    return df, country_df, errors


def summarize_wishlist(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "新增愿望单": 0,
            "删除愿望单": 0,
            "购买转化": 0,
            "礼物转化": 0,
            "净新增": 0,
            "峰值日期": "N/A",
            "峰值新增": 0,
        }

    if "报表状态" in df.columns:
        valid_df = df[df["报表状态"] == "有报表"].copy()
    else:
        valid_df = df.copy()
    if valid_df.empty:
        valid_df = df.copy()

    peak_idx = valid_df["新增愿望单"].idxmax()
    return {
        "新增愿望单": int(valid_df["新增愿望单"].sum()),
        "删除愿望单": int(valid_df["删除愿望单"].sum()),
        "购买转化": int(valid_df["购买转化"].sum()),
        "礼物转化": int(valid_df["礼物转化"].sum()),
        "净新增": int(valid_df["净新增"].sum()),
        "峰值日期": str(valid_df.loc[peak_idx, "日期"] or "N/A"),
        "峰值新增": int(valid_df.loc[peak_idx, "新增愿望单"]),
    }


def country_summary(country_df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    if country_df.empty:
        return pd.DataFrame(columns=["国家/地区", "新增愿望单", "删除愿望单", "购买转化", "礼物转化", "净新增"])

    grouped = (
        country_df.groupby("国家/地区", as_index=False)[["新增愿望单", "删除愿望单", "购买转化", "礼物转化"]]
        .sum()
        .sort_values("新增愿望单", ascending=False)
    )
    grouped["净新增"] = grouped["新增愿望单"] - grouped["删除愿望单"] - grouped["购买转化"] - grouped["礼物转化"]
    return grouped.head(top_n).reset_index(drop=True)
