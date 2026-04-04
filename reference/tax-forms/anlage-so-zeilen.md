# Anlage SO -- Zeilenreferenz (Private Veraeusserungsgeschaefte)

## Source

- **Form download:** [formulare-bfinv.de -- Formular-Management-System](https://www.formulare-bfinv.de/)
- **EStH 2024 -- 23 EStG:** [esth.bundesfinanzministerium.de](https://esth.bundesfinanzministerium.de/esth/2024/A-Einkommensteuergesetz/II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/g-Sonstige-Einkuenfte-22-23/Paragraf-23/inhalt.html)
- **EStH 2024 -- Anhang 26 Private Veraeusserungsgeschaefte:** [esth.bundesfinanzministerium.de](https://esth.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-26/inhalt.html)
- **ELSTER Help 2024:** [elster.de -- Anleitung SO](https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_12_2024)
- **Legal basis:** EStG 22 Nr. 2, 23 Abs. 1 Nr. 2

## Relevance to Engine

Reports gains/losses from sale of "other assets" (Gold ETCs, Crypto ETPs, etc.) within the 1-year speculation period.

---

## Structure of Anlage SO (2024)

The Anlage SO covers two main categories:
1. **Leistungen** (22 Nr. 3 EStG) -- not used by this engine
2. **Private Veraeusserungsgeschaefte** (22 Nr. 2, 23 EStG) -- used by this engine

### Private Veraeusserungsgeschaefte Sections

The form distinguishes:
- Grundstuecke und grundstuecksgleiche Rechte (10-year period, 23 Abs. 1 Nr. 1)
- Kryptowaehrungen/virtuelle Waehrungen (1-year period, Zeilen 41-47)
- Andere Wirtschaftsgueter (1-year period, Zeilen 48-55)

---

## Lines Used by Engine

### Zeilen 48-55: Andere Wirtschaftsgueter

| Zeile | Content |
|-------|---------|
| 48 | Art des Wirtschaftsguts (description) |
| 49 | Anschaffungsdatum |
| 50 | Veraeusserungsdatum |
| 51 | Veraeusserungspreis |
| 52 | Anschaffungskosten |
| 53 | Werbungskosten |
| 54 | Gewinn/Verlust |
| 55 | (Sum / additional info) |

**Engine mapping:**
- `SECTION_23_ESTG_TAXABLE_GAIN` -> positive amount in Zeile 54
- `SECTION_23_ESTG_TAXABLE_LOSS` -> negative amount in Zeile 54
- `SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET` -> not reported (holding period > 1 year = tax-exempt)

---

## Key Rules

### Freigrenze (Exemption Threshold)
- EUR 1,000 per calendar year (since VZ 2024, changed from EUR 600 by JStG 2024)
- Applies to total gain from ALL private sales combined
- If exceeded, the ENTIRE gain is taxable (Freigrenze, not Freibetrag)
- Engine does not apply this threshold; it reports the gross figure

### Loss Offsetting
- 23 EStG losses can only offset 23 EStG gains
- No cross-offsetting with 20 EStG capital income
- Loss carryback to preceding year and carryforward to subsequent years possible (per 10d analogously)

### FIFO
The engine applies FIFO to determine which lots are sold and their holding periods. This follows the general principle applied by the Finanzverwaltung for fungible assets.
