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
