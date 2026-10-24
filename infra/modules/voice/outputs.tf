output "livekit_public_ip" {
  description = "Elastic IP. Point livekit-dev at this address in Cloudflare, DNS only."
  value       = aws_eip.livekit.public_ip
}

output "instance_id" {
  value = aws_instance.livekit.id
}

output "security_group_id" {
  value = aws_security_group.livekit.id
}

output "recordings_bucket" {
  value = aws_s3_bucket.recordings.bucket
}

output "livekit_secret_arn" {
  description = "Secret ARN only. The API key and secret are not outputs."
  value       = aws_secretsmanager_secret.livekit.arn
}

output "sip_trunk_cidr_count" {
  description = "Zero means SIP signalling and RTP are closed."
  value       = length(var.sip_trunk_cidrs)
}
