# Lanes

Directory ownership so parallel agents do not edit the same files. A builder touches only its lane. Shared paths change only through a contract ticket, and that PR needs review.

| Lane | Directories |
|---|---|
| A Telephony | `voice/sip/`, `infra/livekit/` |
| B AI worker | `voice/agent/` |
| C Call data | `app/api/calls/`, `voice/egress/` |
| D Admin | `app/web/admin/` |
| Shared | `packages/contracts/`, migrations |

Shared means Alembic revisions under `app/api/alembic/` and the models in `packages/contracts/`. Contract changes go through the call contract (`docs/CALL_CONTRACT.md`) and PR review. Do not widen a lane ticket into those paths.

WIP limit: one In Progress ticket per lane.
