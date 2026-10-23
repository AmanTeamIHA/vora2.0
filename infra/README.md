# infra/ — Foundation & Infra

Terraform + CI for the single AWS account in ap-south-1 (Mumbai).

- dev and prod VPCs (private subnets; only LiveKit SIP/RTP and the web/API LB are public)
- RDS Postgres (Multi-AZ, RLS), ElastiCache Redis, S3 Mumbai (per-tenant prefixes)
- ECS for API, agent workers, Temporal workers; plain EC2 for LiveKit
- GitHub Actions: build → deploy dev → manual promote prod
- CloudWatch + Grafana; Secrets Manager / SSM (no secrets in code)

Linear project: Foundation & Infra. No multi-region code.
