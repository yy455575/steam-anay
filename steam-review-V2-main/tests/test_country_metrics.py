from __future__ import annotations

import unittest

from steam_intel.country_metrics import (
    MetricStatus,
    distribution_from_percent_mapping,
    parse_gamalytic_active_users_regions,
    unverified_wishlist_insights_distribution,
)


COUNTRIES = {"us": "美国", "gb": "英国", "cn": "中国"}


class CountryMetricContractTests(unittest.TestCase):
    def test_public_top_three_keeps_an_undisclosed_remainder(self) -> None:
        result = distribution_from_percent_mapping(
            {"us": 34.7, "gb": 8.6, "cn": 8.3},
            metric="players",
            source="fixture",
            country_names=COUNTRIES,
            reported_top_n_only=True,
            add_undisclosed_remainder=True,
        )

        self.assertTrue(result.available)
        self.assertFalse(result.is_complete)
        self.assertEqual(result.reported_share_percent, 51.6)
        self.assertEqual([(row.country_code, row.share_percent) for row in result.rows], [("US", 34.7), ("GB", 8.6), ("CN", 8.3), ("OTHER", 48.4)])

    def test_counts_and_fractions_are_not_rescaled_into_percentages(self) -> None:
        result = distribution_from_percent_mapping(
            {"us": 120},
            metric="players",
            source="fixture",
            country_names=COUNTRIES,
        )

        self.assertEqual(result.status, MetricStatus.INVALID_DATA)
        self.assertIn("0 到 100", result.message)

    def test_active_user_parser_accepts_only_the_declared_rows_contract(self) -> None:
        result = parse_gamalytic_active_users_regions(
            {
                "countries": [
                    {"country_code": "us", "percentage": 34.7},
                    {"country_code": "gb", "percentage": 8.6},
                ]
            },
            COUNTRIES,
        )

        self.assertTrue(result.available)
        self.assertEqual(result.schema_version, "gamalytic-active-users-regions/v1")
        self.assertEqual(result.reported_share_percent, 43.3)

    def test_unknown_nested_json_does_not_be_guessed_as_country_distribution(self) -> None:
        result = parse_gamalytic_active_users_regions(
            {"data": {"us": {"wishlists": 999999}, "gb": {"wishlists": 500000}}},
            COUNTRIES,
        )

        self.assertEqual(result.status, MetricStatus.SCHEMA_CHANGED)
        self.assertFalse(result.available)

    def test_unverified_wishlist_payload_is_fail_closed(self) -> None:
        result = unverified_wishlist_insights_distribution()

        self.assertEqual(result.status, MetricStatus.SCHEMA_CHANGED)
        self.assertFalse(result.available)
        self.assertIn("fixture", result.message)


if __name__ == "__main__":
    unittest.main()
