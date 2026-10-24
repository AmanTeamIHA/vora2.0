output "github_oidc_provider_arn" {
  description = "Existing account OIDC provider. This stack does not create or manage it."
  value       = data.aws_iam_openid_connect_provider.github.arn
}

output "alb_dns_name" {
  description = "CNAME target for playground-dev.hellovora.ai. Proxy it in Cloudflare."
  value       = module.edge.alb_dns_name
}

output "acm_validation_records" {
  description = "Add these in Cloudflare as DNS-only before the certificate can issue."
  value       = module.edge.acm_validation_records
}

output "cluster_name" {
  value = module.edge.cluster_name
}

output "livekit_public_ip" {
  description = "A record for livekit-dev.hellovora.ai. Cloudflare DNS only, grey cloud."
  value       = module.voice.livekit_public_ip
}

output "livekit_sip_trunk_cidr_count" {
  description = "Zero means SIP 5060 and RTP 10000-20000 have no ingress."
  value       = module.voice.sip_trunk_cidr_count
}
