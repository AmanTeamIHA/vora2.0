# infra/ — dev only

Terraform for the dev console in ap-south-1. Account 585008088038, shared with CallAtlas. This stack does not create the state bucket, the permission boundary, the deployer role, the GitHub role, or the GitHub OIDC provider. Those already exist. See the AWS bootstrap note.

- State: `s3://vora2-tfstate-585008088038-aps1/dev/terraform.tfstate` with `use_lockfile` (Terraform >= 1.10). No DynamoDB lock.
- GitHub Actions assumes `arn:aws:iam::585008088038:role/vora2-github-dev`. Jobs have no `environment:` key.
- Local plans use `AWS_PROFILE=vora2-dev`. Do not use the `vora` profile directly.
- VPC `10.20.0.0/16`. One NAT. RDS `db.t4g.micro` single-AZ. Redis `cache.t4g.micro`. Two Fargate tasks at 0.5 vCPU / 1 GB.
- Every IAM role this stack creates is named `vora2-*` and carries `vora2-boundary`.
- Secrets are `vora2/dev/*`. The load balancer accepts Cloudflare IPv4 on 80 and 443 only. `/internal` and `/api/internal` return 404 at the load balancer.
- Hostname `playground-dev.hellovora.ai`. DNS and Cloudflare Access are outside AWS. Apply waits until the ACM validation CNAME is in Cloudflare.

Do not apply from a laptop. `infra.yml` plans on a pull request and applies on merge to main, after review.
