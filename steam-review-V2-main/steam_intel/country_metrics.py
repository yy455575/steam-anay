from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping

import pandas as pd


class MetricStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    SCHEMA_CHANGED = "schema_changed"
    INVALID_DATA = "invalid_data"


@dataclass(frozen=True)
class CountryShare:
    country_code: str
    country_name: str
    share_percent: float


@dataclass
class CountryDistribution:
    metric: str
    source: str
    status: MetricStatus
    rows: list[CountryShare] = field(default_factory=list)
    message: str = ""
    reported_share_percent: float = 0.0
    is_complete: bool = False
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = ""

    @property
    def available(self) -> bool:
        return self.status == MetricStatus.AVAILABLE and bool(self.rows)

    def to_frame(self, value_label: str) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=["排名", "国家代码", "国家/地区", value_label, "数据源"])
        frame = pd.DataFrame(
            [
                {
                    "国家代码": row.country_code,
                    "国家/地区": row.country_name,
                    value_label: row.share_percent,
                    "数据源": self.source,
                }
                for row in self.rows
            ]
        )
        frame = frame.sort_values(value_label, ascending=False, kind="stable").reset_index(drop=True)
        frame.insert(0, "排名", range(1, len(frame) + 1))
        return frame


def unavailable_distribution(metric: str, source: str, status: MetricStatus, message: str) -> CountryDistribution:
    return CountryDistribution(metric=metric, source=source, status=status, message=message)


def distribution_from_percent_mapping(
    country_percentages: Mapping[str, Any],
    *,
    metric: str,
    source: str,
    country_names: Mapping[str, str],
    reported_top_n_only: bool = False,
    add_undisclosed_remainder: bool = False,
) -> CountryDistribution:
    """Build a distribution only from an explicit country-code -> percentage contract.

    This deliberately never rescales counts, fractions, ranks, or arbitrary numeric
    fields into percentages. A provider must send a 0..100 percentage per country.
    """

    rows: list[CountryShare] = []
    seen: set[str] = set()
    reported_share = 0.0
    for raw_code, raw_share in country_percentages.items():
        code = str(raw_code).strip().lower()
        if len(code) != 2 or not code.isalpha():
            return unavailable_distribution(
                metric,
                source,
                MetricStatus.INVALID_DATA,
                f"数据源返回了无效国家代码：{raw_code!r}。",
            )
        if code in seen:
            return unavailable_distribution(metric, source, MetricStatus.INVALID_DATA, f"国家代码 {code.upper()} 重复。")
        try:
            share = float(raw_share)
        except (TypeError, ValueError):
            return unavailable_distribution(metric, source, MetricStatus.INVALID_DATA, f"国家 {code.upper()} 的占比不是数字。")
        if not 0.0 <= share <= 100.0:
            return unavailable_distribution(
                metric,
                source,
                MetricStatus.INVALID_DATA,
                f"国家 {code.upper()} 的占比 {share} 不在 0 到 100 范围内。",
            )
        seen.add(code)
        reported_share += share
        rows.append(CountryShare(code.upper(), country_names.get(code, code.upper()), round(share, 2)))

    if not rows:
        return unavailable_distribution(metric, source, MetricStatus.UNAVAILABLE, "数据源没有返回国家占比。")
    if reported_share > 100.0001:
        return unavailable_distribution(
            metric,
            source,
            MetricStatus.INVALID_DATA,
            f"国家占比合计为 {reported_share:.2f}%，超过 100%。",
        )

    is_complete = abs(reported_share - 100.0) <= 0.01 and not reported_top_n_only
    if add_undisclosed_remainder and reported_share < 99.99:
        rows.append(CountryShare("OTHER", "未披露的其他国家", round(100.0 - reported_share, 2)))

    return CountryDistribution(
        metric=metric,
        source=source,
        status=MetricStatus.AVAILABLE,
        rows=rows,
        reported_share_percent=round(reported_share, 2),
        is_complete=is_complete,
    )


def distribution_from_contract_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    metric: str,
    source: str,
    country_names: Mapping[str, str],
    country_key: str = "country_code",
    percentage_key: str = "percentage",
    schema_version: str,
) -> CountryDistribution:
    """Parse a declared row schema; unknown response shapes must fail closed."""

    values: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, Mapping) or country_key not in row or percentage_key not in row:
            return unavailable_distribution(
                metric,
                source,
                MetricStatus.SCHEMA_CHANGED,
                f"响应不符合已验证的 {schema_version} 国家分布契约。",
            )
        code = str(row[country_key]).strip().lower()
        if code in values:
            return unavailable_distribution(metric, source, MetricStatus.INVALID_DATA, f"国家代码 {code.upper()} 重复。")
        values[code] = row[percentage_key]

    result = distribution_from_percent_mapping(
        values,
        metric=metric,
        source=source,
        country_names=country_names,
        reported_top_n_only=True,
    )
    result.schema_version = schema_version
    return result


def parse_gamalytic_active_users_regions(payload: Any, country_names: Mapping[str, str]) -> CountryDistribution:
    """Accept only the documented, fixture-verified active-user rows contract.

    A source change intentionally becomes ``schema_changed`` instead of guessing a
    country/value pair somewhere inside an arbitrary JSON response.
    """

    source = "Gamalytic active-users-regions"
    if not isinstance(payload, Mapping):
        return unavailable_distribution("active_users", source, MetricStatus.SCHEMA_CHANGED, "响应不是对象，无法验证国家分布结构。")
    rows = payload.get("countries")
    if not isinstance(rows, list):
        return unavailable_distribution(
            "active_users",
            source,
            MetricStatus.SCHEMA_CHANGED,
            "接口响应未匹配已验证的 countries[].country_code + percentage 契约。",
        )
    return distribution_from_contract_rows(
        rows,
        metric="active_users",
        source=source,
        country_names=country_names,
        schema_version="gamalytic-active-users-regions/v1",
    )


def unverified_wishlist_insights_distribution() -> CountryDistribution:
    return unavailable_distribution(
        "wishlists",
        "Gamalytic wishlist-insights",
        MetricStatus.SCHEMA_CHANGED,
        "wishlist-insights 尚无已验证的国家字段 fixture；为避免把计数、排名或其他字段误显示为占比，已停止解析。",
    )
