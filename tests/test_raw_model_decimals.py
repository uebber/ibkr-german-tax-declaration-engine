"""A blank decimal column is not a zero, and the per-field validators now get to say so.

Issue #47. `RawBaseRecord` defined `parse_all_decimals`, a `@validator('*', pre=True)` that
ran `safe_decimal(v, default=Decimal("0.0"))` over every `Decimal`-typed field.

The mechanism was the opposite of the one reported, and the difference is why the defect
survived a reading. Pydantic runs a subclass's pre-validators *before* an inherited one, so
the wildcard did not hide the raw value from `parse_decimal_fields` — it ran afterwards and
overwrote what `parse_decimal_fields` returned. Each model's rule takes trouble to tell blank
from zero:

    safe_decimal(v, default=None if v is None or str(v).strip() == "" else Decimal("0.0"))

and the wildcard turned every `None` it produced straight back into `Decimal("0.0")`. So the
distinction could not be observed anywhere, and the per-field rule read as though it guarded
something. Two silent shapes, both as reported: a blank optional column arrived downstream as
a real zero, and a maintainer reading the field validator believed a check was active.

It also meant a **required** decimal that arrived blank became `Decimal("0.0")` rather than
failing — a substituted value of exactly the kind `CLAUDE.md` forbids.

What these tests hold, and why deleting the wildcard is safe rather than merely tidy: every
`Decimal` field on every raw model has its own validator, and the first test below fails if
one is ever added without one.

Calibration: each per-model case was verified by breaking that model's `parse_decimal_fields`
and confirming this file goes red for that model and no other. Recorded in the issue #47
commit.
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.parsers import raw_models as rm

# The one thing that has to be written by hand: a minimal payload each model parses.
# The Decimal fields to exercise are NOT written here -- they are read off the model
# below, so a field added tomorrow is covered tomorrow. They were two hand-kept lists
# per model until 2026-08-09, which had two costs. A new optional Decimal landed with
# no blank-vs-zero coverage and nothing said so (probed: `FXRateToBase` added to
# `RawTradeRecord` and `TRADES_COLUMNS` with the standard validator, suite green). And
# where a list was empty the case skipped with a *reason* -- "has no optional Decimal
# fields" -- that nothing kept true; four of these skipped permanently.
PAYLOADS = {
    "RawTradeRecord":
        {"CurrencyPrimary": "EUR", "AssetClass": "STK", "Symbol": "X",
         "Description": "d", "TradeDate": "2024-01-02", "Quantity": "1",
         "TradePrice": "1"},
    "RawCashTransactionRecord":
        {"CurrencyPrimary": "EUR", "Description": "d", "SettleDate": "2024-01-02",
         "Type": "Dividends", "Amount": "1"},
    "RawPositionRecord":
        {"CurrencyPrimary": "EUR", "AssetClass": "STK", "Symbol": "X",
         "Description": "d", "Quantity": "1"},
    "RawCorporateActionRecord":
        {"Symbol": "X", "Description": "d", "Report Date": "2024-01-02", "Type": "FS"},
    "RawOptionsEAERecord":
        {"CurrencyPrimary": "EUR", "Symbol": "X", "Description": "d",
         "Date": "2024-01-02", "Transaction Type": "Cash Settlement"},
}

# `RawCashBalanceRecord` is deliberately absent above: its validator defaults a blank to
# zero on purpose, so it would fail both behaviour tests. It is pinned by its own test at
# the foot of this file, and still carries the every-field-has-a-validator invariant.
ALL_MODELS = list(PAYLOADS) + ["RawCashBalanceRecord"]


def _decimal_aliases(model_name, *, required):
    """The model's own answer to "which Decimal fields are (not) required"."""
    model = getattr(rm, model_name)
    return sorted(
        (info.alias or name)
        for name, info in model.__fields__.items()
        if info.type_ is Decimal and bool(info.required) is required
    )


def _models_having(*, required):
    """Only models that actually have such a field, so no case is ever vacuous.

    A model with none simply produces no test, rather than a test that skips with a
    claim about the model that nothing rechecks.
    """
    return [m for m in PAYLOADS if _decimal_aliases(m, required=required)]


def _alias_to_field(model):
    return {(info.alias or name): name for name, info in model.__fields__.items()}


# --------------------------------------------------------------------------- invariants


@pytest.mark.parametrize("model_name", ALL_MODELS)
def test_every_decimal_field_has_its_own_validator(model_name):
    """
    The invariant that makes removing the wildcard safe. A `Decimal` field with no
    per-field validator would, before #47, still have been coerced by the inherited
    wildcard; with the wildcard gone it gets raw pydantic coercion instead, which
    rejects a blank string outright and never yields `None`.

    So: adding a `Decimal` field without adding it to that model's `parse_decimal_fields`
    is now a behaviour change, and this test is what catches it.

    Probed: dropping `'strike'` from `RawTradeRecord.parse_decimal_fields`'s field list
    turns this red for RawTradeRecord and nothing else.
    """
    model = getattr(rm, model_name)
    decimal_fields = {n for n, i in model.__fields__.items() if i.type_ is Decimal}
    with_own = {
        name
        for name, info in model.__fields__.items()
        for v in (info.pre_validators or [])
        if getattr(v, "func", v).__qualname__.startswith(f"{model_name}.")
    }
    missing = sorted(decimal_fields - with_own)
    assert not missing, (
        f"{model_name} has Decimal field(s) with no per-field validator: {missing}. "
        f"Add them to that model's `parse_decimal_fields`. Until #47 the inherited "
        f"`RawBaseRecord.parse_all_decimals` covered such a field silently; nothing does now."
    )


