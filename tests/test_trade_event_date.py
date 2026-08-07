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
and by rule since August 2026: `_trade_contract_date` accepts no settlement or
report date, and `RawTradeRecord` no longer carries a settlement field. Before
that it was right only by fallback — the general helper preferred the settlement
date, and only the absence of `SettleDateTarget` from IBKR's Trades export made
the trade date win. These tests assert the rule directly, so that a later change
to the export, the column list, or the helper's ordering fails here instead of in
a filed return.

The distinction that keeps the cash-flow paths correct is asserted too: a
dividend or interest credit is taxed on its Zufluss, so its settlement date is
the right one and this rule must not be generalised to it.

Narrowed in August 2026 (issue #64). Both helpers now take exactly one date,
because exactly one date per record is exported. What each caller supplies is
asserted below, so that a future export gaining `PayDate`, `TradeTime` or
`DateTime` has to arrive through a visible edit rather than through a priority
slot that was sitting there unreachable.
"""
import inspect

from src.parsers.domain_event_factory import DomainEventFactory


def _contract_date(*args) -> str | None:
    return DomainEventFactory._trade_contract_date(*args)


def _zufluss_date(*args) -> str | None:
    return DomainEventFactory._zufluss_date(*args)


class TestATradeIsBookedOnTheContractDate:
    def test_the_contract_date_is_what_resolves(self):
        """
        The case that decides a figure: a purchase struck on 31 January and
        settled on 2 February. Under § 18 Abs. 2 InvStG the contract date keeps
        eleven twelfths of the Vorabpauschale and the settlement date keeps ten,
        so the two differ by a twelfth of a declared amount.
        """
        resolved = _contract_date("2024-01-31")
        assert resolved == "2024-01-31", (
            "Rn. 317 puts Erwerb at the obligatorischer Vertrag, so this must "
            f"be 2024-01-31, got {resolved}")

    def test_the_rule_takes_no_settlement_or_report_date_at_all(self):
        """
        The fix is structural, not a reordering: the trade rule has no parameter
        a settlement or report date could be passed to. Asserted so that
        reintroducing one is a test failure rather than a silent widening.

        Tightened with #64 from "no settlement or report slot" to "one slot,
        and it is the trade date" — the datetime slot that used to sit beside it
        was fed `f"{TradeDate} {TradeTime}"`, and `TradeTime` is not exported, so
        it only ever carried midnight.
        """
        params = set(inspect.signature(
            DomainEventFactory._trade_contract_date).parameters)
        assert params == {"trade_date_str"}, (
            f"the trade date rule grew a new source of truth: {sorted(params)}")

    def test_an_absent_trade_date_resolves_to_nothing_rather_than_a_neighbour(self):
        """
        No silent default. A trade whose contract date is missing must stop the
        run, not borrow the report date — the caller turns None into a data error.
        """
        assert _contract_date(None) is None

    def test_a_trade_date_carrying_a_time_still_resolves(self):
        """
        `TradeDate` is date-only in this export, but the rule must not depend on
        that: a value that does arrive with a time component still resolves to
        its date. This is what the separate datetime parameter used to provide,
        and it survived that parameter's removal — `parse_ibkr_date` splits the
        time off. Probed: reverting the helper's body to `datetime.fromisoformat`
        turns this red and leaves the rest of the file green.
        """
        assert _contract_date("2024-01-31 15:42:00") == "2024-01-31"


class TestTheWiringUsesThatRule:
    """
    The ends of the channel, not the middle. A rule no caller reaches is worth
    nothing, and the trades path is the only caller.
    """

    def test_a_raw_trade_carrying_a_settlement_date_is_still_booked_on_the_contract(self):
        """
        Goes through `create_events_from_trades`, not through the rule, so that
        rewiring the call site fails here.

        Probed, and the negative result is worth recording. Swapping the call site
        to `_zufluss_date(rt.trade_date)` does *not* turn this red, because after
        #64 the two helpers have identical bodies — both are `parse_ibkr_date` on
        their one argument — so with the same input they cannot disagree. The older
        version of this docstring claimed that probe worked; it described the
        pre-#64 helper, which ordered settlement first.

        What does turn it red, each leaving the rest of the file green:
        passing a different column at the call site (`rt.expiry`), and
        re-declaring `report_date` on `RawTradeRecord`. Those are the two ways a
        competing date could come back, and the second is also caught by
        `test_raw_model_fields.py`. The separation of the two helpers is enforced
        by their signatures and by the model having no other date to offer — not
        by their bodies differing.
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

        # Fixture integrity, and the guarantee itself. The row above offers three
        # competing dates; the model must have nowhere to put any of them, so that
        # no call site can reach one. This replaces the older check that
        # `rt.report_date` held the competing value — under #64 the field is gone
        # rather than merely unread, which is the stronger property.
        for absent in ("settle_date_target", "report_date", "trade_time"):
            assert not hasattr(rt, absent), (
                f"RawTradeRecord grew a competing date field again ({absent!r}). "
                "These were removed in August 2026 because a declared-but-unread "
                "date field is how the settlement date became the engine's default; "
                "the model must have nowhere to put one.")
        assert rt.trade_date == "2024-12-30"

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
    flow date governs and must keep winning. Asserted so that a future change
    to the helper cannot fix trades by breaking these.
    """

    def test_the_zufluss_rule_takes_exactly_one_date(self):
        """
        The same structural guarantee as the trade rule, and the one #64 exists
        to install. This helper used to take five dates in a priority order of
        which four were always None for any given caller, because the columns
        behind them are not requested in any Flex Query. A chain that looks
        considered but has one reachable entry is what put the settlement date
        in front of the trade date; had `PayDate` later appeared in the
        corporate-actions export, every corporate action would have moved off
        its report date with nobody deciding it.
        """
        params = set(inspect.signature(
            DomainEventFactory._zufluss_date).parameters)
        assert params == {"zufluss_date_str"}, (
            f"the Zufluss rule grew a competing date again: {sorted(params)}")

    def test_settlement_is_what_a_cash_transaction_is_booked_on(self):
        """`SettleDate` is the Zufluss and the only date the export carries."""
        assert _zufluss_date("2024-02-02") == "2024-02-02"

    def test_a_cash_transaction_reaches_that_rule_with_its_settle_date(self):
        """
        The end of the channel: asserting the helper alone would not catch the
        call site being rewired to a different column. Probed: passing
        `rct.type` instead of `rct.settle_date` turns this red, and leaves every
        other test in the file green.
        """
        import src.parsers.domain_event_factory as def_mod

        seen = []
        original = DomainEventFactory._zufluss_date

        def spy(value):
            seen.append(value)
            return original(value)

        from src.classification.asset_classifier import AssetClassifier
        from src.identification.asset_resolver import AssetResolver
        from src.parsers.raw_models import RawCashTransactionRecord

        rct = RawCashTransactionRecord.parse_obj({
            "CurrencyPrimary": "EUR", "AssetClass": "STK", "Symbol": "DIV",
            "Description": "ACME INC CASH DIVIDEND", "ISIN": "DE0000000001",
            "Conid": "CON_DIV", "SettleDate": "2024-02-02", "Amount": "100.00",
            "Type": "Dividends", "TransactionID": "TX_DIV_1",
        })

        factory = DomainEventFactory(
            asset_resolver=AssetResolver(
                asset_classifier=AssetClassifier(cache_file_path="dummy_cache.json")))
        monkey = def_mod.DomainEventFactory._zufluss_date
        def_mod.DomainEventFactory._zufluss_date = staticmethod(spy)
        try:
            events = factory.create_events_from_cash_transactions([rct])
        finally:
            def_mod.DomainEventFactory._zufluss_date = monkey

        assert seen == ["2024-02-02"], (
            f"the cash-transaction path stopped booking on SettleDate: {seen}")
        assert len(events) == 1 and events[0].event_date == "2024-02-02"

    def test_the_report_date_is_what_a_corporate_action_is_booked_on(self):
        """
        Was `test_pay_date_wins_for_a_corporate_action`, which asserted a
        priority that could never fire: `PayDate` is not exported, so the report
        date was already the only reachable entry. The intent — a corporate
        action is booked on the day its amount flows, and the engine says which
        column that is — is what survives.
        """
        assert _zufluss_date("2024-03-20") == "2024-03-20"

    def test_an_absent_zufluss_date_resolves_to_nothing(self):
        """No silent default here either; the caller turns None into a data error."""
        assert _zufluss_date(None) is None
