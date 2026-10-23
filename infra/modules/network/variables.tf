variable "cidr" {
  type = string
}

variable "cloudflare_ipv4" {
  description = "Cloudflare edge ranges allowed to reach the load balancer."
  type        = list(string)
}