def test_the_base_record_declares_no_validators_at_all():
    """
    Structural, so reintroducing a wildcard is a failure rather than a silent
    re-shadowing. The hazard is specifically a validator inherited by every model: it
    runs *after* the subclass's own pre-validators and discards their result, and
    neither site shows which order applies.

    Probed: restoring `parse_all_decimals` on `RawBaseRecord` turns this red.
    """
    own = [
        name for name, member in vars(rm.RawBaseRecord).items()
        if getattr(member, "__validator_config__", None) is not None
        or name.startswith("validate_") and callable(member)
    ]
    assert not own, (
        f"RawBaseRecord grew validator(s) {own}. A validator here applies to every raw "
        f"model and runs after each model's own pre-validators, overwriting them — which "
        f"is exactly the #47 defect."
    )


# ------------------------------------------------------------------- per-model behaviour


@pytest.mark.parametrize("model_name", _models_having(required=False))
def test_a_blank_optional_decimal_is_none_not_zero(model_name):
    """
    The observable half of the defect. `Strike` is blank on 5,293 of 6,976 trade rows in
    the 2021-2025 history — every non-option — and each one arrived as `Decimal("0.0")`.

    None of those reach a figure today (`strike_price` exists only on `Option`, the
    resolver's update path is `isinstance`-guarded, and every OPT row carries a real
    strike), which is why #47 is Band B. The point is that nothing was arranging for
    that; the distinction the field validator computes was simply thrown away.
    """
    payload = PAYLOADS[model_name]
    optional_decimals = _decimal_aliases(model_name, required=False)
    model = getattr(rm, model_name)
    alias_to_field = _alias_to_field(model)

    record = model.parse_obj({**payload, **{a: "" for a in optional_decimals}})
    for alias in optional_decimals:
        value = getattr(record, alias_to_field[alias])
        assert value is None, (
            f"{model_name}.{alias_to_field[alias]} came back as {value!r} for a blank "
            f"{alias!r}. A blank column is an absent value, not a zero."
        )


@pytest.mark.parametrize("model_name", _models_having(required=False))
def test_a_real_decimal_still_parses(model_name):
    """A validator that rejects everything would also pass the test above."""
    payload = PAYLOADS[model_name]
    optional_decimals = _decimal_aliases(model_name, required=False)
    model = getattr(rm, model_name)
    alias_to_field = _alias_to_field(model)

    record = model.parse_obj({**payload, **{a: "12.5" for a in optional_decimals}})
    for alias in optional_decimals:
        value = getattr(record, alias_to_field[alias])
        assert value == Decimal("12.5"), (
            f"{model_name}.{alias_to_field[alias]} did not parse a real value: {value!r}")


@pytest.mark.parametrize("model_name", _models_having(required=True))
def test_a_blank_required_decimal_is_rejected(model_name):
    """
    No silent default. A required decimal that arrives blank used to become
    `Decimal("0.0")` — a substituted value standing in for an input the run does not
    have, which `CLAUDE.md` forbids outright. It now fails validation.

    **Two models produce no case here, and that is a decision rather than a gap.**
    Every Decimal on `RawCorporateActionRecord` and `RawOptionsEAERecord` is optional,
    so a blank one parses to `None` — right at this layer, since #47 made blank mean
    absent — and the question moves downstream, where the two are not alike:

    - a blank `Proceeds` on an OptionEAE cash settlement yields no event, and
      `_require_option_cash_settlements` then stops the run naming the contract;
    - a blank `Value` on a stock dividend reaches the `HI`/`SD` branch of
      `DomainEventFactory`, which logs *"Assuming 0 FMV"* and declares the dividend at
      zero. That is a substituted value understating Kapitalerträge, and no test holds
      it. **Unreached, not unreachable:** measured 2026-08-09 over the 2021-2025
      import, 5 rows of that type and no blank cell in any corporate-action decimal.
      **Issue #72**, and Band A rather than a fix here — what such a row is worth, and
      whether the `Amount` column #69 leaves unmapped answers it, needs `reference/`
      before any code.

    Note what that failure currently reaches: every parser in `src/parsers/` catches
    `ValidationError`, prints it, and skips the row. So the run does not stop — it loses
    the row instead. **Issue #70**; the coercion is fixed here, the swallow is not, and
    until it is this case has moved from one silent failure to another. No row in
    `data_import/` is affected today — of the 25 `Decimal` fields across the six models,
    only `Strike` is ever blank, and it is optional.
    """
    payload = PAYLOADS[model_name]
    required_decimals = _decimal_aliases(model_name, required=True)
    model = getattr(rm, model_name)

    for alias in required_decimals:
        with pytest.raises(ValidationError):
            model.parse_obj({**payload, alias: ""})


def test_the_cash_balance_record_keeps_its_own_zero_default():
    """
    The one model that deliberately differs, pinned so the difference stays deliberate.
    `RawCashBalanceRecord.parse_decimal_fields` passes `default=Decimal("0.0")`
    unconditionally, so a blank balance is zero rather than absent — which for a cash
    report is the honest reading of an empty cell.

    Probed: deleting that validator turns this red (raw pydantic rejects `""`).
    """
    record = rm.RawCashBalanceRecord.parse_obj({
        "CurrencyPrimary": "EUR", "FromDate": "20240101", "ToDate": "20241231",
        "StartingCash": "", "EndingCash": "",
    })
    assert record.starting_cash == Decimal("0.0")
    assert record.ending_cash == Decimal("0.0")
