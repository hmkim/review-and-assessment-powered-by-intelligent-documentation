#!/usr/bin/env bash
# Download the corpus D2/D3 fixtures (law.go.kr attachments) listed in external_sources.json
# into evals/ko/corpus/external/ and verify their sha256. Already-present, matching files
# are skipped. Requires curl and python3.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$HERE/external"
SOURCES="$HERE/external_sources.json"
mkdir -p "$OUT_DIR"

BASE_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["base_url"])' "$SOURCES")"

python3 -c 'import json,sys
for f in json.load(open(sys.argv[1], encoding="utf-8"))["files"]:
    print(f["filename"] + "\t" + f["flSeq"] + "\t" + f["sha256"])' "$SOURCES" |
while IFS=$'\t' read -r filename flseq expected; do
  target="$OUT_DIR/$filename"
  if [ -f "$target" ] && [ "$(sha256sum "$target" | cut -d' ' -f1)" = "$expected" ]; then
    echo "ok       $filename (already present)"
    continue
  fi
  tmp="$(mktemp "$OUT_DIR/.download.XXXXXX")"
  echo "fetching $filename (flSeq=$flseq)"
  curl -fsSL -A "Mozilla/5.0" -e "https://www.law.go.kr/" -o "$tmp" "${BASE_URL}${flseq}"
  actual="$(sha256sum "$tmp" | cut -d' ' -f1)"
  if [ "$actual" != "$expected" ]; then
    rm -f "$tmp"
    echo "ERROR: sha256 mismatch for $filename (got $actual); the attachment may have been replaced on law.go.kr" >&2
    exit 1
  fi
  mv "$tmp" "$target"
  echo "ok       $filename"
done

echo "external fixtures ready in $OUT_DIR"
