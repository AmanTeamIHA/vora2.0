variable "vpc_id" {
  type = string
}

variable "public_subnet_id" {
  description = "Public subnet for the LiveKit instance. It has an Elastic IP."
  type        = string
}

variable "redis_sg_id" {
  description = "ElastiCache security group. LiveKit is added as a Redis client."
  type        = string
}

variable "redis_address" {
  description = "ElastiCache host:port. LiveKit does not run its own Redis."
  type        = string
}

variable "permissions_boundary_arn" {
  type = string
}

variable "hostname" {
  description = "TLS name for the LiveKit API. DNS is created in Cloudflare, not here."
  type        = string
}

variable "sip_trunk_cidrs" {
  description = "Trunk signalling and media sources. Empty closes 5060 and RTP 10000-20000."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for cidr in var.sip_trunk_cidrs : can(cidrhost(cidr, 0))
    ])
    error_message = "sip_trunk_cidrs must be IPv4 CIDR blocks."
  }
}

variable "nightly_stop_enabled" {
  description = "Stop the instance overnight and start it in the morning."
  type        = bool
  default     = true
}

variable "stop_cron" {
  description = "EventBridge Scheduler cron, evaluated in schedule_timezone."
  type        = string
  default     = "cron(30 23 * * ? *)"
}

variable "start_cron" {
  description = "EventBridge Scheduler cron, evaluated in schedule_timezone."
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "schedule_timezone" {
  type    = string
  default = "Asia/Kolkata"
}

variable "instance_type" {
  type    = string
  default = "c7i.xlarge"
}
