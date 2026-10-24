# Voice worker. The Sarvam API key is saved in Global Settings, not in this task.
# SARVAM_API_KEY in the environment is an optional fallback only.
#
# The worker calls the API on port 8080 of the existing vora2-dev load balancer.
# That listener is open only to this security group. vora2-boundary denies
# route53:CreateHostedZone, so a Cloud Map private DNS namespace cannot be created.
# Attaching another load balancer would replace the API service (load_balancer is
# ForceNew) and drop playground. The public 443 listener still returns 404 for /internal.

resource "aws_ecr_repository" "agent" {
  name                 = "vora2-agent"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name
  policy     = jsonencode({ rules = [local.ecr_keep_10] })
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/vora2/dev/agent"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "seed" {
  name              = "/vora2/dev/seed-demo"
  retention_in_days = 14
}

resource "aws_security_group" "agent" {
  name        = "vora2-agent"
  description = "Voice worker. No inbound. Private API, Sarvam, and LiveKit only."
  vpc_id      = var.vpc_id

  tags = {
    Name = "vora2-agent"
  }
}

resource "aws_vpc_security_group_egress_rule" "agent_https" {
  security_group_id = aws_security_group.agent.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Sarvam, LiveKit signalling, ECR, logs, secrets"
}

resource "aws_vpc_security_group_egress_rule" "agent_livekit_tcp" {
  security_group_id = aws_security_group.agent.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 7881
  to_port           = 7881
  description       = "LiveKit ICE over TCP"
}

resource "aws_vpc_security_group_egress_rule" "agent_livekit_udp" {
  security_group_id = aws_security_group.agent.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "udp"
  from_port         = 50000
  to_port           = 60000
  description       = "LiveKit media"
}

resource "aws_vpc_security_group_egress_rule" "agent_api" {
  security_group_id            = aws_security_group.agent.id
  referenced_security_group_id = var.api_sg_id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "Direct path to API tasks. The worker uses the private listener."
}

resource "aws_vpc_security_group_egress_rule" "agent_alb_private" {
  security_group_id            = aws_security_group.agent.id
  referenced_security_group_id = var.alb_sg_id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "Private API listener on the dev load balancer"
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_agent" {
  security_group_id            = var.alb_sg_id
  referenced_security_group_id = aws_security_group.agent.id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "Voice worker only. Not Cloudflare and not the public internet."
}

resource "aws_vpc_security_group_ingress_rule" "api_from_agent" {
  security_group_id            = var.api_sg_id
  referenced_security_group_id = aws_security_group.agent.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "Voice worker on the private network"
}

resource "aws_iam_role" "agent_exec" {
  name                 = "vora2-agent-exec"
  assume_role_policy   = data.aws_iam_policy_document.ecs_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role" "agent_task" {
  name                 = "vora2-agent-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

data "aws_iam_policy_document" "agent_exec" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.agent.arn]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.agent.arn}:*"]
  }

  statement {
    sid     = "Secrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      var.livekit_secret_arn,
      var.secret_arns.internal,
    ]
  }
}

data "aws_iam_policy_document" "agent_task" {
  statement {
    sid     = "ReadVoiceSecrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      var.livekit_secret_arn,
      var.secret_arns.internal,
    ]
  }
}

resource "aws_iam_role_policy" "agent_exec" {
  name   = "vora2-agent-exec"
  role   = aws_iam_role.agent_exec.id
  policy = data.aws_iam_policy_document.agent_exec.json
}

resource "aws_iam_role_policy" "agent_task" {
  name   = "vora2-agent-task"
  role   = aws_iam_role.agent_task.id
  policy = data.aws_iam_policy_document.agent_task.json
}

resource "aws_ecs_task_definition" "agent" {
  family                   = "vora2-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.agent_exec.arn
  task_role_arn            = aws_iam_role.agent_task.arn

  container_definitions = jsonencode([{
    name      = "agent"
    image     = "${aws_ecr_repository.agent.repository_url}:bootstrap"
    essential = true
    environment = [
      { name = "VORA_API_INTERNAL_URL", value = "http://${aws_lb.dev.dns_name}:8080" },
    ]
    secrets = [
      { name = "LIVEKIT_URL", valueFrom = "${var.livekit_secret_arn}:url::" },
      { name = "LIVEKIT_API_KEY", valueFrom = "${var.livekit_secret_arn}:api_key::" },
      { name = "LIVEKIT_API_SECRET", valueFrom = "${var.livekit_secret_arn}:api_secret::" },
      { name = "INTERNAL_AUTH_SECRET", valueFrom = var.secret_arns.internal },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.agent.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "agent"
      }
    }
  }])
}

resource "aws_ecs_service" "agent" {
  name            = "vora2-agent"
  cluster         = aws_ecs_cluster.dev.id
  task_definition = aws_ecs_task_definition.agent.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.agent.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [task_definition]
  }
}

resource "aws_ecs_task_definition" "seed_demo" {
  family                   = "vora2-seed-demo"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn

  container_definitions = jsonencode([{
    name      = "seed"
    image     = "${aws_ecr_repository.api.repository_url}:bootstrap"
    essential = true
    command   = ["uv", "run", "--no-dev", "python", "-m", "vora_api.seed_demo"]
    environment = [
      { name = "APP_ENV", value = "dev" },
    ]
    secrets = local.api_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.seed.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "seed"
      }
    }
  }])
}
