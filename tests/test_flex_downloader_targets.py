"""
What the Flex Web Service downloader fetches, and what it calls the result.

legal_basis: infrastructure. The engine reads whatever is in `data_import/` and believes
it, so a report the downloader quietly does not fetch is a report the engine treats as
"this did not happen". That is not hypothetical: the Transfers report had no entry here
while its rows decided which account holds which lots, and a `--download` run produced a
`data_import/` that looked complete and was missing a year.

The other downloader (`src/web_portal/`) has its own file. This one covers the Flex Web
Service path, which is what `--download` uses and which had no test at all.

Every identifier below is invented.
"""
from pathlib import Path

import pytest

import src.config_example as config_example
from src.flex_downloader import FlexDownloadError, download_and_merge


ALL_IDS = {
    "trades": 1000001,
    "cash_transactions": 1000002,
    "positions": 1000003,
    "corporate_actions": 1000004,
    "cash_balance": 1000005,
    "options_eae": 1000006,
    "transfers": 1000007,
}


class TestEveryConfiguredQueryHasSomewhereToLand:
    """A query ID in the config is a promise that the report will be fetched."""

    def test_the_config_template_offers_an_id_for_every_report(self):
        """`config_example.py` is the tracked template, so a report it does not
        mention is a report nobody knows they can configure. Transfers was the one
        missing, which is why it was never downloaded."""
        assert set(config_example.FLEX_QUERY_IDS) == set(ALL_IDS)

    def test_transfers_is_one_of_them(self):
        """Named on its own because the general assertion above would stay green if
        both sides lost it together."""
        assert "transfers" in config_example.FLEX_QUERY_IDS

    def test_a_configured_query_with_nowhere_to_land_stops_the_run(self, tmp_path,
                                                                   monkeypatch):
        """The failure this file exists for. A query type the user has given an ID
        has to be either downloaded or refused -- skipping it silently leaves a
        `data_import/` that looks complete, and the engine then reads the absence as
        "nothing happened in that year"."""
        monkeypatch.setattr("src.flex_downloader.resolve_token", lambda: "TOKEN")
        monkeypatch.chdir(tmp_path)

        with pytest.raises(FlexDownloadError) as excinfo:
            download_and_merge(2025, {"a_report_nobody_mapped": 999},
                               cache_dir=str(tmp_path / "cache"))

        message = str(excinfo.value)
        assert "a_report_nobody_mapped" in message
        assert "transfers" in message, "the error lists what it does know"

    def test_an_unconfigured_query_is_skipped_without_raising(self, tmp_path,
                                                             monkeypatch):
        """`None` is the template's default and means "I have not made this query".
        It must stay ordinary: only an ID with nowhere to land is the error above."""
        monkeypatch.setattr("src.flex_downloader.resolve_token", lambda: "TOKEN")
        monkeypatch.chdir(tmp_path)

        assert download_and_merge(2025, {k: None for k in ALL_IDS},
                                  cache_dir=str(tmp_path / "cache")) == {}


class TestTheFileNamesTheConsumerLooksFor:
    """The downloader writes; `data_preparation` reads. Two spellings of one naming
    scheme drift, so this drives the consumer's own lookup over the writer's names."""

    def test_data_preparation_finds_every_report_the_downloader_can_write(
            self, tmp_path, monkeypatch):
        from src import data_preparation

        monkeypatch.setattr(data_preparation, "IMPORT_DIR", tmp_path)
        for prefix in ("Trades", "Cash_Transactions", "Corporate_Actions",
                       "Cash_Balance", "Options_EAE", "Transfers"):
            (tmp_path / f"{prefix}-2025.csv").write_text(
                '"ClientAccountID"\n"U1000000"\n', encoding="utf-8-sig")

            assert data_preparation._find_import_file(prefix, 2025) is not None, prefix
            assert data_preparation._find_years_available(prefix) == [2025], prefix
