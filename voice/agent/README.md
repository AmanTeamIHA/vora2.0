# Voice worker

LiveKit Agents process. Sarvam supplies Saaras STT, the `sarvam-105b-conversations` LLM, and Bulbul TTS. The worker reads the deployed agent version from `POST /internal/calls/start` on the private API (`VORA_API_INTERNAL_URL`, default `http://api.vora2.local:8000`) with the `x-vora-internal` header. It does not call the public load balancer.

On each call it also reads `GET /internal/integrations/sarvam`. That response is the Sarvam API key saved under Admin → Global Settings → Integrations, plus the STT, TTS, and LLM model ids. `SARVAM_API_KEY` in the environment is used only when that setting is empty or the private API cannot be reached. The worker does not need `vora2/dev/sarvam` in Secrets Manager.

Per-turn latency is one CloudWatch EMF line on stdout (`Vora/Voice`) and a data packet on topic `vora.turn`.
