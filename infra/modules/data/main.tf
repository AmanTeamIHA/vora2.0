resource "random_password" "master" {
  length  = 32
  special = false
}

resource "random_password" "app" {
  length  = 32
  special = false
}

resource "random_password" "admin" {
  length  = 32
  special = false
}

resource "random_password" "jwt" {
  length  = 48
  special = false
}

resource "random_password" "internal" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "dev" {
  name       = "vora2-dev"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "vora2-dev"
  }
}

resource "aws_db_instance" "dev" {
  identifier     = "vora2-dev"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "vora"
  username = "vora"
  password = random_password.master.result

  db_subnet_group_name   = aws_db_subnet_group.dev.name
  vpc_security_group_ids = [var.db_sg_id]
  publicly_accessible    = false
  multi_az               = false

  backup_retention_period = 1
  deletion_protection     = true
  skip_final_snapshot     = true
  copy_tags_to_snapshot   = true
  apply_immediately       = true

  tags = {
    Name = "vora2-dev"
  }
}

resource "aws_elasticache_subnet_group" "dev" {
  name       = "vora2-dev"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "vora2-dev"
  }
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "vora2-dev"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.dev.name
  security_group_ids   = [var.redis_sg_id]

  tags = {
    Name = "vora2-dev"
  }
}

resource "aws_secretsmanager_secret" "master" {
  name = "vora2/dev/db-master"
}

resource "aws_secretsmanager_secret" "app" {
  name = "vora2/dev/db-app"
}

resource "aws_secretsmanager_secret" "admin" {
  name = "vora2/dev/db-admin"
}

resource "aws_secretsmanager_secret" "jwt" {
  name = "vora2/dev/jwt"
}

resource "aws_secretsmanager_secret" "internal" {
  name = "vora2/dev/internal-auth"
}

resource "aws_secretsmanager_secret" "owner" {
  name = "vora2/dev/owner"
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id = aws_secretsmanager_secret.master.id
  secret_string = jsonencode({
    username = "vora"
    password = random_password.master.result
    url      = "postgresql+psycopg://vora:${random_password.master.result}@${aws_db_instance.dev.address}:5432/vora"
  })
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    username = "vora_app"
    password = random_password.app.result
    url      = "postgresql+psycopg://vora_app:${random_password.app.result}@${aws_db_instance.dev.address}:5432/vora"
  })
}

resource "aws_secretsmanager_secret_version" "admin" {
  secret_id = aws_secretsmanager_secret.admin.id
  secret_string = jsonencode({
    username = "vora_admin"
    password = random_password.admin.result
    url      = "postgresql+psycopg://vora_admin:${random_password.admin.result}@${aws_db_instance.dev.address}:5432/vora"
  })
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = random_password.jwt.result
}

resource "aws_secretsmanager_secret_version" "internal" {
  secret_id     = aws_secretsmanager_secret.internal.id
  secret_string = random_password.internal.result
}

resource "aws_secretsmanager_secret_version" "owner" {
  secret_id = aws_secretsmanager_secret.owner.id
  secret_string = jsonencode({
    OWNER_EMAIL    = ""
    OWNER_PASSWORD = ""
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
