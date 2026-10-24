variable "region" {
  description = "AWS region. Vora 2.0 is India only."
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = var.region == "ap-south-1"
    error_message = "Vora 2.0 is India only. Region must be ap-south-1."
  }
}

variable "domain" {
  description = "Dev console hostname. DNS and Cloudflare Access stay outside this account."
  type        = string
  default     = "playground-dev.hellovora.ai"
}

variable "vpc_cidr" {
  description = "Dev VPC. Isolated from other workloads in the shared account."
  type        = string
  default     = "10.20.0.0/16"
}

variable "permissions_boundary_arn" {
  description = "Boundary that every Vora IAM role must carry. Created outside this stack."
  type        = string
  default     = "arn:aws:iam::585008088038:policy/vora2-boundary"
}

variable "livekit_hostname" {
  description = "LiveKit API hostname. The Cloudflare record is not created here."
  type        = string
  default     = "livekit-dev.hellovora.ai"
}

variable "sip_trunk_cidrs" {
  description = "Trunk CIDRs allowed to reach SIP 5060 and RTP 10000-20000. Empty closes both."
  type        = list(string)
  default     = []
}

variable "livekit_nightly_stop_enabled" {
  description = "Stop vora2-dev-livekit overnight and start it in the morning."
  type        = bool
  default     = true
}

variable "livekit_stop_cron" {
  description = "When to stop LiveKit. Default 23:30 IST."
  type        = string
  default     = "cron(30 23 * * ? *)"
}

variable "livekit_start_cron" {
  description = "When to start LiveKit. Default 08:00 IST."
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "livekit_schedule_timezone" {
  type    = string
  default = "Asia/Kolkata"
}
