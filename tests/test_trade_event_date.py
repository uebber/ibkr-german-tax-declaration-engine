"""The day a trade is booked on: the contract, never the settlement.

legal_basis: [GT-ESTG20-040] BMF 14.05.2025 Rn. 317 — *"Der Begriff des Erwerbs
beinhaltet den Tatbestand des 'rechtswirksam abgeschlossenen obligatorischen
Vertrags oder gleichstehenden Rechtsaktes'."*; and [GT-ESTG20-039] Rn. 85, which
puts the disposal side on the same footing: the obligatorische Rechtsgeschäft is
*"der maßgebliche Zeitpunkt für die Währungsumrechnung und die Berechnung des
steuerlichen Veräußerungs- bzw. Einlösungsgewinns oder -verlustes"*. Both in
reference/bmf-guidance/abgeltungsteuer-einzelfragen.md.

Why this is worth its own file. The date a `TradeEvent` carries is not one fact
but four: it picks the ECB rate, it decides the assessment year when contract and
settlement straddle a year end, it starts the § 23 Jahresfrist, and it fixes the
month § 18 Abs. 2 InvStG counts twelfths from. The engine gets it right today,
but by fallback rather than by rule — `_get_prioritized_date` prefers the
settlement date, and only the absence of `SettleDateTarget` from IBKR's Trades
export makes the trade date win. These tests take the fallback away and assert
the rule directly, so that a later change to the export, the column list, or the
helper's ordering fails here instead of in a filed return.

The distinction that keeps the cash-flow paths correct is asserted too: a
dividend or interest credit is taxed on its Zufluss, so its settlement date is
the right one and this rule must not be generalised to it.
"""
from src.parsers.domain_event_factory import DomainEventFactory


def _contract_date(**kwargs) -> str | None:
    return DomainEventFactory._trade_contract_date(**kwargs)


def _zufluss_date(**kwargs) -> str | None:
    return DomainEventFactory._get_prioritized_date(**kwargs)


class TestATradeIsBookedOnTheContractDate:
    def test_the_contract_date_is_what_resolves(self):
        """
        The case that decides a figure: a purchase struck on 31 January and
        settled on 2 February. Under § 18 Abs. 2 InvStG the contract date keeps
        eleven twelfths of the Vorabpauschale and the settlement date keeps ten,
        so the two differ by a twelfth of a declared amount.
        """
        resolved = _contract_date(
            trade_or_event_datetime_str="2024-01-31 15:42:00",
            trade_date_str="2024-01-31",
        )
        assert resolved == "2024-01-31", (
            "Rn. 317 puts Erwerb at the obligatorischer Vertrag, so this must "
            f"be 2024-01-31, got {resolved}")

    def test_the_rule_takes_no_settlement_or_report_date_at_all(self):
        """
        The fix is structural, not a reordering: the trade rule has no parameter
        a settlement or report date could be passed to. Asserted so that
        reintroducing one is a test failure rather than a silent widening.
        """
        import inspect

        params = set(inspect.signature(
            DomainEventFactory._trade_contract_date).parameters)
        assert params == {"trade_or_event_datetime_str", "trade_date_str"}, (
            f"the trade date rule grew a new source of truth: {sorted(params)}")

    def test_an_absent_trade_date_resolves_to_nothing_rather_than_a_neighbour(self):
        """
        No silent default. A trade whose contract date is missing must stop the
        run, not borrow the report date — the caller turns None into a data error.
        """
        assert _contract_date(trade_or_event_datetime_str=None,
                              trade_date_str=None) is None

    def test_a_bare_date_in_the_datetime_slot_still_resolves(self):
        """`TradeDate` with no `TradeTime` composes a value that is not a datetime."""
        assert _contract_date(trade_or_event_datetime_str="2024-01-31",
                              trade_date_str="2024-01-31") == "2024-01-31"


class TestTheWiringUsesThatRule:
    """
    The ends of the channel, not the middle. A rule no caller reaches is worth
    nothing, and the trades path is the only caller.
    """

    def test_a_raw_trade_carrying_a_settlement_date_is_still_booked_on_the_contract(self):
        """
        Goes through `create_events_from_trades`, not through the rule, so that
        putting the settlement date back at the call site fails here. Probed:
        restoring `_get_prioritized_date(settle_date_str=rt.settle_date_target, …)`
        turns this red and leaves every other test in the file green.
        """
        from src.classification.asset_classifier import AssetClassifier
        from src.identification.asset_resolver import AssetResolver
        from src.parsers.raw_models import RawTradeRecord

        rt = RawTradeRecord.parse_obj({
            "CurrencyPrimary": "EUR", "AssetClass": "STK", "Symbol": "DATE",
            "Description": "Date Test Stock", "ISIN": "DE0000000000",
            "Conid": "CON_DATE", "TradeDate": "2024-12-30", "TradeTime": "09:05:00",
            "SettleDateTarget": "2025-01-02", "ReportDate": "2025-01-02",
            "Quantity": "10", "TradePrice": "40.00", "Buy/Sell": "BUY",
            "TransactionID": "TX_DATE_1", "Open/CloseIndicator": "O",
        })
        assert rt.settle_date_target == "2025-01-02", (
            "fixture no longer exercises the case: the raw record dropped the "
            "settlement date, so this test would pass either way")

        factory = DomainEventFactory(
            asset_resolver=AssetResolver(
                asset_classifier=AssetClassifier(cache_file_path="dummy_cache.json")))
        created, _options, _stock = factory.create_events_from_trades([rt])

        assert len(created) == 1, f"expected one trade event, got {created}"
        assert created[0].event_date == "2024-12-30", (
            "a disposal moved into the following assessment year on its "
            f"settlement date; expected 2024-12-30, got {created[0].event_date}")


class TestACashFlowIsStillBookedOnItsZufluss:
    """
    Rn. 85 and Rn. 317 are about Veräußerung/Einlösung and Erwerb. A dividend,
    an interest credit or a withholding entry is taxed when it flows, so the
    settlement date governs and must keep winning. Asserted so that a future
    reordering of the helper cannot fix trades by breaking these.
    """

    def test_settlement_wins_for_a_cash_transaction(self):
        resolved = _zufluss_date(
            settle_date_str="2024-02-02",
            trade_or_event_datetime_str="2024-01-31",
            report_date_str="2024-02-05",
        )
        assert resolved == "2024-02-02"

    def test_pay_date_wins_for_a_corporate_action(self):
        resolved = _zufluss_date(
            pay_date_str="2024-03-15",
            report_date_str="2024-03-20",
            trade_or_event_datetime_str="2024-03-01",
        )
        assert resolved == "2024-03-15"
