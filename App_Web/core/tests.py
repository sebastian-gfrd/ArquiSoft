import json
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Tenant, Project, UserProfile, EstadoTenant, PlanTenant, ProveedorCloud, RolUserProfile
from rest_framework.test import APIClient
from rest_framework import status

Usuario = get_user_model()


class CoreAdministrativeTests(TestCase):
    """
    Conjunto de pruebas unitarias modernas para el Microservicio 1: Core Administrativo de BITE.co.
    Cubre: Aislamiento Multitenant, Integridad de Sesiones, Resiliencia de EventBridge y Django Signals.
    """

    def setUp(self):
        # 1. Crear Tenants de prueba
        self.tenant_a = Tenant.objects.create(
            nombre="Empresa A",
            estado=EstadoTenant.ACTIVO,
            plan=PlanTenant.ENTERPRISE
        )
        self.tenant_b = Tenant.objects.create(
            nombre="Empresa B",
            estado=EstadoTenant.ACTIVO,
            plan=PlanTenant.FREE
        )

        # 2. Crear Usuarios y Perfiles Organizacionales
        self.user_a = Usuario.objects.create_user(
            email="admin@empresa_a.com",
            nombre="Admin A",
            password="securepasswordA"
        )
        self.profile_a = UserProfile.objects.create(
            usuario=self.user_a,
            tenant=self.tenant_a,
            rol=RolUserProfile.ADMIN
        )

        self.user_b = Usuario.objects.create_user(
            email="viewer@empresa_b.com",
            nombre="Viewer B",
            password="securepasswordB"
        )
        self.profile_b = UserProfile.objects.create(
            usuario=self.user_b,
            tenant=self.tenant_b,
            rol=RolUserProfile.VIEWER
        )

        # 3. Clientes de API con Autenticación Simulada
        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

    @patch("core.signals.boto3.client")
    def test_creacion_proyecto_publica_evento_eventbridge(self, mock_boto_client):
        """
        Verifica que al guardar un Project, se dispare la señal post_save y se publique
        el evento JSON correcto en AWS EventBridge a través de boto3.
        """
        mock_events = MagicMock()
        mock_events.put_events.return_value = {"FailedEntryCount": 0, "Entries": []}
        mock_boto_client.return_value = mock_events

        # Crear Proyecto
        proj = Project.objects.create(
            tenant=self.tenant_a,
            nombre="Proyecto FinOps A",
            descripcion="Optimización de instancias EC2",
            proveedor_cloud_primario=ProveedorCloud.AWS
        )

        # Verificar que se instanció el cliente y se llamó put_events
        self.assertTrue(mock_events.put_events.called)
        
        # Recuperar argumentos pasados a EventBridge
        call_args = mock_events.put_events.call_args[1]
        entries = call_args.get("Entries", [])
        self.assertEqual(len(entries), 1)
        
        entry = entries[0]
        self.assertEqual(entry["Source"], "bite.core")
        self.assertEqual(entry["DetailType"], "ProjectCreated")
        self.assertEqual(entry["EventBusName"], "bite-event-bus")
        
        # Validar el Detail JSON estructurado
        detail = json.loads(entry["Detail"])
        self.assertEqual(detail["id"], proj.id)
        self.assertEqual(detail["nombre"], "Proyecto FinOps A")
        self.assertEqual(detail["tenant_id"], self.tenant_a.id)

    @patch("core.signals.boto3.client")
    def test_falla_eventbridge_no_aborta_transaccion_db(self, mock_boto_client):
        """
        Garantiza la resiliencia y el aislamiento de fallos (ASR-04/05). 
        Si EventBridge lanza una excepción de red, la transacción de base de datos local
        debe completarse de forma exitosa sin perturbar el guardado en DB.
        """
        mock_events = MagicMock()
        mock_events.put_events.side_effect = Exception("Falla crítica de red o Timeout con AWS")
        mock_boto_client.return_value = mock_events

        # Crear Proyecto (debe guardarse sin lanzar excepciones a la capa superior)
        proj = Project.objects.create(
            tenant=self.tenant_a,
            nombre="Proyecto Resiliente",
            descripcion="Prueba de fallo EventBridge",
            proveedor_cloud_primario=ProveedorCloud.GCP
        )

        # El objeto debe haberse persistido correctamente
        self.assertIsNotNone(proj.id)
        self.assertEqual(Project.objects.filter(id=proj.id).count(), 1)

    def test_aislamiento_multitenant_proyectos(self):
        """
        Verifica el estricto aislamiento de proyectos (Multitenancy).
        Un usuario de la Empresa A no debe poder ver los proyectos de la Empresa B.
        """
        # Crear proyecto en Empresa B
        proj_b = Project.objects.create(
            tenant=self.tenant_b,
            nombre="Proyecto Privado B",
            proveedor_cloud_primario=ProveedorCloud.GCP
        )

        # 1. Cliente A (Empresa A) intenta listar proyectos
        response = self.client_a.get("/api/v1/projects/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project_ids = [p["id"] for p in response.data]
        self.assertNotIn(proj_b.id, project_ids)

        # 2. Cliente A intenta acceder directamente por ID al proyecto de la Empresa B
        response_detail = self.client_a.get(f"/api/v1/projects/{proj_b.id}/")
        # Debe retornar 404 para ocultar la existencia y resguardar la confidencialidad
        self.assertEqual(response_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_usuario_estandar_no_puede_crear_proyecto_en_otro_tenant(self):
        """
        Verifica que la API impida a un usuario asociar proyectos a un Tenant ajeno.
        """
        payload = {
            "tenant": self.tenant_a.id,
            "nombre": "Inyección Maliciosa de Proyecto",
            "proveedor_cloud_primario": ProveedorCloud.AWS
        }
        
        # Cliente B intenta asociar su proyecto al Tenant A
        response = self.client_b.post("/api/v1/projects/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tenant", response.data)

    def test_health_check_operational(self):
        """
        Valida que el endpoint de salud proactivo (/health/) retorne estado operacional
        saludable de la base de datos y la caché de desarrollo.
        """
        response = self.client_a.get("/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
