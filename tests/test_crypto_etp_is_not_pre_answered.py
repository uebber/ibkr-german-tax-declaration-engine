"""A crypto ETP is a question the engine must put, not one it may answer.

legal_basis: GT-ESTG23-011, as it stands after the issue #66 audit of 2026-08-08.

BMF 14.05.2025 Rz. 57 is the only Tier 2 authority under that claim, and both limbs of its
test are worded to a Rohstoff: the Emittent must invest *"nahezu vollstaendig in Gold oder
einen anderen Rohstoff"*, and the exclusive claim must run to *"Auslieferung des hinterlegten
Rohstoffs"* or to *"Auszahlung des Erloeses aus der Veraeusserung des Rohstoffs"*. A crypto
asset is not a Rohstoff. The Randziffer therefore reaches a crypto ETP in **neither**
direction, and the claim no longer lists one.

What the engine did before this change, and what each test below holds shut:

  - `preliminary_classify` matched a handful of descriptions and symbols and returned
    `PRIVATE_SALE_ASSET` outright — § 23, Anlage SO.
  - that preliminary category became the dialog's *default*, so Enter accepted § 23.
  - the § 23 option label named *Krypto-ETP* in its own text, telling the taxpayer the
    answer while asking them the question.
  - a `--no-interactive` run on an uncached instrument kept the heuristic silently, under
    the note "Auto-classified based on heuristics".

Each of those is the engine deciding, and none of them had a source. The remedy is not a
different answer — it is no answer: the instrument reaches the taxpayer with nothing
pre-selected, and a non-interactive run raises instead of inventing. Which side it then
lands on turns on the Emissionsbedingungen, which no input to this engine carries.

**Scope boundary, asserted here rather than assumed.** Gold and commodity ETCs keep their
preliminary § 23 answer. Rz. 57 is authority for the Rohstoff case and this change does not
touch it; `test_a_gold_etc_still_gets_its_section_23_answer` fails if it does, which is what
stops a crypto fix from quietly becoming a commodity one.
"""

import pytest

from src.classification.asset_classifier import AssetClassifier
from src.domain.assets import Asset
from src.domain.enums import AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError


# Every description and symbol the removed heuristic matched on. Parametrising over the
# whole set rather than one example is deliberate: the branch had four description patterns
# and three symbols, and deleting some of them would leave the rest deciding.
CRYPTO_INSTRUMENTS = [
    ("STK", "", "BTCETC PHYSICAL BITCOIN", "BTCE"),
    ("STK", "COMMON", "SOME ISSUER BITCOIN ETP", "XBTE"),
    ("STK", "", "SOME ISSUER CRYPTO ETP", "CRYP"),
    ("STK", "", "SOME ISSUER ETHEREUM ETP", "ZETH"),
    ("STK", "", "SOME ISSUER ETC ON BITCOIN", "BITC"),
    ("STK", "", "SOME ISSUER CRYPTO ETC", "ETCZERO"),
]


@pytest.fixture
def classifier(tmp_path):
    return AssetClassifier(cache_file_path=str(tmp_path / "cache" / "user_classifications.json"))


def _asset(classifier, asset_class, sub_category, description, symbol):
    """An asset carrying the category the preliminary pass would really have given it.

    Hand-setting `asset_category=UNKNOWN` here would make the default and raise tests below
    pass against the unfixed code — they assert on behaviour that keys off exactly that
    field, so supplying the post-fix value is assuming the fix. The resolver runs
    `preliminary_classify` and stores its answer; so does this.
    """
    category, fund_type = classifier.preliminary_classify(
        asset_class, sub_category, description, symbol
    )
    asset = Asset(
        asset_category=category,
        description=description,
        currency="EUR",
        ibkr_symbol=symbol,
        ibkr_conid=f"CON_{symbol}",
        ibkr_asset_class_raw=asset_class,
        ibkr_sub_category_raw=sub_category,
    )
    asset.fund_type = fund_type
    return asset


@pytest.mark.parametrize("asset_class,sub_category,description,symbol", CRYPTO_INSTRUMENTS)
def test_the_preliminary_pass_answers_nothing(
    classifier, asset_class, sub_category, description, symbol
):
    """The heuristic returned `PRIVATE_SALE_ASSET`; nothing in the store supports it.

    `UNKNOWN` specifically, not merely "not PRIVATE_SALE_ASSET": `UNKNOWN` is the only
    category the dialog refuses to offer as a default, so it is what makes the next two
    tests true. Falling through to `STOCK` would satisfy a weaker assertion and hand the
    taxpayer an Enter key that buys the Aktienverlusttopf.
    """
    category, fund_type = classifier.preliminary_classify(
        asset_class, sub_category, description, symbol
    )
    assert category is AssetCategory.UNKNOWN, (
        f"{description!r} was pre-classified {category.name} — the engine answered a "
        f"question Rz. 57 does not reach and no other source in reference/ addresses"
    )
    assert fund_type is InvestmentFundType.NONE


