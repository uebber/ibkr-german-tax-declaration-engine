"""A raw-model field is a claim that the column arrives. This test checks the claim.

Issue #64. `SettleDateTarget` was declared on `RawTradeRecord` and populated by nothing —
it is not in the Flex Query and not in `TRADES_COLUMNS`. That did not stay harmless:
`_get_prioritized_date` listed it *first*, so the legally decisive date of every trade was
the settlement date by rule, and the trade date only by the accident of the column being
absent. Adding the column to the query would have moved every lot's date silently.

The audit that followed found 72 more such fields across four models. Among them: two
thirds of the corporate-action date chain (`PayDate`, `ExDate`), `TradeTime`,
`TradeMoney`/`Proceeds` on trades, `Code` on cash transactions, and the
`SecurityID`/`SecurityIDType` pair whose absence made
`raw_isin=isin or security_id if security_id_type == "ISIN" else isin` reduce to `isin` at
six call sites.

Nothing failed on any of them, and nothing would have. That is what this file changes: the
declared-but-unrequested state is now a test failure rather than a latent one.

Calibration — each assertion below was checked against a deliberately broken tree, and the
mutation it catches is named in its docstring.
"""
import csv
import glob

import pytest

from src.parsers import column_validator as cv
from src.parsers import raw_models as rm

# (model, its column tuple, the glob matching the exports it is parsed from)
MODELS = [
    ("RawTradeRecord", cv.TRADES_COLUMNS, "data_import/Trades-*.csv"),
    ("RawCashTransactionRecord", cv.CASH_TRANSACTIONS_COLUMNS,
     "data_import/Cash_Transactions-*.csv"),
    ("RawPositionRecord", cv.POSITIONS_COLUMNS, "data_import/Positions-*.csv"),
    ("RawCorporateActionRecord", cv.CORPORATE_ACTIONS_COLUMNS,
     "data_import/Corporate_Actions-*.csv"),
    ("RawOptionsEAERecord", cv.OPTIONS_EAE_COLUMNS, "data_import/Options_EAE-*.csv"),
    ("RawCashBalanceRecord", cv.CASH_BALANCE_COLUMNS, "data_import/Cash_Balance-*.csv"),
]


def _aliases(model_name):
    model = getattr(rm, model_name)
    return {name: (info.alias or name) for name, info in model.__fields__.items()}


@pytest.mark.parametrize("model_name,columns,_glob",
                         MODELS, ids=[m[0] for m in MODELS])
def test_every_declared_field_maps_to_a_requested_column(model_name, columns, _glob):
    """
    The invariant. A field whose alias is not in the model's `*_COLUMNS` tuple can
    never be populated: the parsers reject unexpected columns, so the tuple is the
    complete set of what arrives. Such a field reads as a supported input at every
    call site, which is how a dead fallback gets wired to it.

    Adding a field means adding the column to the Flex Query *and* to the tuple.

    Probed: re-declaring `pay_date: Optional[str] = Field(None, alias="PayDate")` on
    `RawCorporateActionRecord` — the field whose absence from the export made two
    thirds of the corporate-action date chain dead — turns this red, naming PayDate.
    """
    unrequested = sorted(
        f"{name} (alias {alias!r})"
        for name, alias in _aliases(model_name).items()
        if alias not in set(columns)
    )
    assert not unrequested, (
        f"{model_name} declares {len(unrequested)} field(s) for columns no Flex Query "
        f"requests, so nothing can ever populate them: {unrequested}. Either add the "
        f"column to the Flex Query and to the matching *_COLUMNS tuple, or drop the "
        f"field. Leaving it declared is the state issue #64 exists to prevent."
    )


def test_the_column_tuples_match_the_real_exports():
    """
    The other half, and the reason the tuples can be trusted as ground truth above:
    `*_COLUMNS` must be what the files actually carry. If a tuple drifts from the
    export, the test above certifies a set of fields against a fiction.

    **One test over all six, skipping once.** It was six parametrised cases until
    2026-08-09, which meant six skip lines on any tree without `data_import/` — and
    six narrow-looking gaps read as six unrelated things when there is one condition:
    the exports are real account data and a clean clone has none. What a clean clone
    cannot check is *any* tuple against *any* export, and one line should say so.

    Every mismatch is collected before asserting, so one run names every drifted file
    rather than the first — CLAUDE.md's report-together rule. A partially populated
    `data_import/` checks what it has; only a wholly empty one skips.

    Probed: deleting "TradeDate" from `TRADES_COLUMNS` turns this red naming every
    Trades file (and the parser's own validator red for every trades file). Probed
    for the skip: with no exports present the suite reports one skip, not six.
    """
    checked = 0
    mismatches = []
    for model_name, columns, file_glob in MODELS:
        for path in sorted(glob.glob(file_glob)):
            checked += 1
            with open(path, newline="", encoding="utf-8-sig") as handle:
                header = set(next(csv.reader(handle)))
            if header != set(columns):
                mismatches.append(
                    f"{path} ({model_name}): only in the file "
                    f"{sorted(header - set(columns))}; only in the tuple "
                    f"{sorted(set(columns) - header)}"
                )

    if not checked:
        pytest.skip(
            "no exports under data_import/ — no column tuple is checked against a "
            "real export, so the two tests either side of this one compare the models "
            "against tuples nothing has anchored"
        )

    assert not mismatches, (
        f"{len(mismatches)} of {checked} export(s) do not match their column tuple:\n"
        + "\n".join(mismatches)
    )


def test_the_models_that_deliberately_drop_a_requested_column_are_listed():
    """
    The mirror case, pinned rather than fixed. Three columns are requested and
    delivered but have no field, so `extra = 'ignore'` discards them silently.

    They are left alone here because correcting one could move a figure — feeding
    `SubCategory` into `process_positions` would reach `preliminary_classify`, and
    classification drives Teilfreistellung and the KAP/KAP-INV split. That makes it
    Band A work with its own parity and knowledge-store gates, not part of a
    fix-nonfunc sweep.

    **Tracked as issue #69**, which ranks the three and says what each needs:
    `Amount` wants a `reference/` answer before any code (at least one corporate
    action has a non-zero `Amount` disagreeing with both `Proceeds` and `Value`);
    `SubCategory` wants its masking measured; `ClientAccountID` is inert until the
    per-Depot flip, because `account_key()` currently has no call sites.

    This test fails when the set changes, so the next person either finds the
    decision recorded or has to record their own.

    Probed: mapping `Amount` onto `RawCorporateActionRecord` turns this red.
    """
    dropped = {
        model_name: sorted(set(columns) - set(_aliases(model_name).values()))
        for model_name, columns, _ in MODELS
    }
    dropped = {k: v for k, v in dropped.items() if v}

    assert dropped == {
        "RawPositionRecord": ["ClientAccountID", "SubCategory"],
        "RawCorporateActionRecord": ["Amount"],
    }, (
        f"the set of requested-but-unmapped columns changed: {dropped}. If a column "
        f"gained a field, remove it from this list. If one was dropped, decide whether "
        f"the figure it could move has been checked."
    )
