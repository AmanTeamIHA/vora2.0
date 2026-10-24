# LiveKit on dev EC2

Pinned images, rendered on the instance. Terraform owns the host (`infra/modules/voice`). API key and secret are generated into Secrets Manager `vora2/dev/livekit` and read at boot. They are not in this directory.

| Process | Image |
|---|---|
| livekit-server | `livekit/livekit-server:v1.13.10` |
| livekit-sip | `livekit/sip:v1.21.0` |
| livekit-egress | `livekit/egress:v1.15.0` |
| Caddy | `caddy:2.11.7` |

Caddy terminates TLS for `livekit-dev.hellovora.ai` and proxies to LiveKit on `127.0.0.1:7880`. Certificates are Let's Encrypt HTTP-01, so port 80 stays open for ACME only. Media is not proxied: WebRTC uses TCP 7881 and UDP 50000-60000. SIP signalling is 5060 TCP/UDP and RTP is UDP 10000-20000, and those ports stay closed until `sip_trunk_cidrs` is set.

Redis is the existing `vora2-dev` ElastiCache node. There is no Redis container.

Egress writes to `vora2-dev-recordings` with the instance role. Object keys must be `tenants/{tenant_id}/calls/{call_id}`. The role cannot write anywhere else.

Codecs are PCMA and PCMU. DTMF stays RFC 2833 (`telephone-event`). `audio_dtmf` is off so tones are not converted to in-band audio.

`rtc.use_external_ip` and `rtc.node_ip` are both set. On EC2 the STUN self-check cannot reach the instance's own Elastic IP, so `skip_external_ip_validation` is set or LiveKit drops the public candidate. SIP cannot set `use_external_ip` and `nat_1_to_1_ip` together; it announces the Elastic IP with `nat_1_to_1_ip`.

## DNS (Cloudflare, not Terraform)

Grey cloud. Cloudflare cannot proxy UDP or WebRTC.

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `livekit-dev` | `livekit_public_ip` output | DNS only |

Zone `hellovora.ai`. The certificate will not issue until this record exists. Caddy retries.

## After apply

```bash
aws secretsmanager get-secret-value \
  --secret-id vora2/dev/livekit \
  --region ap-south-1 \
  --profile vora2-dev \
  --query SecretString \
  --output text

lk room list --url wss://livekit-dev.hellovora.ai --api-key <api_key> --api-secret <api_secret>
```

Do not paste the secret into git, a PR, or chat.

A config change replaces the instance. The Elastic IP stays. The nightly start at 08:00 IST re-reads the secret. To reload sooner, from an SSM session: `sudo systemctl restart vora2-livekit`.

## Cost (dev, list price)

On-demand `c7i.xlarge` in ap-south-1 is $0.1785/hour. The schedule runs it 15.5 hours/day (08:00–23:30 IST). A 730-hour month:

| Item | Monthly |
|---|---|
| EC2 15.5/24 × 730 × $0.1785 | $84.16 |
| gp3 30 GB × $0.0912 | $2.74 |
| Elastic IP while stopped, 8.5/24 × 730 × $0.005 | $1.29 |
| Logs and an empty recordings bucket | about $1 |
| **Incremental total** | **about $89** |

Running the same instance all month, with no idle-IP charge, is about $133. The schedule is on by default (`livekit_nightly_stop_enabled`).
