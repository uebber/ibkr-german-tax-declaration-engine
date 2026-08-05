#!/usr/bin/env bash
# Parity check tooling (rework2-plan AR0, ground rules 4 & 5).
#
# Captures a full real-data pipeline run and compares two captures. A capture is
# three artifacts:
#   parity/<label>.console.txt   stdout -- the tax report itself
#   parity/<label>.log.txt       stderr -- the logging stream
#   parity/<label>.pdf           the generated PDF
#
# Run-random noise is normalized away: leading log timestamps, per-run event
# UUIDs, and the output PDF path. PDFs are compared with CreationDate/ModDate/ID
# stripped (they differ between ANY two runs by PDF design).
#
# Three properties this script deliberately guarantees, none of which it had
# originally:
#
# 1. HERMETIC w.r.t. cache/. The pipeline both reads and writes
#    cache/user_classifications.json. Left alone, the baseline capture warms the
#    cache and the second capture reads it back, so a change to classification
#    logic is invisible -- demonstrated: a heuristic change moving a holding from
#    STOCK to AKTIENFONDS (Aktien 2250.00 -> 250.00, Fonds 0.00 -> 1568.00)
#    compared as IDENTICAL with a warm cache and produced a 46-line diff with a
#    cold one. Classification drives Teilfreistellung and the KAP/KAP-INV split,
#    so this was the blind spot with the largest tax consequence. Each capture
#    now runs against a snapshot of cache/ that is restored afterwards: both legs
#    start from identical state and the maintainer's curated cache is never
#    mutated (deleting it is not an acceptable way to get hermeticity -- it holds
#    hand-made classifications that cannot be recomputed).
#    The guarantee is precisely "every capture sees the same cache state, and no
#    capture inherits another's writes". It is NOT "classification changes are
#    always visible": an asset already carrying an explicit cached classification
#    is resolved from the cache in both legs, which is also what production does,
#    so a heuristic change genuinely does not affect it. What the snapshot
#    restores is the ability to see changes for assets the cache does not yet
#    cover -- which, before this, the baseline capture itself silently populated.
#    data/ needs no such treatment: prepare_data_for_tax_year() regenerates it
#    from data_import/ on every run.
#
# 2. ORDER-SENSITIVE. The original merged stdout and stderr with 2>&1 and then
#    sorted, because merging two differently-buffered streams makes line order
#    nondeterministic (proven: the same code under PYTHONUNBUFFERED=1 moves 16
#    lines). Sorting reduced the comparison to a multiset of lines. The streams
#    are now captured separately, which removes the interleaving at source and
#    lets both be compared in order -- the report is a document, and its sequence
#    is part of its meaning.
#
# 3. PORTABLE. `stat -c%s` is GNU-only and fails on macOS, where this repo is
#    developed; it sat in the PDF-difference branch, so it only broke once there
#    was something to report. Uses `wc -c`.
#
# Console and PDF differences are fatal. A log-only difference is reported but
# not fatal, since adding a log line is a legitimate change that should not block
# an output-neutral refactor; set PARITY_STRICT_LOG=1 to enforce it too.
#
# Usage:
#   scripts/parity_check.sh capture <label> [extra main.py args...]
#   scripts/parity_check.sh compare <labelA> <labelB>
# Captures live under parity/ (gitignored — contains real account data).
set -euo pipefail
cmd=${1:?usage: parity_check.sh capture|compare ...}
mkdir -p parity

_cache_backup=""
_cache_existed=0

restore_cache() {  # runs on every exit path, including Ctrl-C and pipeline failure
  [ -n "$_cache_backup" ] || return 0
  rm -rf cache
  if [ "$_cache_existed" -eq 1 ]; then mv "$_cache_backup/cache" cache; fi
  rm -rf "$_cache_backup"
  _cache_backup=""
}
trap restore_cache EXIT

snapshot_cache() {
  _cache_backup="$(mktemp -d "${TMPDIR:-/tmp}/parity-cache.XXXXXX")"
  if [ -d cache ]; then
    _cache_existed=1
    cp -R cache "$_cache_backup/cache"
  else
    _cache_existed=0
  fi
}

normalize() {  # strip run-random noise; NO sort -- order is part of the output
  sed -E 's/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:,]+ - //;
          s/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/UUID/g;
          s|parity/[A-Za-z0-9_.-]+\.pdf|PDF|g' "$1"
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

diff_leg() {  # <name> <fileA> <fileB> <outfile>; prints verdict, returns 1 on difference
  local name=$1 a=$2 b=$3 out=$4
  if diff <(normalize "$a") <(normalize "$b") > "$out"; then
    echo "${name}: IDENTICAL (normalized)"
    rm -f "$out"
    return 0
  fi
  echo "${name} DIFF (normalized): $(grep -c '^[<>]' "$out" || true) changed lines -> $out"
  return 1
}

case "$cmd" in
  capture)
    label=${2:?label required}; shift 2
    snapshot_cache   # restored by the EXIT trap; see property 1 above
    # --no-interactive + stdin /dev/null: a capture must be deterministic; an
    # unexpected classification prompt fails fast (EOFError) instead of hanging.
    # stdout and stderr are kept apart on purpose; see property 2 above.
    uv run python -m src.main --report-tax-declaration --no-interactive \
      --pdf-output-file "parity/${label}.pdf" "$@" \
      < /dev/null > "parity/${label}.console.txt" 2> "parity/${label}.log.txt"
    # Record the invocation so compare can refuse unlike runs -- two captures
    # taken at different --tax-year values are not a parity result.
    printf 'args=%s\nhead=%s\n' "$*" "$(git rev-parse HEAD 2>/dev/null || echo unknown)" \
      > "parity/${label}.meta"
    echo "captured parity/${label}.{console.txt,log.txt,pdf}"
    ;;
  compare)
    a=${2:?labelA}; b=${3:?labelB}
    fail=0

    args_a=$(sed -n 's/^args=//p' "parity/${a}.meta" 2>/dev/null || true)
    args_b=$(sed -n 's/^args=//p' "parity/${b}.meta" 2>/dev/null || true)
    if [ "$args_a" != "$args_b" ]; then
      echo "REFUSING: captures used different arguments ('${args_a}' vs '${args_b}')" >&2
      exit 2
    fi

    diff_leg "console" "parity/${a}.console.txt" "parity/${b}.console.txt" \
      "parity/${a}_vs_${b}.console.diff" || fail=1

    if ! diff_leg "log" "parity/${a}.log.txt" "parity/${b}.log.txt" \
         "parity/${a}_vs_${b}.log.diff"; then
      if [ "${PARITY_STRICT_LOG:-0}" = "1" ]; then
        fail=1
      else
        echo "  (log difference is not fatal; set PARITY_STRICT_LOG=1 to enforce)"
      fi
    fi

    if ! cmp -s <(pdf_strip_meta "parity/${a}.pdf") <(pdf_strip_meta "parity/${b}.pdf"); then
      echo "PDF DIFF (metadata-stripped): sizes $(wc -c < "parity/${a}.pdf") vs $(wc -c < "parity/${b}.pdf") bytes"
      fail=1
    else
      echo "pdf: IDENTICAL (metadata-stripped)"
    fi
    exit $fail
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
