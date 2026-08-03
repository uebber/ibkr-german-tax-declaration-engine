# EStG 20 -- Einkuenfte aus Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 20 EStG](https://www.gesetze-im-internet.de/estg/__20.html)
- **With annotations:** [dejure.org -- 20 EStG](https://dejure.org/gesetze/EStG/20.html)
- **Current version:** As amended by Jahressteuergesetz 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025

## Relevance to Engine

This is the central statute for all capital income taxation. It defines what constitutes capital income (Abs. 1), capital gains (Abs. 2), gain calculation (Abs. 4), corporate action treatment (Abs. 4a), and loss offsetting (Abs. 6).

---

## Abs. 1 -- Income Types (Laufende Einkuenfte)

### Nr. 1 -- Dividends
Dividends and other distributions from corporations (Koerperschaften).

**Engine mapping:** `DIVIDEND_CASH` event -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE`

### Nr. 3 -- Investmentertraege
*"Investmentertraege nach § 16 des Investmentsteuergesetzes"*. This is the hook through which all
fund income (Ausschuettungen, Vorabpauschale, Veraeusserungsgewinne) becomes Einkuenfte aus
Kapitalvermoegen. Nr. 3a does the same for Spezial-Investmentertraege nach § 34 InvStG -- out of
scope for this engine.

**Engine mapping:** all `ANLAGE_KAP_INV_*` categories; see `investment-tax-law/`. Declared on
Anlage KAP-INV, not Anlage KAP.

### Nr. 7 -- Interest
Interest from capital claims of any kind (Kapitalforderungen jeder Art).

**Engine mapping:** `INTEREST_RECEIVED` event -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE`

### Nr. 11 -- Stillhalterpraemien (Option Premiums)
Premiums received for granting options (Einraeumung von Optionen).

Statutory text (retrieved 2026-08-03): *"Stillhalterpraemien, die fuer die Einraeumung von
Optionen vereinnahmt werden; schliesst der Stillhalter ein Glattstellungsgeschaeft ab, sind die
im Glattstellungsgeschaeft gezahlten Praemien zum Zeitpunkt der Zahlung als negative Einnahmen zu
beruecksichtigen."*

Key rules:
- Premium is taxable upon receipt under Abs. 1 Nr. 11
- Glattstellungsgeschaeft (closing/buy-back): paid premium is a **negative Einnahme at the time
  of payment**. See the timing caveat below -- the *from when* is not settled here.
- Physical exercise: premium does NOT reduce under Nr. 11; instead affects cost basis of underlying trade (Abs. 2)
- Barausgleich (cash settlement) by Stillhalter: loss from Termingeschaeft under Abs. 2 Satz 1 Nr. 3a (per BFH VIII R 55/13)

**Engine mapping:** Short option events, `OPTION_EXPIRED_SHORT`, `OPTION_CASH_SETTLED_SHORT`

#### Open question -- from which VZ does the "negative Einnahmen" wording apply? (NOT resolved)

The *"zum Zeitpunkt der Zahlung als negative Einnahmen"* wording was put into the statute by the
**JStG 2024**, displacing BFH v. 02.08.2022 - VIII R 27/21, which had held that Glattstellung
costs reduce the Stillhalterpraemien **in the VZ the premium was received** (a rueckwirkendes
Ereignis under 175 Abs. 1 S. 1 Nr. 2 AO), not in the VZ of payment. The two readings put the
same amount in different years, so this changes a declared figure whenever the two legs straddle
a year end.

What is not established:

- buzer.de lists **two** JStG-2024 versions of § 20 EStG -- one effective **06.12.2024**
  (Art. 3) and one effective **01.01.2025** (Art. 4) -- and does not say which carried Nr. 11.
- No application rule in § 52 EStG for Nr. 11 has been located.
- Tier 5 sources disagree openly: Haufe Finance Office states application from 01.01.2024; Haufe
  Steuer Office Excellence states from the day after promulgation.

**What the engine does:** it books the paid premium at the payment date in every year. That
matches the new statutory wording, and it matches the administration's practice even before it
(BMF 18.01.2016 Rz. 25 ff., carried into BMF 19.05.2022 and 14.05.2025) -- but it is contrary to
BFH VIII R 27/21 for any VZ before the amendment took effect. **A straddling Stillhalter/
Glattstellung pair in VZ 2024 or earlier should be reviewed by hand.** Recorded in
`research/coverage-matrix.md`.

> **Correction, 2026-08-03.** This section previously asserted the change was "codified in
> statute effective 01.01.2024" as settled fact. The codification is real; the date was
> unsourced, contradicted this file's own header (JStG 2024, effective 01.01.2025), and is
> disputed. Validation Protocol items 3 and 7.

---

## Abs. 2 -- Capital Gains (Veraeusserungsgewinne)

### Satz 1 Nr. 1 -- Sale of shares in corporations (Aktien)
Gains from sale of shares in any corporation (Koerperschaft, Personenvereinigung, Vermoegensmasse).

**Engine mapping:** `LONG_POSITION_SALE` / `SHORT_POSITION_COVER` for STOCK category -> `ANLAGE_KAP_AKTIEN_GEWINN`

### Satz 1 Nr. 2 -- Sale of Dividenden-/Zinsscheine apart from the Stammrecht

**Not bonds.** Nr. 2 covers the sale of *"Dividendenscheinen und sonstigen Anspruechen durch den
Inhaber des Stammrechts, wenn die dazugehoerigen Aktien oder sonstigen Anteile nicht
mitveraeussert werden"* (Buchst. a) and of *"Zinsscheinen und Zinsforderungen durch den Inhaber
oder ehemaligen Inhaber der Schuldverschreibung, wenn die dazugehoerigen Schuldverschreibungen
nicht mitveraeussert werden"* (Buchst. b) -- i.e. a coupon or dividend claim detached from the
security it belongs to.

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__20.html.

**Engine mapping: none.** The engine has no event for a detached coupon sale.

> **Correction, 2026-08-03.** This entry previously read "Sale of other capital claims -- gains
> from sale of interest-bearing instruments (Anleihen, Zertifikate, etc.)" and carried the BOND
> engine mapping. That is Nr. 7, not Nr. 2 -- as this same file states correctly under
> "Satz 1 Nr. 7" and again in the Satz 2 section below. The file contradicted itself and the
> wrong half was the one carrying an engine mapping. Validation Protocol item 2.

### Satz 1 Nr. 3 -- Termingeschaefte (Derivatives)
Gains from derivatives/forward transactions.

**Sub-section 3a:** Gains from Barausgleich (cash settlement) of Termingeschaefte.

**Engine mapping:** `OPTION_TRADE_CLOSE_LONG/SHORT`, `OPTION_EXPIRED_LONG`, `OPTION_CASH_SETTLED_LONG/SHORT` -> `ANLAGE_KAP_TERMIN_GEWINN` (<=2024) or `ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT` (>=2025)

### Satz 1 Nr. 7 -- Gains from capital claims
Gains from redemption/sale of capital claims (Kapitalforderungen jeder Art).

Statutory text: *"der Gewinn aus der Veraeusserung von sonstigen Kapitalforderungen jeder Art im Sinne des Absatzes 1 Nummer 7"*

**Engine mapping:** Bond sales, FX gains on interest-bearing accounts

### Satz 2 -- Disposal fiction (Einloesung, Rueckzahlung, Abtretung)

**This is the provision that makes a bond redemption at maturity a taxable disposal.**

Statutory text: *"Als Veraeusserung im Sinne des Satzes 1 gilt auch die Einloesung, Rueckzahlung, Abtretung oder verdeckte Einlage in eine Kapitalgesellschaft; in den Faellen von Satz 1 Nummer 4 gilt auch die Vereinnahmung eines Auseinandersetzungsguthabens als Veraeusserung."*

> Verified 2026-08-02 against two Tier 1 sources: gesetze-im-internet.de/estg/__20.html
> and dejure.org/gesetze/EStG/20.html (wording, semicolon and word order agree).
> Version status: as amended by JStG 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025.
> Note Abs. 2 continues past Satz 2 -- Saetze 3-5 cover Personengesellschaft interests
> and the separation of Zinsschein/Zinsforderung from the Stammrecht; Satz 2 is not the
> end of the Absatz.

Satz 2 applies to **all** of Satz 1, including Nr. 7. Consequently:

| Event | Mechanism | Gain category |
|-------|-----------|---------------|
| Bond sold before maturity | Veraeusserung (Satz 1 directly) | Satz 1 Nr. 7 |
| Bond redeemed at maturity (Faelligkeit) | **Einloesung, deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |
| Bond repaid early (Rueckzahlung) | **deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |

Gain is computed under Abs. 4 (Veraeusserungserloes minus Veraeusserungskosten minus
Anschaffungskosten). Bonds are not Aktien, so the Abs. 6 Satz 4 ring-fencing does not apply.

**Correct citation for bond maturity is therefore `Abs. 2 Satz 1 Nr. 7 i.V.m. Satz 2`.**
Citing Satz 1 Nr. 7 alone is incomplete -- it establishes the gain category but not
that a redemption counts as a disposal at all.

#### Form placement (Tier 3 -- verified against the official Anleitung)

Verified against BOTH tax years the engine supports: Anleitung zur Anlage KAP **2024**
(`reference/Anltg_KAP_24.md`, Zeilen 18/19) and **2025** (`reference/Anltg_KAP_25.md`,
same wording at Zeile 19 and the identical "zusaetzlich" rule). The placement below is
unchanged by JStG 2024 -- that amendment removed Zeilen 21/24 (Termingeschaefte), which
bonds never used.

Anleitung zur Anlage KAP 2024, Zeilen 18/19:

- Zeile 18 takes **inlaendische** Kapitalertraege not yet subject to Steuerabzug by an
  inlaendische Zahlstelle.
- Zeile 19 takes **auslaendische** Ertraege, *"insbesondere Ertraege bei auslaendischen
  Kreditinstituten"*.
- *"Alle Veraeusserungstatbestaende tragen Sie bitte zusaetzlich in die Zeilen 20
  und / oder 22 und / oder 23 ein."*

The Z18/Z19 split turns on the **intermediary** (broker location), NOT on issuer domicile
-- see `reference/research/inlaendisch-auslaendisch-relevance.md`. Because IBKR is an Irish
broker, all income from this engine's inputs lands in Zeile 19 regardless of where the bond
issuer sits. **This mapping is conditional on that fact**; it is not a property of bond
maturities as such. A bond redeemed through a German Zahlstelle would belong in Zeile 18.

Applying the "zusaetzlich" rule: a bond maturity **gain** nets into Zeile 19 only (Zeile 20
is reserved for Aktien). A bond maturity **loss** subtracts within Zeile 19 and is
additionally entered in Zeile 22 as a positive amount (Zeile 23 is reserved for Aktien).

**Engine mapping:** IBKR corporate action `Type="BM"` -> synthetic `TRADE_SELL_LONG` ->
`RealizationType.LONG_POSITION_SALE` -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` (Zeile 19)
if positive, `ANLAGE_KAP_SONSTIGE_VERLUSTE` (Zeile 22) if negative. EUR conversion of both
legs follows the engine's general enrichment rule (ECB rate at each event date), not a
provision specific to Satz 2.

---

## Abs. 3 -- Special Benefits
Special benefits or advantages granted in addition to or in place of income under Abs. 1 and 2.

---

## Abs. 4 -- Gain Calculation

**Gain = Sale proceeds - Transaction costs - Acquisition costs (Anschaffungskosten)**

Abs. 4 has **nine Saetze**. Satz 1 defines the gain; **Satz 7** supplies the
lot-identification fiction that decides *which* Anschaffungskosten are used when several
lots of the same security are held.

**Engine implementation:** `FifoManager` with lot-level tracking.

### Satz 7 -- FIFO fiction (Verbrauchsreihenfolge)

Statutory text: *"Bei vertretbaren Wertpapieren, die einem Verwahrer zur Sammelverwahrung
im Sinne des § 5 des Depotgesetzes [...] anvertraut worden sind, ist zu unterstellen, dass
die zuerst angeschafften Wertpapiere zuerst veraeussert wurden."*

> Verified 2026-08-02 against two Tier 1 sources: gesetze-im-internet.de/estg/__20.html
> (full sentence, extracted from the official HTML) and dejure.org/gesetze/EStG/20.html
> (operative clause and Depotgesetz condition agree).
> Sentence position confirmed by the official numbering: Satz 7 of 9. Satz 8 concerns a
> Zinsschein separated from the Stammrecht, Satz 9 the allocation of that value -- neither
> continues the FIFO rule.
> Umlauts are transliterated per this library's convention. The elision `[...]` is the
> Depotgesetz version citation, verbatim: *"in der Fassung der Bekanntmachung vom
> 11. Januar 1995 (BGBl. I S. 34), das zuletzt durch Artikel 4 des Gesetzes vom
> 5. April 2004 (BGBl. I S. 502) geaendert worden ist, in der jeweils geltenden Fassung"*.

What the statute does and does not say:

- It **is mandatory** -- *"ist zu unterstellen"* is a Fiktion, not a default that the
  taxpayer may rebut.
- It does **not** say "per Depot". The only occurrence of "Depot" in Satz 7 is inside the
  citation *"Depotgesetzes"*. Depot-relatedness comes from Tier 2 (below), not from the
  statute.
- It does **not** offer a specific-identification alternative. Its only condition is the
  form of custody (Sammelverwahrung per § 5 DepotG).

#### Depot-relatedness (Tier 2 -- BMF, this is where "je Depot" comes from)

BMF-Schreiben vom 14. Mai 2025, GZ IV C 1 - S 2252/00075/016/070, *"Einzelfragen zur
Abgeltungsteuer"*, section I.4.b **Rz. 97-99**. Neufassung of BMF 19.05.2022
(BStBl I S. 742). The wording is **identical** in BMF 18.01.2016, so this is stable
administrative practice across both, not a recent change.

Rz. 97: *"Gemaess § 20 Absatz 4 Satz 7 EStG ist bei Wertpapieren bei der Veraeusserung aus
der Girosammelverwahrung (§§ 5 ff. DepotG) zu unterstellen, dass die zuerst angeschafften
Wertpapiere zuerst veraeussert werden (Fifo-Methode). Die Anwendung der Fifo-Methode im
Sinne des § 20 Absatz 4 Satz 7 EStG ist auf das einzelne Depot bezogen anzuwenden. Konkrete
Einzelweisungen des Kunden, welches Wertpapier veraeussert werden soll, sind insoweit
einkommensteuerrechtlich unbeachtlich."*

Rz. 98: *"Als Depot im Sinne dieser Regelung ist auch ein Unterdepot anzusehen. Bei einem
Unterdepot handelt es sich um eine eigenstaendige Untergliederung eines Depots mit einer
laufenden Unterdepot-Nummer. Der Kunde kann hierbei die Zuordnung der einzelnen Wertpapiere
zum jeweiligen Depot bestimmen."*

Rz. 99: *"Die Fifo-Methode gilt auch bei der Streifbandverwahrung."*

| Question | Answer | Source |
|----------|--------|--------|
| Is FIFO mandatory? | Yes -- Fiktion, not a default | Abs. 4 S. 7 (Tier 1) |
| May the taxpayer designate which lot is sold? | **No** -- *einkommensteuerrechtlich unbeachtlich* | Rz. 97 S. 3 (Tier 2) |
| Is FIFO pooled across depots, or per depot? | **Per single depot** | Rz. 97 S. 2 (Tier 2) |
| Does a sub-depot count as a depot? | **Yes**, if an independent subdivision with its own running number | Rz. 98 (Tier 2) |
| May the taxpayer choose which depot a security sits in? | **Yes** | Rz. 98 S. 3 (Tier 2) |
| Does FIFO also apply outside Sammelverwahrung? | Yes, also to Streifbandverwahrung | Rz. 99 (Tier 2) |

The pairing of Rz. 97 S. 3 with Rz. 98 S. 3 is deliberate and is the practically important
point: **lot selection by sale instruction is disregarded; lot allocation by custody
placement is respected.** Holding the same ISIN in two depots is therefore a lawful way to
influence which lots are consumed, whereas instructing the broker which lot to sell is not.

Note also that Sparer-Pauschbetrag and Abs. 6 loss offsetting operate per taxpayer at the
Veranlagung, across all depots. Depot separation changes the consumption order only.

#### Correction of a previous entry in this file

Until 2026-08-02 this section read, without any source:

> *"Key principle: FIFO method applies per asset per depot unless specific identification
> is possible."*

The *"unless specific identification is possible"* clause is **wrong** and is removed.
It is contradicted by Rz. 97 S. 3 (customer instructions on which security to sell are
irrelevant for income tax) and by Rz. 99 (FIFO applies even to Streifbandverwahrung, so
individual custody is not an escape either). The clause was a live hazard rather than a
harmless imprecision: IBKR itself supports lot-matching methods (LIFO, specific lot,
MaxLoss) and its realized-P&L output may reflect them, so an engine change that adopted
IBKR's lot matching would have been endorsed by this library while being contrary to
Rz. 97 S. 3. The "per depot" half was substantively correct but unsourced; it is now
carried by Rz. 97 S. 2.

#### Open question -- foreign custody (NOT settled, do not cite as resolved)

Satz 7 conditions the fiction on Sammelverwahrung *im Sinne des § 5 DepotG* -- a German
statute -- and Rz. 97-99 are written from the perspective of a German depotfuehrende
Stelle. Securities held through a foreign broker may sit in omnibus custody or in
Wertpapierrechnung, which is not § 5 DepotG Sammelverwahrung. Rz. 99 extending the method
to Streifbandverwahrung shows the administration applies FIFO irrespective of custody
form, which makes FIFO itself safe; what Rz. 97-99 do not squarely address is whether the
*"einzelnes Depot"* boundary transposes to a foreign broker's account/sub-account
structure. No Tier 1 or Tier 2 source located that settles this. Per-account FIFO is the
defensible reading and matches the administration's evident intent, but it is reasoned,
not sourced.

Practical consequence: this engine's outputs are Veranlagungsfaelle under § 32d Abs. 3
(foreign broker, no inlaendische Zahlstelle, no Steuerbescheinigung), so no bank has
applied FIFO and the taxpayer both computes and evidences it. § 90 Abs. 2 AO imposes an
erhoehte Mitwirkungspflicht for foreign matters, so a per-depot result must be evidenced
by per-account holdings, not merely asserted.

**Engine mapping and known deviation:** the ledger registries are keyed by
`(account_key, asset_id)`, but every write uses a single `DEFAULT_ACCOUNT` constant and no
account identifier is read anywhere in `src/engine/`, `src/domain/` or `src/processing/`
-- i.e. the key is a seam and FIFO is still pooled across accounts. This **deviates from
Rz. 97 S. 2**. It is currently without effect on the maintainer's own declaration, whose input
data contains exactly one `ClientAccountID`; per-depot and pooled FIFO coincide when there
is one depot. For any taxpayer
holding one ISIN in two accounts the pooled result is wrong. Flagged here per the
CLAUDE.md ground rule that code/reference conflicts are surfaced, not silently followed.
Note that a transfer between the taxpayer's own depots is **not** a Veraeusserung under
Abs. 2 (no change of beneficial owner, no consideration): acquisition date and cost carry
over to the receiving depot, so a per-depot implementation must relocate lots rather than
close and reopen them. The § 43 / § 43a Depotuebertrag rules (BMF Rz. 162-173, 184a-193)
are Kapitalertragsteuer provisions addressed to German institutions and do not apply to a
foreign broker; they cannot be cited for the disposal question.

### Abs. 4a -- Corporate Actions (Kapitalmasnahmen)

**Satz 1-2: Stock-for-stock mergers/exchanges**
When shares are exchanged for shares of another corporation due to corporate measures (gesellschaftsrechtliche Massnahmen), the new shares step into the tax position of the old shares. No taxable event occurs.

Conditions:
- German taxation right on gain is not excluded/restricted, OR
- EU Merger Directive (Art. 8, Richtlinie 2009/133/EG) applies

Additional cash consideration (Barzuzahlung) is taxable under Abs. 1 Nr. 1.

**Satz 5: Zuteilung without consideration (foreign corporations)**
Shares allocated without consideration by a corporation with *"weder Geschaeftsleitung noch Sitz
im Inland"*: income and acquisition cost are both set to EUR 0, and the cost basis of the shares
that gave rise to the allocation is unchanged. **Conditional** -- the statute adds *"wenn die
Voraussetzungen der Saetze 3, 4 und 7 nicht vorliegen"*, i.e. Satz 5 is the residual case after
the Wandelanleihe (Satz 3), Bezugsrecht (Satz 4) and Abspaltung (Satz 7) rules. The engine
applies the EUR 0 treatment without testing those three conditions.

**Satz 7: Spin-offs (Abspaltungen)**
Asset transfer via Abspaltung: Satz 1 and 2 apply analogously.

**Satz 6: Timing**
*"Soweit es auf die steuerliche Wirksamkeit einer Kapitalmassnahme im Sinne der vorstehenden
Saetze 1 bis 5 ankommt, ist auf den Zeitpunkt der Einbuchung in das Depot des Steuerpflichtigen
abzustellen."*

> **Correction, 2026-08-03.** Previously cited as "Satz 8". **Abs. 4a has seven Saetze; there is
> no Satz 8.** The timing rule is Satz 6 and it is expressly limited to Saetze 1 bis 5 -- it
> does not govern the Abspaltung case in Satz 7. Retrieved 2026-08-03 from
> gesetze-im-internet.de/estg/__20.html. Validation Protocol item 2.

**Saetze 3 and 4 -- present in the statute, not implemented**
- Satz 3: Wandel-/Umtauschanleihen -- where the holder or issuer exercises a right to deliver
  shares instead of cash at maturity, the cost of the claim becomes the disposal price of the
  claim *and* the acquisition cost of the shares received.
- Satz 4: Bezugsrechte -- the portion of the old shares' acquisition cost attributable to the
  subscription right is set at EUR 0.

Neither has an engine event. Recorded per Validation Protocol item 2.

**Engine mapping:**
- `CORP_MERGER_STOCK` -> tax-neutral cost basis transfer (FifoManager drain/receive)
- `CORP_MERGER_CASH` -> `CASH_MERGER_PROCEEDS` realization
- `CORP_SPLIT_FORWARD` -> lot quantity/cost adjustment
- `CORP_STOCK_DIVIDEND` -> new shares with EUR 0 cost basis (if foreign)

---

## Abs. 6 -- Loss Offsetting

See dedicated file: [estg-20-abs6-verlustverrechnung.md](estg-20-abs6-verlustverrechnung.md)

---

## Abs. 8 -- Subsidiarity (Subsidiaritaet)

Capital income that belongs to income from agriculture/forestry, trade/business, self-employment, or rental is attributed to those income types instead. This engine assumes all positions are in Privatvermoegen (private assets).
