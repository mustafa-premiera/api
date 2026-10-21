variable "aws_profile" {
  type    = string
  default = "manara-free"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "manara-todo"
}

variable "alert_email" {
  type        = string
  description = "Email address that receives budget alerts."
}

variable "enable_waf" {
  type    = bool
  default = true
}

variable "enable_api_cache" {
  type    = bool
  default = true
}

variable "api_cache_ttl_seconds" {
  type    = number
  default = 60
}

variable "geo_block_countries" {
  type    = list(string)
  default = ["KP", "CU", "IR", "SY"]
}

variable "waf_rate_limit" {
  type    = number
  default = 300
}
