"""The interactive classification prompt must not mislead the person answering it.

The prompt is where the taxpayer decides which § 20 / § 23 treatment an instrument gets, so
a label that misdescribes its option changes the declaration as surely as a routing bug —
issue #52, where "Sonstiges (Standard Anlage KAP)" read as a catch-all for ordinary Anlage
KAP income and mapped to `AssetCategory.STOCK`.

Three invariants are held here. All are about failure modes that leave the suite green and
the output plausible.

1. **No option that routes to `STOCK` may hide it.** Routing to `STOCK` applies the
   Aktienverlusttopf — § 20 Abs. 6 Satz 4, still in force after the JStG-2024 repeal of the
   Termingeschäft cap ([GT-ESTG20-033]) — so a loss on a non-share instrument sent here is
   offsettable only against share gains. The direction is against the taxpayer and nothing
   in the output says so.

2. **No option is a catch-all.** Exactly one option may route to `STOCK`, and it is the one
   that names a share. A second option with the same effect and a residual-sounding label is
   how #52 happened, and renaming such an option does not stop it being the easy answer for
   someone who cannot find theirs.

3. **The Enter key only ever confirms, never decides.** Where the preliminary pass produced
   no classification, there is no default and Enter re-prompts. The old code defaulted an
   `UNKNOWN` asset to the `STOCK` catch-all — ring-fencing for free — and an investment fund
   whose type matched no option to index 0, Aktienfonds with its Teilfreistellung.
"""

from decimal import Decimal

import pytest

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import Asset, InvestmentFund
from src.domain.enums import AssetCategory, InvestmentFundType


@pytest.fixture
def classifier(tmp_path):
    return AssetClassifier(cache_file_path=str(tmp_path / "cache" / "user_classifications.json"))


def test_every_option_label_is_distinct(classifier):
    labels = [label for label, _, _ in classifier._dialog_options]
    assert len(labels) == len(set(labels)), "two options are indistinguishable to the reader"


def test_no_option_routing_to_stock_hides_that_it_does(classifier):
    """Issue #52. An option that maps to `STOCK` must say so on its face. A label that reads
    as "other" or "miscellaneous" while applying the Aktienverlusttopf is the defect."""
    for label, category, _ in classifier._dialog_options:
        if category is not AssetCategory.STOCK:
            continue
        assert "Aktie" in label, (
            f"option {label!r} routes to STOCK and applies the Aktienverlusttopf "
            f"([GT-ESTG20-033]) without the label saying so"
        )


def test_exactly_one_option_routes_to_stock(classifier):
    """Issue #52's residue. The catch-all was renamed to "wie eine Aktie" before it was
    removed, which satisfied the test above while leaving two doors to the same treatment —
    one of them the one an unsure reader takes. A single share option is the invariant; a
    second `STOCK` entry is a catch-all whatever it is called."""
    stock_options = [label for label, cat, _ in classifier._dialog_options if cat is AssetCategory.STOCK]
    assert len(stock_options) == 1, (
        f"{len(stock_options)} options route to STOCK and apply the Aktienverlusttopf: "
        f"{stock_options!r}. One of them is a catch-all."
    )


def _prompting_input(answers):
    """Fake `input()` that records the prompts it was shown and replays `answers` in order."""
    prompts, remaining = [], iter(answers)
    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(remaining)
    return fake_input, prompts


def test_pressing_enter_on_an_unknown_asset_decides_nothing(classifier, monkeypatch):
    """Issue #52, ask 2. An asset the preliminary pass could not classify has no default:
    Enter re-prompts rather than buying the Aktienverlusttopf for free.

    Driven through the real prompt. The first two answers are Enter; if either selected an
    option, the third answer would be read as the notes and the classification would be
    whatever Enter chose. It is the third answer that must decide.
    """
    asset = Asset(
        asset_category=AssetCategory.UNKNOWN,
        description="XAGUSD Spot Silver",
        currency="EUR",
        ibkr_symbol="XAGUSD",
        ibkr_conid="CON_XAGUSD",
        ibkr_asset_class_raw="CMDTY",
    )
    chosen = next(
        i for i, (_, cat, _) in enumerate(classifier._dialog_options)
        if cat is AssetCategory.SONSTIGE_KAPITALFORDERUNG
    )

    fake_input, prompts = _prompting_input(["", "", str(chosen + 1), ""])
    monkeypatch.setattr("builtins.input", fake_input)

    category, fund_type, _notes, _needs_replacement = classifier.ensure_final_classification(
        asset, interactive_mode=True
    )

    assert category is AssetCategory.SONSTIGE_KAPITALFORDERUNG, (
        f"an Enter press decided the classification: got {category.name} without the user "
        f"naming an option"
    )
    assert fund_type is InvestmentFundType.NONE
    assert not any("Default" in p for p in prompts), (
        f"the prompt offered a default for an unclassifiable asset: {prompts!r}"
    )


def test_a_fund_whose_type_matches_no_option_gets_no_default(classifier, monkeypatch):
    """The same defect one category over, and the reason the default rule is "exact match or
    nothing". `InvestmentFundType.NONE` is representable and no dialog option carries it, so
    the old code left the default at its initial index 0 — Aktienfonds, and a
    Teilfreistellung the fund may not be entitled to."""
    asset = InvestmentFund(
        description="Some Fund With No Type Yet",
        currency="EUR",
        ibkr_symbol="NOTYPE",
        ibkr_conid="CON_NOTYPE",
        ibkr_asset_class_raw="FUND",
        fund_type=InvestmentFundType.NONE,
    )
    chosen = next(
        i for i, (_, cat, ft) in enumerate(classifier._dialog_options)
        if cat is AssetCategory.INVESTMENT_FUND and ft is InvestmentFundType.MISCHFONDS
    )

    fake_input, prompts = _prompting_input(["", str(chosen + 1), ""])
    monkeypatch.setattr("builtins.input", fake_input)

    _category, fund_type, _notes, _needs = classifier.ensure_final_classification(
        asset, interactive_mode=True
    )

    assert fund_type is InvestmentFundType.MISCHFONDS, (
        f"an Enter press decided the fund type: got {fund_type.name}"
    )
    assert not any("Default" in p for p in prompts), (
        f"the prompt offered a default for a fund with no recognised type: {prompts!r}"
    )


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
