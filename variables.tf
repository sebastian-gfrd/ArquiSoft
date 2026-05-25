# variables.tf
# Declaración de variables de configuración para el ecosistema BITE.co

variable "aws_region" {
  type        = string
  description = "Región de AWS donde se desplegará la infraestructura."
  default     = "us-east-1"
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN del certificado SSL/TLS en AWS Certificate Manager (ACM) para el balanceador ALB."
  default     = "arn:aws:acm:us-east-1:123456789012:certificate/example-cert-id"
}

variable "auth0_domain" {
  type        = string
  description = "Dominio de Auth0 para la integración de seguridad e identidad OIDC."
  default     = "dev-example.auth0.com"
}

variable "auth0_client_id" {
  type        = string
  description = "Identificador de Cliente (Client ID) de Auth0 para el balanceador ALB."
  default     = "auth0-client-id-placeholder"
}

variable "auth0_client_secret" {
  type        = string
  description = "Secreto del Cliente (Client Secret) de Auth0 para el balanceador ALB."
  sensitive   = true
  default     = "auth0-client-secret-placeholder"
}
