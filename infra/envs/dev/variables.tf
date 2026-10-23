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
