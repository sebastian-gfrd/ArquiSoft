# BITE.co - Documento de Arquitectura General (Microservicios & CQRS)

**Para:** Gemini 3.5 Flash (Entorno Antigravity 2.0)  
**Contexto del Sistema:** Plataforma SaaS Multitenant de Gestión FinOps y Optimización Cloud.

---

## 1. Vista General del Sistema

La arquitectura de BITE.co ha evolucionado de un monolito Django a una **Arquitectura de Microservicios Desacoplada y Orientada a Eventos**. El sistema implementa el patrón **Database per Service** para aislar el radio de explosión (*Blast Radius*) y el patrón **CQRS** a nivel de infraestructura para segregar las cargas transaccionales de escritura de las consultas de baja latencia.

### Objetivos Técnicos Críticos (ASRs Resueltos)
- **ASR-01 (Escalabilidad):** Soportar picos de 12,000 usuarios concurrentes en ventanas de 10 minutos.
- **ASR-02 (Latencia):** Despachar reportes interactivos en un tiempo $< 100\text{ ms}$.
- **ASR-03 (Asincronía):** Delegar análisis pesados ($> 2\text{ segundos}$) a Background Workers, liberando la UI de inmediato.
- **ASR-04/05 (Disponibilidad y Resiliencia):** Aislamiento de fallos; la degradación del motor analítico no compromete el flujo de autenticación central.

---

## 2. Descomposición de Microservicios y Fronteras Lógicas

El ecosistema se divide en 4 microservicios independientes distribuidos por dominio funcional:

```
[Cliente Web] ---> [AWS Application Load Balancer]
       |
       +------------------+------------------+
       | (/auth/)        | (/reports/)     | (/integrate/*)
       v                  v                  v
[1. Django Core]   [2. Analytics API] [3. Integration Service]
  (ECS Fargate)       (AWS Lambda)       (AWS Lambda)
       |                  |                  |
       v                  v                  +---> [AWS SQS]
   [Admin DB]        [RDS Proxy]                           |
       ^                  |                                v
       |                  v                        [4. Celery Worker]
       +------------------+-----------------------   (ECS Fargate)
                          |
                          v
                    [Analytics DB]
```

### 1. Microservicio Core Administrativo (Django)
- **Tecnología:** Django 5.x de nivel intermedio, empaquetado en contenedores WSGI/ASGI estándar.
- **Cómputo:** **AWS ECS Fargate** (Instancias persistentes tipo `t3.medium`).
- **Responsabilidades:** 
  - Gestión de Identidad y Autenticación externa delegada a **Auth0** (utilizando flujos criptográficos basados en `jwks.json` locales).
  - Control de Acceso Basado en Roles (RBAC) y aislamiento de organizaciones (*Multitenancy*).
- **Persistencia:** `Admin DB` (Amazon Aurora PostgreSQL), exclusiva para tablas de usuarios, roles y metadatos de clientes.

### 2. Microservicio de Reportes Rápidos (FastAPI Analytics API)
- **Tecnología:** FastAPI (Elegido por su bajo tiempo de inicio en frío/*Cold Start*).
- **Cómputo:** **AWS Lambda** (Cómputo efímero/Serverless para absorber ráfagas masivas).
- **Responsabilidades:** Exponer los endpoints de lectura para los componentes del Frontend Dashboard.
- **Estrategia CQRS (Lectura):** Implementa el patrón *Cache-Aside*. Consulta en primera instancia a **Amazon ElastiCache (Redis)**; ante un *cache miss*, consulta a las **Réplicas de Lectura** del clúster de analítica pasando a través de **Amazon RDS Proxy**.

### 3. Motor de Ingesta Extensible (FastAPI Cloud Integration Service)
- **Tecnología:** FastAPI.
- **Cómputo:** **AWS Lambda**.
- **Responsabilidades:** Conectarse a las APIs de los proveedores de nube para extraer métricas de cómputo y reportes de costos masivos (CUR de AWS / Facturación de GCP).
- **Estrategia de Extensibilidad (Modificabilidad):** Implementa el patrón **Adapter/Plugin**. Expone una interfaz abstracta común. El microservicio conmuta dinámicamente entre adaptadores específicos (`AWSAdapter`, `GCPAdapter`) permitiendo agregar nuevas nubes sin modificar el core del código.
- **Manejo de Carga Pesada:** Si la petición analítica toma $> 2\text{ segundos}$, empaqueta los parámetros del Job y los inserta en una cola de mensajería (**Amazon SQS**), respondiendo de inmediato al cliente HTTP con un estado `202 Accepted`.

### 4. Procesador Analítico en Segundo Plano (Celery Worker)
- **Tecnología:** Python Celery Workers integrados con el ORM/Core de Django para tareas de persistencia pesada.
- **Cómputo:** **AWS ECS Fargate** (Instancias elásticas optimizadas para cómputo tipo `c5.large`). Escala dinámicamente según la métrica de mensajes acumulados en la cola SQS. Rompe el límite físico de 15 minutos impuesto por AWS Lambda.
- **Responsabilidades:** Consumir mensajes de SQS, descargar archivos de facturación masivos de S3, ejecutar algoritmos de agregación de datos, detectar patrones de desperdicio y disparar notificaciones por email vía Amazon SES si los procesos exceden los umbrales de tiempo permitidos.
- **Estrategia CQRS (Escritura):** Realiza operaciones de inserción masiva (`bulk_insert`) únicamente sobre el nodo **Writer (Escritor)** del clúster de la `Analytics DB`.

---

## 3. Estrategia de Persistencia y Consistencia de Datos

### Consistencia Eventual y Mensajería (Pub/Sub)
Las bases de datos `Admin DB` y `Analytics DB` **no se encuentran sincronizadas síncronamente**. No existen llaves foráneas (*Foreign Keys*) directas entre servicios para evitar acoplamiento y caídas en cadena (*Blast Radius* total).

- **Mecanismo de Sincronización:** Cuando el Microservicio Core (Django) modifica la estructura de una empresa o proyecto, confirma la transacción localmente y publica de inmediato un evento en **Amazon EventBridge** (ej: `ProyectoCreado`).
- **Tolerancia a Fallos:** EventBridge enruta el mensaje a la cola SQS del procesador analítico. Si la base de datos de costos está inactiva o saturada, el mensaje permanece seguro en SQS garantizando que los datos convergerán eventualmente de manera asíncrona sin afectar la experiencia web del usuario.

### El Rol Crítico de Amazon RDS Proxy
Debido a que el microservicio de lectura (*Analytics API*) corre sobre AWS Lambda, el escalado elástico inmediato a miles de hilos concurrentes saturaría el pool de conexiones TCP de Aurora PostgreSQL.
- **Mitigación:** **Amazon RDS Proxy** se interpone de forma obligatoria antes del clúster de la `Analytics DB`. El Proxy mantiene, recicla y distribuye de forma eficiente el pool de conexiones hacia los nodos de la base de datos, absorbiendo el impacto transaccional de las funciones Serverless.

---

## 4. Instrucción Operacional para el Modelo de IA
Cuando se te solicite generar, refactorizar o analizar código para cualquiera de las aplicaciones del ecosistema BITE.co, debes validar estrictamente que:
1. **Ninguna vista de Django** realice agregaciones matemáticas de consumo en tiempo real; estas deben ser delegadas al Worker o consultadas directamente desde los endpoints de FastAPI de lectura.
2. **Los adaptadores de nube** implementen la clase base abstracta de integración para preservar el principio Open/Closed.
3. **El manejo de sesiones** de Django apunte a la infraestructura compartida de Redis para mantener la arquitectura web completamente *stateless*.
