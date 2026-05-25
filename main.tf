# ==========================================
# PROYECTO: BITE.co - FinOps SaaS (main.tf)
# ==========================================

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ------------------------------------------
# 1. CAPA DE RED (VPC & Subnets) - ASR-04 (Seguridad)
# ------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "bite-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"] # Persistencia y Cómputo (Fargate/Lambda)
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"] # Application Load Balancer

  enable_nat_gateway = true # Permite a las subredes privadas salir a internet (AWS APIs)
}

# ------------------------------------------
# SEGURIDAD (Grupos de Seguridad - Security Groups)
# ------------------------------------------
resource "aws_security_group" "alb_sg" {
  name        = "bite-alb-sg"
  description = "Security Group for the Application Load Balancer"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Allow HTTPS from internet"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "lambda_sg" {
  name        = "bite-lambda-sg"
  description = "Security Group for Lambda Functions"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "rds_proxy_sg" {
  name        = "bite-rds-proxy-sg"
  description = "Security Group for Amazon RDS Proxy"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "Allow traffic from Lambda and Fargate"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ------------------------------------------
# 2. CAPA DE MENSAJERÍA (Asincronía) - ASR-03
# ------------------------------------------
# Dead Letter Queue para reportes fallidos
resource "aws_sqs_queue" "bite_dlq" {
  name = "bite-integration-dlq"
}

# Cola principal consumida por el Celery Worker (MS4)
resource "aws_sqs_queue" "bite_worker_queue" {
  name                       = "bite-integration-queue"
  visibility_timeout_seconds = 900 # 15 minutos (Tiempo máximo de procesamiento analítico)
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.bite_dlq.arn
    maxReceiveCount     = 3
  })
}

# Bus de eventos para Consistencia Eventual
resource "aws_cloudwatch_event_bus" "bite_event_bus" {
  name = "bite-event-bus"
}

# ------------------------------------------
# 3. CAPA DE PERSISTENCIA (Database per Service)
# ------------------------------------------
# Admin DB (PostgreSQL para Django MS1) y Analytics DB
module "aurora_cluster" {
  source = "terraform-aws-modules/rds-aurora/aws"

  name           = "bite-db-cluster"
  engine         = "aurora-postgresql"
  engine_version = "15.4"
  instance_class = "db.r6g.large"
  instances = {
    writer = {} # Usado por MS1 (Admin) y MS4 (Escritura Analítica)
    reader = {} # Usado por MS2 (Lecturas Rápidas CQRS)
  }
  vpc_id               = module.vpc.vpc_id
  db_subnet_group_name = module.vpc.database_subnet_group_name
}

# Amazon RDS Proxy (Protección de Escalabilidad - ASR-06)
resource "aws_db_proxy" "bite_rds_proxy" {
  name                   = "bite-rds-proxy"
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  vpc_subnet_ids         = module.vpc.private_subnets
  vpc_security_group_ids = [aws_security_group.rds_proxy_sg.id]
}

# Caché (Redis para MS1 Sesiones y MS2 Cache-Aside)
resource "aws_elasticache_cluster" "bite_redis" {
  cluster_id           = "bite-redis-cluster"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  subnet_group_name    = module.vpc.elasticache_subnet_group_name
}

# ------------------------------------------
# 4. CAPA DE CÓMPUTO PERSISTENTE (AWS ECS Fargate)
# ------------------------------------------
resource "aws_ecs_cluster" "bite_cluster" {
  name = "bite-ecs-cluster"
}

# Microservicio 1: Django Core
module "ecs_ms1_django" {
  source = "terraform-aws-modules/ecs/aws//modules/service"

  name        = "ms1-django-core"
  cluster_arn = aws_ecs_cluster.bite_cluster.arn
  cpu         = 1024
  memory      = 2048
  # Conexión al ALB para rutas /auth/*
  load_balancer = {
    target_group_arn = aws_lb_target_group.ms1_tg.arn
    container_name   = "django-core"
    container_port   = 8000
  }
}

# Microservicio 4: Celery Worker (Headless)
module "ecs_ms4_worker" {
  source = "terraform-aws-modules/ecs/aws//modules/service"

  name        = "ms4-celery-worker"
  cluster_arn = aws_ecs_cluster.bite_cluster.arn
  cpu         = 2048 # Perfil c5.large simulado en Fargate
  memory      = 4096
  # Sin Load Balancer (Aplicación de fondo)
  
  # Auto-scaling basado en SQS Queue Depth
  autoscaling_min_capacity = 2
  autoscaling_max_capacity = 4
}

# ------------------------------------------
# 5. CAPA DE CÓMPUTO SERVERLESS (AWS Lambda)
# ------------------------------------------
# Microservicio 2: Analytics API
module "lambda_ms2_analytics" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "6.0.0"

  function_name = "ms2-analytics-api"
  handler       = "app.main.handler"
  runtime       = "python3.11"
  vpc_subnet_ids         = module.vpc.private_subnets
  vpc_security_group_ids = [aws_security_group.lambda_sg.id]

  environment_variables = {
    DATABASE_URL = aws_db_proxy.bite_rds_proxy.endpoint # Conexión vía Proxy
    REDIS_URL    = aws_elasticache_cluster.bite_redis.cache_nodes[0].address
  }
}

