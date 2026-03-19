# Cambio en Topología de Hardware: Sistema Multi-País con IA

## Estado Actual vs. Estado Propuesto

| Aspecto | Actual | Propuesto |
|--------|--------|-----------|
| **Alcance Geográfico** | Exclusivamente Chile | Agnóstico a la región (Multi-país) |
| **Ciclo de Vida** | Lógica estática | Gestión basada en telemetría e IA |

---

## 1. Desacoplamiento Geográfico (Carrier Registry)

### Problema

La identificación de carriers por ICCID está "hardcoded" para prefijos chilenos, lo que impide la expansión a Colombia y otros mercados.

### Cambio Propuesto

Implementar un **Carrier Context Registry** en la capa de configuración. La lógica de resolución de ICCID debe pasar de ser una constante a un servicio de búsqueda dinámico.

### Nuevo Esquema de Configuración

```json
{
  "countries": {
    "CL": { "name": "Chile", "dial_code": "+56" },
    "CO": { "name": "Colombia", "dial_code": "+57" }
  },
  "carrier_mapping": [
    { "prefix": "895609", "carrier": "WOM", "country": "CL" },
    { "prefix": "895710", "carrier": "Tigo", "country": "CO" }
  ]
}
```

### Impacto en API/Spec

- Los endpoints de `SimSlot` ahora deben retornar un objeto `Location` que incluya `country_code` y `network_operator`
- Eliminar validaciones rígidas basadas en prefijos de 6 dígitos dentro del core

---

## 2. Redefinición del Ciclo de Vida (AI-Driven Lifecycle)

### Problema

El ciclo de vida actual (Virgin, 3M, 7M, Dead) es lineal y no refleja la realidad del desgaste físico o comercial de la SIM en un entorno de alta densidad.

### Cambio Propuesto

Sustituir los estados estáticos por una **Métrica de Salud Dinámica (Health Score)**.

### Variables de Telemetría para la IA

- **usage_frequency**: Densidad de peticiones/minuto
- **burn_rate**: Consumo de datos/SMS en ventana de tiempo
- **at_command_latency**: Tiempo de respuesta del modem (indicador de desgaste físico)
- **carrier_rejection_count**: Errores de red recibidos

### Nuevo Modelo de Estados

| Estado | Descripción |
|--------|-------------|
| **ACTIVE** | Operación normal |
| **THROTTLED** | Alerta de patrón de detección de carrier (reducción de frecuencia para evitar bloqueo) |
| **RECOVERY** | Periodo de enfriamiento (cooldown) tras uso intensivo |
| **EoL** | Predicción de muerte comercial inminente |

### Objetivo del Agente de IA

1. Entrenar un modelo de clasificación que identifique patrones de comportamiento que preceden al estado **DEAD** por compañía
2. **Acción Proactiva**: Si la IA detecta que el carrier MOVISTAR está bloqueando SIMs con un patrón X, el orquestador cambiará automáticamente el perfil de uso de todas las SIMs de ese carrier para "alargar" su vida útil

---

## 3. Actualización de la Infraestructura de Datos

Para soportar estos cambios, se requieren las siguientes modificaciones en la base de datos/config:

### Cambios en Base de Datos

- **Migración de Tabla `sim_cards`**: Añadir campo `country_code` y `usage_logs` (JSON)
- **Módulo de Inferencia**: Integrar un servicio de pre-procesamiento que evalúe la SIM cada vez que entra en un Handover

### Próximos Pasos en la Spec (SDD)

- [ ] Actualizar `components/schemas/SimSlot` para incluir metadata de país
- [ ] Definir el endpoint `/analytics/prediction` para que el orquestador consulte la "salud" de la SIM antes de lanzarla a producción
- [ ] Modificar el `config.json` para que sea una estructura jerárquica por país
