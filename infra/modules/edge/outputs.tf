output "alb_dns_name" {
  value = aws_lb.dev.dns_name
}

output "acm_validation_records" {
  value = [
    for record in aws_acm_certificate.dev.domain_validation_options : {
      name  = record.resource_record_name
      type  = record.resource_record_type
      value = record.resource_record_value
    }
  ]
}

output "cluster_name" {
  value = aws_ecs_cluster.dev.name
}
