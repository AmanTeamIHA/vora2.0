locals {
  api_secrets = [
    { name = "DATABASE_URL", valueFrom = "${var.secret_arns.master}:url::" },
    { name = "APP_DATABASE_URL", valueFrom = "${var.secret_arns.app}:url::" },
    { name = "ADMIN_DATABASE_URL", valueFrom = "${var.secret_arns.admin}:url::" },
    { name = "JWT_SECRET", valueFrom = var.secret_arns.jwt },
    { name = "INTERNAL_AUTH_SECRET", valueFrom = var.secret_arns.internal },
    { name = "LIVEKIT_URL", valueFrom = "${var.livekit_secret_arn}:url::" },
    { name = "LIVEKIT_API_KEY", valueFrom = "${var.livekit_secret_arn}:api_key::" },
    { name = "LIVEKIT_API_SECRET", valueFrom = "${var.livekit_secret_arn}:api_secret::" },
  ]
  ecr_keep_10 = {
    rulePriority = 1
    description  = "Keep the last 10 images"
    selection = {
      tagStatus   = "any"
      countType   = "imageCountMoreThan"
      countNumber = 10
    }
    action = { type = "expire" }
  }
}

resource "aws_ecr_repository" "api" {
  name                 = "vora2-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_repository" "web" {
  name                 = "vora2-web"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy     = jsonencode({ rules = [local.ecr_keep_10] })
}

resource "aws_ecr_lifecycle_policy" "web" {
  repository = aws_ecr_repository.web.name
  policy     = jsonencode({ rules = [local.ecr_keep_10] })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/vora2/dev/api"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "web" {
  name              = "/vora2/dev/web"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/vora2/dev/migrate"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "owner" {
  name              = "/vora2/dev/bootstrap-owner"
  retention_in_days = 14
}

data "aws_iam_policy_document" "ecs_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exec" {
  name                 = "vora2-ecs-exec"
  assume_role_policy   = data.aws_iam_policy_document.ecs_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role" "api" {
  name                 = "vora2-api-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role" "web" {
  name                 = "vora2-web-task"
  assume_role_policy   = data.aws_iam_policy_document.ecs_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

data "aws_iam_policy_document" "exec_logs_and_secrets" {
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
    resources = [aws_ecr_repository.api.arn, aws_ecr_repository.web.arn]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "${aws_cloudwatch_log_group.api.arn}:*",
      "${aws_cloudwatch_log_group.web.arn}:*",
      "${aws_cloudwatch_log_group.migrate.arn}:*",
      "${aws_cloudwatch_log_group.owner.arn}:*",
      "${aws_cloudwatch_log_group.seed.arn}:*",
    ]
  }

  statement {
    sid     = "Secrets"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      var.secret_arns.master,
      var.secret_arns.app,
      var.secret_arns.admin,
      var.secret_arns.jwt,
      var.secret_arns.internal,
      var.secret_arns.owner,
      var.livekit_secret_arn,
    ]
  }
}

resource "aws_iam_role_policy" "exec" {
  name   = "vora2-ecs-exec"
  role   = aws_iam_role.exec.id
  policy = data.aws_iam_policy_document.exec_logs_and_secrets.json
}

resource "aws_ecs_cluster" "dev" {
  name = "vora2-dev"
}

resource "aws_ecs_task_definition" "api" {
  family                   = "vora2-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${aws_ecr_repository.api.repository_url}:bootstrap"
    essential = true
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    command = ["uv", "run", "--no-dev", "uvicorn", "vora_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    environment = [
      { name = "APP_ENV", value = "dev" },
      { name = "CORS_ORIGINS", value = "https://${var.domain}" },
      { name = "REDIS_URL", value = var.redis_url },
    ]
    secrets = local.api_secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 40
    }
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "vora2-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.web.arn

  container_definitions = jsonencode([{
    name      = "web"
    image     = "${aws_ecr_repository.web.repository_url}:bootstrap"
    essential = true
    portMappings = [{
      containerPort = 3000
      protocol      = "tcp"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.web.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "web"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1:3000/admin/login || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 40
    }
  }])
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "vora2-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn

  container_definitions = jsonencode([{
    name      = "migrate"
    image     = "${aws_ecr_repository.api.repository_url}:bootstrap"
    essential = true
    command   = ["uv", "run", "--no-dev", "alembic", "upgrade", "head"]
    environment = [
      { name = "APP_ENV", value = "dev" },
    ]
    secrets = concat(local.api_secrets, [
      { name = "VORA_APP_PASSWORD", valueFrom = "${var.secret_arns.app}:password::" },
      { name = "VORA_ADMIN_PASSWORD", valueFrom = "${var.secret_arns.admin}:password::" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.migrate.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "migrate"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "owner" {
  family                   = "vora2-bootstrap-owner"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.api.arn

  container_definitions = jsonencode([{
    name      = "owner"
    image     = "${aws_ecr_repository.api.repository_url}:bootstrap"
    essential = true
    command   = ["uv", "run", "--no-dev", "python", "-m", "vora_api.bootstrap_owner"]
    environment = [
      { name = "APP_ENV", value = "dev" },
    ]
    secrets = concat(local.api_secrets, [
      { name = "OWNER_EMAIL", valueFrom = "${var.secret_arns.owner}:OWNER_EMAIL::" },
      { name = "OWNER_PASSWORD", valueFrom = "${var.secret_arns.owner}:OWNER_PASSWORD::" },
    ])
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.owner.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "owner"
      }
    }
  }])
}

resource "aws_lb" "dev" {
  name                       = "vora2-dev"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [var.alb_sg_id]
  subnets                    = var.public_subnet_ids
  ip_address_type            = "ipv4"
  drop_invalid_header_fields = true

  tags = {
    Name = "vora2-dev"
  }
}

resource "aws_lb_target_group" "api" {
  name        = "vora2-dev-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path                = "/healthz"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_lb_target_group" "web" {
  name        = "vora2-dev-web"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path                = "/admin/login"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}

resource "aws_acm_certificate" "dev" {
  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_acm_certificate_validation" "dev" {
  certificate_arn = aws_acm_certificate.dev.arn
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.dev.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.dev.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.dev.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "internal" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 1

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "application/json"
      message_body = "{\"detail\":\"Not found\"}"
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = ["/internal", "/internal/*"]
    }
  }
}

resource "aws_lb_listener_rule" "api_internal" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 2

  action {
    type = "fixed-response"

    fixed_response {
      content_type = "application/json"
      message_body = "{\"detail\":\"Not found\"}"
      status_code  = "404"
    }
  }

  condition {
    path_pattern {
      values = ["/api/internal", "/api/internal/*"]
    }
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}

resource "aws_ecs_service" "api" {
  name            = "vora2-api"
  cluster         = aws_ecs_cluster.dev.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.api_sg_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}

resource "aws_ecs_service" "web" {
  name            = "vora2-web"
  cluster         = aws_ecs_cluster.dev.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = 0
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.web_sg_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.https]

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }
}
