#!/bin/bash
# Verifies the archived v4.17 trader files: (1) checksums in MANIFEST.sha256, (2) byte-identity with the blobs on
# origin/main at the archived commit. Read-only. Usage: bash trader-archive/live-trader-4.17/verify_archive.sh
set -euo pipefail
cd "$(dirname "$0")"
( cd files && sha256sum -c ../MANIFEST.sha256 )
REPO=$(git rev-parse --show-toplevel)
COMMIT=$(sed -n 's/^Archived from origin\/main commit: //p' PROVENANCE.md)
for f in files/*; do
  b=$(basename "$f")
  if git -C "$REPO" cat-file -e "$COMMIT:$b" 2>/dev/null; then
    if git -C "$REPO" show "$COMMIT:$b" | cmp -s - "$f"; then echo "identical to $COMMIT:$b"; else echo "DIFFERS from $COMMIT:$b"; exit 1; fi
  else echo "note: $COMMIT not in this clone (git fetch origin main) - checksum check above still applies"; fi
done
echo ARCHIVE_OK
