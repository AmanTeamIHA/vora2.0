provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = "vora2"
      env     = "dev"
    }
  }
}