@pytest.mark.parametrize("asset_class,sub_category,description,symbol", CRYPTO_INSTRUMENTS)
def test_the_taxpayer_is_still_asked(
    classifier, asset_class, sub_category, description, symbol
):
    """Answering nothing is only safe if the question still gets put.

    `_is_potentially_special` is what routes an instrument into the dialog. Deleting the
    crypto patterns from it as well would send a Bitcoin ETP straight through as whatever
    its asset class implies — for `STK`, an ordinary share.
    """
    asset = _asset(classifier, asset_class, sub_category, description, symbol)
    assert classifier._is_potentially_special(asset) is True, (
        f"{description!r} would not be shown to the taxpayer at all"
    )


def test_no_dialog_option_names_a_crypto_product(classifier):
    """The § 23 label read "... oder Krypto-ETP", which is the same unsourced answer
    printed as guidance. Options state the criterion the taxpayer matches against a
    factsheet; naming the instrument decides it for them."""
    offenders = [
        label for label, _, _ in classifier._dialog_options
        if "krypto" in label.lower() or "crypto" in label.lower()
    ]
    assert offenders == [], (
        f"a dialog option tells the taxpayer where a crypto product goes: {offenders!r}"
    )


def test_the_dialog_offers_no_default_and_enter_decides_nothing(classifier, monkeypatch):
    """Driven through the real prompt, because the default is computed inside it.

    The first two answers are Enter. If either were accepted, the third answer would be
    read as the free-text note and the classification would be whatever the default was.
    """
    asset = _asset(classifier, "STK", "", "BTCETC PHYSICAL BITCOIN", "BTCE")

    prompts = []
    answers = iter(["", "", "7", ""])

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    category, _fund_type, _notes, _needs = classifier.ensure_final_classification(
        asset, interactive_mode=True
    )

    assert not any("Default" in p for p in prompts), (
        f"the prompt pre-selected an answer for a crypto ETP: {prompts!r}"
    )
    # Option 7 is whatever the taxpayer picked; the point is that a keystroke chose it.
    assert category is classifier._dialog_options[6][1]


def test_a_non_interactive_run_raises_rather_than_inventing(classifier):
    """CLAUDE.md: no silent default — anything unresolvable raises.

    The old path kept the heuristic and stamped "Auto-classified based on heuristics",
    which produces a § 23 figure on Anlage SO that no source stands behind and that reads
    on the form exactly like a measured one.
    """
    asset = _asset(classifier, "STK", "", "BTCETC PHYSICAL BITCOIN", "BTCE")
    with pytest.raises(DataIntegrityError) as excinfo:
        classifier.ensure_final_classification(asset, interactive_mode=False)
    assert "BTCE" in str(excinfo.value), (
        "the error must name the instrument, so one run identifies every unclassified one"
    )


def test_a_taxpayer_classification_is_still_honoured(classifier):
    """Removing the pre-answer must not remove the answer.

    The seven Bitcoin ETPs classified by hand on 2026-08-07 sit in the cache, which
    `ensure_final_classification` consults before any heuristic. If this broke, a settled
    VZ 2023 classification would start re-prompting — or, non-interactively, raising.
    """
    asset = _asset(classifier, "STK", "", "BTCETC PHYSICAL BITCOIN", "BTCE")
    classifier.classifications_cache[asset.get_classification_key()] = (
        AssetCategory.PRIVATE_SALE_ASSET.name,
        InvestmentFundType.NONE.name,
        "physically backed, exclusive delivery claim (taxpayer, 2026-08-07)",
    )

    category, fund_type, notes, _needs = classifier.ensure_final_classification(
        asset, interactive_mode=False
    )

    assert category is AssetCategory.PRIVATE_SALE_ASSET
    assert fund_type is InvestmentFundType.NONE
    assert "taxpayer" in notes


@pytest.mark.parametrize(
    "description,symbol",
    [
        ("XETRA-GOLD INHABERSCHULDVERSCHREIBUNG", "4GLD"),
        ("SOME ISSUER PHYSICAL GOLD", "XAD5"),
        ("SOME ISSUER GOLD ETC", "GZLD"),
    ],
)
def test_a_gold_etc_still_gets_its_section_23_answer(classifier, description, symbol):
    """The scope boundary of issue #66 item 1, held by a test rather than by intention.

    Rz. 57 is squarely about Gold und andere Rohstoffe, so the commodity heuristic is a
    different question from the crypto one and is not what the audit found unsourced.
    Whether it *should* pre-answer a question that turns on the Emissionsbedingungen is a
    separate matter and not decided here; what this test forbids is deciding it silently
    while fixing crypto.
    """
    category, _fund_type = classifier.preliminary_classify("STK", "", description, symbol)
    assert category is AssetCategory.PRIVATE_SALE_ASSET, (
        f"the commodity branch moved to {category.name} — out of scope for issue #66 "
        f"item 1, which is about the crypto row of [GT-ESTG23-011]"
    )
