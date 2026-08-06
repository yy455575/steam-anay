from __future__ import annotations

import unittest
from unittest.mock import patch

from steam_intel.country_metrics import MetricStatus
from wishlist_tools import (
    extract_country_distribution,
    fetch_gamalytic_active_users_regions,
    fetch_gamalytic_wishlist_country_distribution,
    fetch_purchase_language_distribution,
    fetch_regional_wishlist_interest,
    gamalytic_country_data_frame,
    parse_popular_wishlist_html,
)


class WishlistToolRegressionTests(unittest.TestCase):
    def test_public_country_data_keeps_other_as_undisclosed(self) -> None:
        frame = gamalytic_country_data_frame({"countryData": {"us": 34.7, "gb": 8.6, "cn": 8.3}})

        self.assertEqual(frame["国家代码"].tolist(), ["OTHER", "US", "GB", "CN"])
        other = frame.loc[frame["国家代码"] == "OTHER"].iloc[0]
        self.assertEqual(other["国家/地区"], "未披露的其他国家")
        self.assertEqual(other["玩家占比(%)"], 48.4)

    def test_rate_limit_becomes_a_data_state_instead_of_an_exception(self) -> None:
        with patch("wishlist_tools.fetch_gamalytic_api_json", side_effect=RuntimeError("Gamalytic API 返回 429：请求过于频繁")):
            result = fetch_gamalytic_active_users_regions("2769570", "test-key")

        self.assertEqual(result.status, MetricStatus.RATE_LIMITED)
        self.assertFalse(result.available)

    def test_wishlist_response_is_not_parsed_without_a_verified_schema(self) -> None:
        with patch("wishlist_tools.fetch_gamalytic_api_json", return_value={"countries": [{"country_code": "us", "percentage": 99.0}]}):
            result = fetch_gamalytic_wishlist_country_distribution("2769570", "test-key")

        self.assertEqual(result.status, MetricStatus.SCHEMA_CHANGED)
        self.assertFalse(result.available)

    def test_store_search_html_keeps_identity_fields(self) -> None:
        html = '''
        <a class="search_result_row" data-ds-appid="2769570" href="https://store.steampowered.com/app/2769570/Fable/">
          <span class="title">Fable</span>
          <div class="search_released">2026</div>
          <img src="https://cdn.example/fable.jpg">
        </a>
        '''

        rows = parse_popular_wishlist_html(html)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["AppID"], "2769570")
        self.assertEqual(rows[0]["游戏名称"], "Fable")
        self.assertEqual(rows[0]["商店链接"], "https://store.steampowered.com/app/2769570/")

    def test_legacy_proxies_are_disabled_instead_of_generating_country_shares(self) -> None:
        parsed = extract_country_distribution({"us": 999, "gb": 1}, "占比(%)", "fixture")
        regional_long, regional_wide = fetch_regional_wishlist_interest(["US", "CN"])
        review_long, review_wide = fetch_purchase_language_distribution(None, ["english"])

        self.assertTrue(parsed.empty)
        self.assertTrue(regional_long.empty)
        self.assertTrue(regional_wide.empty)
        self.assertTrue(review_long.empty)
        self.assertTrue(review_wide.empty)


if __name__ == "__main__":
    unittest.main()
