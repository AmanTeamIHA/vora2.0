variable "domain" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_sg_id" {
  type = string
}

variable "api_sg_id" {
  type = string
}

variable "web_sg_id" {
  type = string
}

variable "permissions_boundary_arn" {
  type = string
}

variable "redis_url" {
  type = string
}

variable "secret_arns" {
  type = map(string)
}

variable "livekit_secret_arn" {
  type = string
}