# Microservicio 3: Cloud Integration Service
module "lambda_ms3_integration" {
  source  = "terraform-aws-modules/lambda/aws"

  function_name = "ms3-integration-api"
  handler       = "app.main.handler"
  runtime       = "python3.11"

  environment_variables = {
    SQS_QUEUE_URL = aws_sqs_queue.bite_worker_queue.url
  }
}

# ------------------------------------------
# 6. CAPA DE PERÍMETRO Y SEGURIDAD (AWS ALB & Auth0)
# ------------------------------------------
resource "aws_lb" "bite_alb" {
  name               = "bite-main-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = module.vpc.public_subnets
}

# Listener principal HTTPS
resource "aws_lb_listener" "https_listener" {
  load_balancer_arn = aws_lb.bite_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = var.acm_certificate_arn # Certificado SSL administrado

  # Acción por defecto: Bloquear tráfico no enrutado (ASR-04)
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "403 Forbidden - BITE.co"
      status_code  = "403"
    }
  }
}

# ------------------------------------------
# GRUPOS DE DESTINO (Target Groups)
# ------------------------------------------
resource "aws_lb_target_group" "ms1_tg" {
  name        = "bite-ms1-target-group"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip" # ECS Fargate requiere target_type = "ip"

  health_check {
    path                = "/health/"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 3
    unhealthy_threshold = 3
    matcher             = "200"
  }
}

resource "aws_lb_target_group" "lambda_ms2_tg" {
  name        = "bite-ms2-target-group"
  target_type = "lambda"
}

resource "aws_lb_target_group" "lambda_ms3_tg" {
  name        = "bite-ms3-target-group"
  target_type = "lambda"
}

# Permisos para que el ALB invoque a Lambdas
resource "aws_lambda_permission" "allow_alb_to_invoke_ms2" {
  statement_id  = "AllowALBToInvokeMS2"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ms2_analytics.lambda_function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.lambda_ms2_tg.arn
}

resource "aws_lambda_permission" "allow_alb_to_invoke_ms3" {
  statement_id  = "AllowALBToInvokeMS3"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_ms3_integration.lambda_function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.lambda_ms3_tg.arn
}

# Asociación de Targets
resource "aws_lb_target_group_attachment" "ms2_attachment" {
  target_group_arn = aws_lb_target_group.lambda_ms2_tg.arn
  target_id        = module.lambda_ms2_analytics.lambda_function_arn
  depends_on       = [aws_lambda_permission.allow_alb_to_invoke_ms2]
}

resource "aws_lb_target_group_attachment" "ms3_attachment" {
  target_group_arn = aws_lb_target_group.lambda_ms3_tg.arn
  target_id        = module.lambda_ms3_integration.lambda_function_arn
  depends_on       = [aws_lambda_permission.allow_alb_to_invoke_ms3]
}

# ------------------------------------------
# 7. REGLAS DE ENRUTAMIENTO Y OIDC (Auth0)
# ------------------------------------------

# Regla 1: Tráfico Administrativo -> MS1 (Django Fargate)
resource "aws_lb_listener_rule" "rule_auth_ms1" {
  listener_arn = aws_lb_listener.https_listener.arn
  priority     = 100

  condition {
    path_pattern {
      values = ["/auth/*"]
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ms1_tg.arn
  }
}

# Regla 2: Tráfico Analítico -> MS2 (FastAPI Lambda) con Auth0
resource "aws_lb_listener_rule" "rule_reports_ms2" {
  listener_arn = aws_lb_listener.https_listener.arn
  priority     = 110

  condition {
    path_pattern {
      values = ["/reports/*"]
    }
  }

  # Interceptor OIDC en el perímetro (Verificación de Identidad)
  action {
    type = "authenticate-oidc"
    authenticate_oidc {
      authorization_endpoint = "https://${var.auth0_domain}/authorize"
      client_id              = var.auth0_client_id
      client_secret          = var.auth0_client_secret
      issuer                 = "https://${var.auth0_domain}/"
      token_endpoint         = "https://${var.auth0_domain}/oauth/token"
      user_info_endpoint     = "https://${var.auth0_domain}/userinfo"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.lambda_ms2_tg.arn
  }
}

# Regla 3: Tráfico de Integración -> MS3 (FastAPI Lambda) con Auth0
resource "aws_lb_listener_rule" "rule_integrate_ms3" {
  listener_arn = aws_lb_listener.https_listener.arn
  priority     = 120

  condition {
    path_pattern {
      values = ["/integrate/*"]
    }
  }

  action {
    type = "authenticate-oidc"
    authenticate_oidc {
      # Mismos parámetros de Auth0 para inyectar x-amzn-oidc-data
      authorization_endpoint = "https://${var.auth0_domain}/authorize"
      client_id              = var.auth0_client_id
      client_secret          = var.auth0_client_secret
      issuer                 = "https://${var.auth0_domain}/"
      token_endpoint         = "https://${var.auth0_domain}/oauth/token"
      user_info_endpoint     = "https://${var.auth0_domain}/userinfo"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.lambda_ms3_tg.arn
  }
}
