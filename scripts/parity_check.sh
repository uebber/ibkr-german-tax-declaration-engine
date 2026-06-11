#!/usr/bin/env bash
# Parity check tooling (rework2-plan AR0, ground rules 4 & 5).
#
# Captures a full real-data pipeline run (console + PDF) and compares two
# captures with run-random noise normalized:
#   - leading log timestamps,
#   - run-random event UUIDs (regenerated every run),
#   - the output PDF path,
#   - log emission order (sorted; dict iteration order is not deterministic).
# PDFs are compared by size and content with the CreationDate/ModDate/ID
# metadata ignored (they differ between ANY two runs by PDF design).
#
# Usage:
#   scripts/parity_check.sh capture <label> [extra main.py args...]
#   scripts/parity_check.sh compare <labelA> <labelB>
# Captures live under parity/ (gitignored — contains real account data).
set -euo pipefail
cmd=${1:?usage: parity_check.sh capture|compare ...}
mkdir -p parity

normalize() {
  sed -E 's/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ - //;
          s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/UUID/g;
          s|parity/[A-Za-z0-9_.-]+\.pdf|PDF|g' "$1" | sort
}

pdf_strip_meta() {  # remove volatile PDF metadata for byte comparison
  python3 - "$1" <<'PY'
import re, sys
b = open(sys.argv[1], "rb").read()
b = re.sub(rb"/CreationDate \(D:[^)]*\)", b"/CreationDate (D:0)", b)
b = re.sub(rb"/ModDate \(D:[^)]*\)", b"/ModDate (D:0)", b)
b = re.sub(rb"/ID\s*\n?\[<[0-9a-fA-F]+><[0-9a-fA-F]+>\]", b"/ID [<0><0>]", b)
sys.stdout.buffer.write(b)
PY
}

case "$cmd" in
  capture)
    label=${2:?label required}; shift 2
    # --no-interactive + stdin /dev/null: a capture must be deterministic; an
    # unexpected classification prompt fails fast (EOFError) instead of hanging.
    uv run python -m src.main --report-tax-declaration --no-interactive \
      --pdf-output-file "parity/${label}.pdf" "$@" \
      < /dev/null > "parity/${label}.console.txt" 2>&1
    echo "captured parity/${label}.{console.txt,pdf}"
    ;;
  compare)
    a=${2:?labelA}; b=${3:?labelB}
    fail=0
    if ! diff <(normalize "parity/${a}.console.txt") <(normalize "parity/${b}.console.txt") \
         > "parity/${a}_vs_${b}.console.diff"; then
      echo "CONSOLE DIFF (normalized): $(wc -l < parity/${a}_vs_${b}.console.diff) lines -> parity/${a}_vs_${b}.console.diff"; fail=1
    else
      echo "console: IDENTICAL (normalized)"
    fi
    if ! cmp -s <(pdf_strip_meta "parity/${a}.pdf") <(pdf_strip_meta "parity/${b}.pdf"); then
      echo "PDF DIFF (metadata-stripped): sizes $(stat -c%s parity/${a}.pdf) vs $(stat -c%s parity/${b}.pdf)"; fail=1
    else
      echo "pdf: IDENTICAL (metadata-stripped)"
    fi
    exit $fail
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
