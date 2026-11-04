from types import SimpleNamespace as NS
import unittest

from bot.broker_account_snapshot import BrokerSnapshotError, TInvestAccountReader


def quotation(units, nano=0):
    return NS(units=units, nano=nano)


def client_fixture(*, accounts=None, portfolio=None, orders=None):
    return NS(
        users=NS(get_accounts=lambda: NS(accounts=accounts if accounts is not None else [NS(id="acct")])),
        operations=NS(get_portfolio=lambda **kwargs: NS(portfolio=portfolio)),
        orders=NS(get_orders=lambda **kwargs: NS(orders=orders if orders is not None else [])),
    )


def valid_portfolio():
    return NS(
        money=[NS(currency="rub", available=quotation(1000), blocked=quotation(100))],
        securities=[
            NS(instrument_uid="uid-1", ticker="AAA", quantity=quotation(2),
               current_price=quotation(50), currency="rub")
        ],
    )


class BrokerAccountSnapshotTests(unittest.TestCase):
    def test_reads_snapshot_without_mutating_account(self):
        reader = TInvestAccountReader(client_fixture(portfolio=valid_portfolio()))
        snapshot = reader.read_snapshot("acct")

        self.assertEqual(snapshot.account_id, "acct")
        self.assertEqual(snapshot.currency, "RUB")
        self.assertEqual(snapshot.available_cash, 1000)
        self.assertEqual(snapshot.blocked_cash, 100)
        self.assertEqual(snapshot.total_position_value, 100)
        self.assertEqual(snapshot.total_equity, 1200)
        self.assertEqual(snapshot.positions[0].ticker, "AAA")
        self.assertEqual(snapshot.open_orders_count, 0)

    def test_refuses_unknown_account(self):
        reader = TInvestAccountReader(client_fixture(accounts=[], portfolio=valid_portfolio()))
        with self.assertRaisesRegex(BrokerSnapshotError, "exactly one accessible account"):
            reader.read_snapshot("acct")

    def test_refuses_ambiguous_cash_currency(self):
        portfolio = valid_portfolio()
        portfolio.money.append(NS(currency="usd", available=quotation(2), blocked=quotation(0)))
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "exactly one cash currency"):
            reader.read_snapshot("acct")

    def test_refuses_mixed_currency_position(self):
        portfolio = valid_portfolio()
        portfolio.securities[0].currency = "usd"
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "multi-currency reconciliation"):
            reader.read_snapshot("acct")

    def test_counts_unfinished_orders_as_open(self):
        orders = [
            NS(execution_report_status="FILL"),
            NS(execution_report_status="EXECUTION_REPORT_STATUS_CANCELLED"),
            NS(execution_report_status="NEW"),
            NS(execution_report_status="PARTIALLYFILL"),
        ]
        reader = TInvestAccountReader(client_fixture(portfolio=valid_portfolio(), orders=orders))
        self.assertEqual(reader.read_snapshot("acct").open_orders_count, 2)

    def test_rejects_invalid_quote_and_duplicate_position(self):
        portfolio = valid_portfolio()
        portfolio.securities[0].current_price = quotation(-1)
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "non-negative"):
            reader.read_snapshot("acct")

        portfolio = valid_portfolio()
        portfolio.securities.append(portfolio.securities[0])
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "duplicate broker position"):
            reader.read_snapshot("acct")


    def test_rejects_boolean_money_and_quotation_components(self):
        portfolio = valid_portfolio()
        portfolio.money[0].available = True
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "not boolean"):
            reader.read_snapshot("acct")

        portfolio = valid_portfolio()
        portfolio.securities[0].quantity = quotation(True)
        reader = TInvestAccountReader(client_fixture(portfolio=portfolio))
        with self.assertRaisesRegex(BrokerSnapshotError, "not boolean"):
            reader.read_snapshot("acct")

if __name__ == "__main__":
    unittest.main()
