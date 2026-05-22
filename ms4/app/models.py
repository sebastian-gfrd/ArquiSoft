from sqlalchemy import Column, Integer, String, Date, Numeric
from app.database import Base

class ProcessedCost(Base):
    """
    Modelo relacional para almacenar el histórico de costos procesados por inquilino y proyecto.
    
    Este modelo cumple con el requerimiento de Integridad Analítica (ASR-04) permitiendo
    inserciones masivas y consultas de solo lectura de alta velocidad para el Microservicio 2.
    """
    __tablename__ = "processed_costs"
    
    # Llave primaria autoincremental
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identificadores de negocio inmutables (desacoplamiento total del microservicio administrativo)
    tenant_id = Column(Integer, nullable=False, index=True)
    project_id = Column(Integer, nullable=False, index=True)
    
    # Proveedor de nube: AWS o GCP
    provider = Column(String(50), nullable=False)
    
    # Fecha correspondiente a los costos procesados
    fecha_consumo = Column(Date, nullable=False, index=True)
    
    # Costos desagregados en formato numérico preciso para contabilidad FinOps
    costo_computo = Column(Numeric(18, 2), nullable=False, default=0.00)
    costo_almacenamiento = Column(Numeric(18, 2), nullable=False, default=0.00)
    costo_otros = Column(Numeric(18, 2), nullable=False, default=0.00)
    
    # Conteo de recursos que no cumplen con parámetros óptimos de uso
    recursos_infrautilizados_count = Column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<ProcessedCost(id={self.id}, tenant_id={self.tenant_id}, project_id={self.project_id}, "
            f"provider='{self.provider}', fecha='{self.fecha_consumo}', total_cost={self.costo_computo + self.costo_almacenamiento + self.costo_otros})>"
        )
