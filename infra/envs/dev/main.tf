data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "http" "cloudflare_ipv4" {
  url = "https://www.cloudflare.com/ips-v4"

  request_headers = {
    Accept = "text/plain"
  }
}

locals {
  cloudflare_ipv4 = [
    for cidr in split("\n", trimspace(data.http.cloudflare_ipv4.response_body)) :
    trimspace(cidr) if trimspace(cidr) != ""
  ]
}

module "network" {
  source = "../../modules/network"

  cidr            = var.vpc_cidr
  cloudflare_ipv4 = local.cloudflare_ipv4
}

module "data" {
  source = "../../modules/data"

  private_subnet_ids = module.network.private_subnet_ids
  db_sg_id           = module.network.db_sg_id
  redis_sg_id        = module.network.redis_sg_id
}

module "edge" {
  source = "../../modules/edge"

  domain                   = var.domain
  vpc_id                   = module.network.vpc_id
  public_subnet_ids        = module.network.public_subnet_ids
  private_subnet_ids       = module.network.private_subnet_ids
  alb_sg_id                = module.network.alb_sg_id
  api_sg_id                = module.network.api_sg_id
  web_sg_id                = module.network.web_sg_id
  permissions_boundary_arn = var.permissions_boundary_arn
  redis_url                = module.data.redis_url
  secret_arns              = module.data.secret_arns
  livekit_secret_arn       = module.voice.livekit_secret_arn
}

module "voice" {
  source = "../../modules/voice"

  vpc_id                   = module.network.vpc_id
  public_subnet_id         = module.network.public_subnet_ids[0]
  redis_sg_id              = module.network.redis_sg_id
  redis_address            = module.data.redis_address
  permissions_boundary_arn = var.permissions_boundary_arn
  hostname                 = var.livekit_hostname
  sip_trunk_cidrs          = var.sip_trunk_cidrs
  nightly_stop_enabled     = var.livekit_nightly_stop_enabled
  stop_cron                = var.livekit_stop_cron
  start_cron               = var.livekit_start_cron
  schedule_timezone        = var.livekit_schedule_timezone
}
