# Voice worker

LiveKit Agents process. Sarvam supplies Saaras STT, the `sarvam-105b-conversations` LLM, and Bulbul TTS. The worker reads the deployed agent version from `POST /internal/calls/start` on the private API (`VORA_API_INTERNAL_URL`, default `http://api.vora2.local:8000`) with the `x-vora-internal` header. Playground sets that variable to port 8080 on the dev load balancer. That port accepts the agent security group only. The public 443 listener still returns 404 for `/internal`.

On each call it also reads `GET /internal/integrations/sarvam`. That response is the Sarvam API key saved under Admin → Global Settings → Integrations, plus the STT, TTS, and LLM model ids. `SARVAM_API_KEY` in the environment is used only when that setting is empty or the private API cannot be reached. The worker does not need `vora2/dev/sarvam` in Secrets Manager.

Per-turn latency is one CloudWatch EMF line on stdout (`Vora/Voice`) and a data packet on topic `vora.turn`.

The same turn is also a `turn.completed` lifecycle event. After `POST /internal/calls/start` the worker appends `call.created`, then `call.answered`, one `turn.completed` per spoken turn, and `call.ended` (`recording_key` null until egress exists). `call.ringing` is published only when a SIP participant's `sip.callStatus` is `ringing`. Each body is the contracts JSON, validated with `parse_lifecycle_event`, and written to Redis streams `calls:events` and `calls:events:{tenant_id}` in the stream field `data`. `REDIS_URL` is the same value as the API task (`module.data.redis_url`). The dev agent task definition sets it, and `deploy-dev.sh` copies it from the API task when it swaps the image, because the ECS service ignores task-definition drift. If it is unset, or Redis errors, the worker logs that and the call continues.

The image build context is the repo root: `docker build -f voice/agent/Dockerfile .`
