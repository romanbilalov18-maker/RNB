import os
import unittest


@unittest.skipUnless(
    os.getenv("RUN_LIVE_TINVEST_TEST") == "1",
    "live T-Invest test is disabled; set RUN_LIVE_TINVEST_TEST=1",
)
class TestLiveBotStart(unittest.TestCase):
    """Real T-Invest startup smoke test. It never sends trading orders."""

    def test_bot_connects_and_reads_stock_market(self):
        from bot.config import Config
        from t_tech.invest import Client

        config = Config.from_env()

        with Client(config.invest_token) as client:
            response = client.instruments.shares()
            shares = list(response.instruments)

            self.assertGreater(len(shares), 0, "T-Invest returned no shares")

            rub_shares = [
                share
                for share in shares
                if str(getattr(share, "currency", "")).upper() in {"RUB", "RUR"}
                and getattr(share, "api_trade_available_flag", True)
            ]

            self.assertGreater(
                len(rub_shares),
                0,
                "T-Invest returned no tradable RUB shares",
            )

            sample = rub_shares[:10]
            instrument_ids = [
                str(
                    getattr(share, "uid", "")
                    or getattr(share, "figi", "")
                )
                for share in sample
            ]
            instrument_ids = [value for value in instrument_ids if value]

            prices = client.market_data.get_last_prices(
                instrument_id=instrument_ids,
            )

            self.assertGreater(
                len(prices.last_prices),
                0,
                "T-Invest returned no current prices",
            )

            print(
                f"Live startup OK: {len(shares)} shares, "
                f"{len(rub_shares)} tradable RUB shares, "
                f"{len(prices.last_prices)} current prices."
            )


if __name__ == "__main__":
    unittest.main()
