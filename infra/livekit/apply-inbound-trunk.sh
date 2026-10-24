#!/bin/sh
# Render infra/livekit/inbound-trunk.json and apply it to dev LiveKit.
# A second run that already matches the trunk does not create or update.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
exec python3 "$root/voice/sip/apply.py" --config "$root/infra/livekit/inbound-trunk.json" "$@"
