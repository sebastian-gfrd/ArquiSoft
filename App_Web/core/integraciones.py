"""
Política de integraciones BITE.co (SaaS extensible, sin acoplamiento a CRM/ERP).

Integraciones explícitas en esta etapa (según cliente):
- Proveedores cloud (ingesta de consumo/costos).
- Identidad y control de acceso (usuarios, roles, permisos).
- Servicios de notificación (correo, etc.).

No se contemplan integraciones nativas con CRM, ERP o contabilidad específica.
La interoperabilidad con sistemas externos debe hacerse vía APIs REST, webhooks
u otros mecanismos estándar, sin modificar el núcleo del dominio.
"""
