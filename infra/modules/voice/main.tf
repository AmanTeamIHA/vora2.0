data "aws_caller_identity" "current" {}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

resource "random_string" "api_key" {
  length  = 16
  special = false
  upper   = false
}

resource "random_password" "api_secret" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "livekit" {
  name = "vora2/dev/livekit"
}

resource "aws_secretsmanager_secret_version" "livekit" {
  secret_id = aws_secretsmanager_secret.livekit.id
  secret_string = jsonencode({
    api_key    = "dev${random_string.api_key.result}"
    api_secret = random_password.api_secret.result
    url        = "wss://${var.hostname}"
  })
}

resource "aws_s3_bucket" "recordings" {
  bucket = "vora2-dev-recordings"

  tags = {
    Name = "vora2-dev-recordings"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "recordings" {
  bucket                  = aws_s3_bucket.recordings.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "recordings" {
  bucket     = aws_s3_bucket.recordings.id
  depends_on = [aws_s3_bucket_versioning.recordings]

  rule {
    id     = "expire-90-days"
    status = "Enabled"

    filter {}

    expiration {
      days = 90
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "recordings" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.recordings.arn,
      "${aws_s3_bucket.recordings.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyOutsideTenantCalls"
    effect = "Deny"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
    ]
    not_resources = ["${aws_s3_bucket.recordings.arn}/tenants/*/calls/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  policy = data.aws_iam_policy_document.recordings.json

  depends_on = [aws_s3_bucket_public_access_block.recordings]
}

resource "aws_cloudwatch_log_group" "livekit" {
  name              = "/vora2/dev/livekit"
  retention_in_days = 14
}

resource "aws_security_group" "livekit" {
  name        = "vora2-dev-livekit"
  description = "LiveKit API, WebRTC, and trunk-only SIP"
  vpc_id      = var.vpc_id

  tags = {
    Name = "vora2-dev-livekit"
  }
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.livekit.id
  description       = "LiveKit API and WebSocket via Caddy"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "acme" {
  security_group_id = aws_security_group.livekit.id
  description       = "Lets Encrypt HTTP-01"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "webrtc_tcp" {
  security_group_id = aws_security_group.livekit.id
  description       = "WebRTC ICE over TCP"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 7881
  to_port           = 7881
}

resource "aws_vpc_security_group_ingress_rule" "webrtc_udp" {
  security_group_id = aws_security_group.livekit.id
  description       = "WebRTC media"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "udp"
  from_port         = 50000
  to_port           = 60000
}

resource "aws_vpc_security_group_ingress_rule" "sip_tcp" {
  for_each = toset(var.sip_trunk_cidrs)

  security_group_id = aws_security_group.livekit.id
  description       = "SIP signalling from trunk"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 5060
  to_port           = 5060
}

resource "aws_vpc_security_group_ingress_rule" "sip_udp" {
  for_each = toset(var.sip_trunk_cidrs)

  security_group_id = aws_security_group.livekit.id
  description       = "SIP signalling from trunk"
  cidr_ipv4         = each.value
  ip_protocol       = "udp"
  from_port         = 5060
  to_port           = 5060
}

resource "aws_vpc_security_group_ingress_rule" "rtp" {
  for_each = toset(var.sip_trunk_cidrs)

  security_group_id = aws_security_group.livekit.id
  description       = "SIP RTP from trunk"
  cidr_ipv4         = each.value
  ip_protocol       = "udp"
  from_port         = 10000
  to_port           = 20000
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.livekit.id
  description       = "WebRTC and SIP peers use dynamic ports"
  ip_protocol       = "-1"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "redis" {
  security_group_id            = var.redis_sg_id
  description                  = "LiveKit to ElastiCache"
  referenced_security_group_id = aws_security_group.livekit.id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

data "aws_iam_policy_document" "ec2_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "livekit" {
  name                 = "vora2-livekit"
  assume_role_policy   = data.aws_iam_policy_document.ec2_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.livekit.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "livekit" {
  statement {
    sid       = "ReadLivekitSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.livekit.arn]
  }

  statement {
    sid = "Recordings"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.recordings.arn}/tenants/*/calls/*"]
  }

  statement {
    sid       = "RecordingsList"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.recordings.arn]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = [
      aws_cloudwatch_log_group.livekit.arn,
      "${aws_cloudwatch_log_group.livekit.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "livekit" {
  name   = "vora2-livekit"
  role   = aws_iam_role.livekit.id
  policy = data.aws_iam_policy_document.livekit.json
}

resource "aws_iam_instance_profile" "livekit" {
  name = "vora2-livekit"
  role = aws_iam_role.livekit.name
}

resource "aws_eip" "livekit" {
  domain = "vpc"

  tags = {
    Name = "vora2-dev-livekit"
  }
}

resource "aws_instance" "livekit" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = var.public_subnet_id
  vpc_security_group_ids      = [aws_security_group.livekit.id]
  iam_instance_profile        = aws_iam_instance_profile.livekit.name
  associate_public_ip_address = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    livekit_yaml      = file("${path.module}/../../../voice/livekit/livekit.yaml")
    sip_yaml          = file("${path.module}/../../../voice/livekit/sip.yaml")
    egress_yaml       = file("${path.module}/../../../voice/livekit/egress.yaml")
    caddyfile         = file("${path.module}/../../../voice/livekit/Caddyfile")
    compose_yaml      = file("${path.module}/../../../voice/livekit/docker-compose.yml")
    render_py         = file("${path.module}/../../../voice/livekit/render.py")
    node_ip           = aws_eip.livekit.public_ip
    redis_address     = var.redis_address
    hostname          = var.hostname
    recordings_bucket = aws_s3_bucket.recordings.bucket
  })
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true

    tags = {
      Name = "vora2-dev-livekit"
    }
  }

  tags = {
    Name = "vora2-dev-livekit"
  }

  depends_on = [
    aws_secretsmanager_secret_version.livekit,
    aws_cloudwatch_log_group.livekit,
    aws_iam_role_policy.livekit,
    aws_iam_role_policy_attachment.ssm,
  ]

  lifecycle {
    ignore_changes = [ami]

    precondition {
      condition     = data.aws_caller_identity.current.account_id == "585008088038"
      error_message = "Refusing to plan LiveKit outside account 585008088038."
    }
  }
}

resource "aws_eip_association" "livekit" {
  allocation_id = aws_eip.livekit.id
  instance_id   = aws_instance.livekit.id
}

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count = var.nightly_stop_enabled ? 1 : 0

  name                 = "vora2-livekit-scheduler"
  assume_role_policy   = data.aws_iam_policy_document.scheduler_trust.json
  permissions_boundary = var.permissions_boundary_arn
}

data "aws_iam_policy_document" "scheduler" {
  count = var.nightly_stop_enabled ? 1 : 0

  statement {
    sid = "StartStopLivekit"
    actions = [
      "ec2:StartInstances",
      "ec2:StopInstances",
    ]
    resources = [aws_instance.livekit.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  count = var.nightly_stop_enabled ? 1 : 0

  name   = "vora2-livekit-scheduler"
  role   = aws_iam_role.scheduler[0].id
  policy = data.aws_iam_policy_document.scheduler[0].json
}

resource "aws_scheduler_schedule" "stop" {
  count = var.nightly_stop_enabled ? 1 : 0

  name                         = "vora2-dev-livekit-stop"
  schedule_expression          = var.stop_cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.scheduler[0].arn
    input = jsonencode({
      InstanceIds = [aws_instance.livekit.id]
    })
  }
}

resource "aws_scheduler_schedule" "start" {
  count = var.nightly_stop_enabled ? 1 : 0

  name                         = "vora2-dev-livekit-start"
  schedule_expression          = var.start_cron
  schedule_expression_timezone = var.schedule_timezone

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.scheduler[0].arn
    input = jsonencode({
      InstanceIds = [aws_instance.livekit.id]
    })
  }
}
