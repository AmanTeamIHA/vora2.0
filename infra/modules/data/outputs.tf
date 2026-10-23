output "redis_url" {
  value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
}

output "secret_arns" {
  value = {
    master   = aws_secretsmanager_secret.master.arn
    app      = aws_secretsmanager_secret.app.arn
    admin    = aws_secretsmanager_secret.admin.arn
    jwt      = aws_secretsmanager_secret.jwt.arn
    internal = aws_secretsmanager_secret.internal.arn
    owner    = aws_secretsmanager_secret.owner.arn
  }
}
