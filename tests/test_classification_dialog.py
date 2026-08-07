"""The interactive classification prompt must not mislead the person answering it.

The prompt is where the taxpayer decides which § 20 / § 23 treatment an instrument gets, so
a label that misdescribes its option changes the declaration as surely as a routing bug —
issue #52, where "Sonstiges (Standard Anlage KAP)" read as a catch-all for ordinary Anlage
KAP income and mapped to `AssetCategory.STOCK`.

Two invariants are held here. Both are about failure modes that leave the suite green and
the output plausible.

1. **No option that routes to `STOCK` may hide it.** Routing to `STOCK` applies the
   Aktienverlusttopf — § 20 Abs. 6 Satz 4, still in force after the JStG-2024 repeal of the
   Termingeschäft cap ([GT-ESTG20-033]) — so a loss on a non-share instrument sent here is
   offsettable only against share gains. The direction is against the taxpayer and nothing
   in the output says so.

2. **The Enter-key default still resolves.** The default for an UNKNOWN asset used to be
   found by matching the literal label text `"Sonstiges (Standard Anlage KAP)"`. Rewording
   the label breaks that match silently, and the default falls through to index 0 —
   Aktienfonds, a KAP-INV fund with a 30 % Teilfreistellung. Pressing Enter would have
   declared an unclassifiable instrument as an equity fund. The lookup is now by constant;
   this test is what keeps it honest.
"""

from decimal import Decimal

import pytest

from src.classification.asset_classifier import AssetClassifier, FALLBACK_OPTION_LABEL
from src.domain.assets import Asset
from src.domain.enums import AssetCategory, InvestmentFundType


@pytest.fixture
def classifier(tmp_path):
    return AssetClassifier(cache_file_path=str(tmp_path / "cache" / "user_classifications.json"))


def test_every_option_label_is_distinct(classifier):
    labels = [label for label, _, _ in classifier._dialog_options]
    assert len(labels) == len(set(labels)), "two options are indistinguishable to the reader"


def test_no_option_routing_to_stock_hides_that_it_does(classifier):
    """Issue #52. Two options map to `STOCK` — "Aktie" and the fallback — and both must say
    so on their face. A label that reads as "other" or "miscellaneous" while applying the
    Aktienverlusttopf is the defect, not the duplication."""
    for label, category, _ in classifier._dialog_options:
        if category is not AssetCategory.STOCK:
            continue
        assert "Aktie" in label, (
            f"option {label!r} routes to STOCK and applies the Aktienverlusttopf "
            f"([GT-ESTG20-033]) without the label saying so"
        )


def test_the_fallback_option_exists_exactly_once_and_is_the_stock_route(classifier):
    matches = [
        (label, cat, ft) for label, cat, ft in classifier._dialog_options
        if label == FALLBACK_OPTION_LABEL
    ]
    assert len(matches) == 1, (
        "FALLBACK_OPTION_LABEL no longer matches exactly one dialog option, so the "
        "Enter-key default lookup silently falls through to option 1"
    )
    _, category, fund_type = matches[0]
    assert category is AssetCategory.STOCK
    assert fund_type is InvestmentFundType.NONE


def test_pressing_enter_on_an_unknown_asset_selects_the_fallback_not_a_fund(
    classifier, monkeypatch
):
    """Drives the real prompt. `input()` returns "" for both questions — the choice and the
    notes — which is what pressing Enter twice does.

    This asserts the CURRENT behaviour, and issue #52 argues that behaviour is wrong: a
    default that applies stock ring-fencing should not be what an unsure user gets for free.
    When #52 changes it, this test is the thing that has to be changed with it, deliberately.
    What it rules out in the meantime is the default moving somewhere nobody chose.
    """
    asset = Asset(
        asset_category=AssetCategory.UNKNOWN,
        description="XAGUSD Spot Silver",
        currency="EUR",
        ibkr_symbol="XAGUSD",
        ibkr_conid="CON_XAGUSD",
        ibkr_asset_class_raw="CMDTY",
    )

    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "")

    category, fund_type, _notes, _needs_replacement = classifier.ensure_final_classification(
        asset, interactive_mode=True
    )

    assert category is AssetCategory.STOCK, (
        f"the Enter-key default landed on {category.name}, not the fallback option — the "
        f"label lookup in _determine_classification_interactively_or_heuristically no "
        f"longer finds FALLBACK_OPTION_LABEL"
    )
    assert fund_type is InvestmentFundType.NONE


def test_an_fx_pair_is_never_defaulted_into_a_cash_balance(classifier, monkeypatch):
    """The FX-pair guard, which the relabelling of options 13 and 14 is about. An FX trading
    pair is not a currency holding: its gain or loss is realised on the two currency
    ledgers, and the instrument itself carries none."""
    asset = Asset(
        asset_category=AssetCategory.UNKNOWN,
        description="EUR.USD",
        currency="USD",
        ibkr_symbol="EUR.USD",
        ibkr_conid="CON_EURUSD",
        ibkr_asset_class_raw="CASH",
    )

    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: "")

    category, _fund_type, _notes, _needs = classifier.ensure_final_classification(
        asset, interactive_mode=True
    )

    assert category is not AssetCategory.CASH_BALANCE
    assert category is AssetCategory.UNKNOWN
