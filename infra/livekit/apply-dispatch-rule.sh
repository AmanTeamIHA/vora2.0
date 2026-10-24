#!/bin/sh
# Render infra/livekit/dispatch-rule.json and apply it to dev LiveKit.
# A second run that already matches the rule does not create or update.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
exec python3 "$root/voice/sip/apply_dispatch.py" --config "$root/infra/livekit/dispatch-rule.json" "$@"
