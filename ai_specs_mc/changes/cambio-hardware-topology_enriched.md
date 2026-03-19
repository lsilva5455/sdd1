# Task: cambio-hardware-topology - Evolve hardware topology for multi-country and AI-driven SIM lifecycle

## Completeness Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Objective | Complete | The task clearly states the desired shift from Chile-only topology rules to a multi-country, telemetry-driven model |
| Scope | Partial | The proposal identifies major areas of change, but it does not define rollout boundaries, phasing, or explicit exclusions |
| Acceptance criteria | Missing | The task describes direction and examples, but it does not define measurable conditions for completion |
| Technical context | Partial | Affected concerns are identified (configuration, API, DB, orchestration, AI), but exact components and layer ownership are not fully mapped |
| Dependencies | Partial | The task implies dependencies on telemetry, historical data, config changes, and an inference service, but prerequisites are not explicitly listed |
| Edge cases | Missing | No behavior is defined for unknown carriers, missing telemetry, inference failures, or backward compatibility |
| Testing strategy | Missing | No unit, integration, or manual verification plan is provided |
| Impact analysis | Partial | The task mentions API, schema, and config impacts, but it does not describe migration risks or compatibility expectations for existing flows |

**Overall Score: 1/8 criteria complete**

## Original Description

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

## Enhanced Description

### Objective

Replace Chile-specific ICCID carrier resolution and static SIM lifecycle labels with a configuration-driven, multi-country topology model and a telemetry-based SIM health evaluation flow. This change matters because the current hardware and orchestration assumptions block regional expansion and do not provide enough signal to manage SIM exhaustion, throttling risk, or proactive carrier-specific mitigation.

The enriched goal has two connected outcomes:
- make location and carrier resolution independent from hardcoded Chilean ICCID prefixes
- make lifecycle decisions depend on telemetry and inference rather than fixed age buckets such as `Virgin`, `3M`, `7M`, and `Dead`

### Scope

- **In scope**:
  - Introduce a configuration-level carrier registry with country metadata and ICCID-to-carrier mappings
  - Replace hardcoded ICCID prefix validation in core logic with a dynamic resolution service
  - Extend `SimSlot`-related API responses with location metadata (`country_code`, `network_operator`)
  - Add data model support for SIM country attribution and telemetry persistence needed for health evaluation
  - Define a SIM health evaluation capability that consumes telemetry and produces a health-oriented outcome for orchestration
  - Define an orchestration integration point through `/analytics/prediction` before a SIM is sent to production
  - Expose prediction results for operator visibility in the first iteration, using existing API/UI surfaces where applicable
- **Out of scope**:
  - Full retraining strategy, model selection, or MLOps lifecycle for the classifier beyond what is required to consume predictions in the system
  - Automatic carrier-wide policy changes in the first implementation increment
  - New frontend dashboards dedicated to ML operations unless existing pool views must expose the new data
  - Hardware protocol changes to SimBank AT commands or modem reboot logic
  - Country onboarding process for markets beyond the configuration and resolution model described here

### Affected Architecture Layers

- [x] Domain (entities, value objects, repository ABCs) - carrier context, location metadata, SIM health state/value representation
- [x] Application (services, validators) - ICCID resolution service, health evaluation orchestration, prediction request/response handling
- [x] Infrastructure (DB repos, hardware adapters, serial communication) - config loading, telemetry persistence, inference service integration, schema migration
- [x] Presentation - Flask API (blueprints, routes) - `SimSlot` payload changes and analytics endpoint definition
- [x] Presentation - React Dashboard (components, hooks) - existing pool views may need to render country/operator/health fields if they surface `SimSlot` data
- [ ] Presentation - Streamlit Dashboard (pages, widgets)

### Acceptance Criteria

1. `config.json` is the canonical source of truth for country metadata and carrier mappings in the first implementation increment.
2. ICCID resolution uses configuration data and applies a deterministic `longest prefix match` rule when multiple carrier mappings could match the same ICCID.
3. ICCID resolution returns carrier and country context from configuration for at least the sample Chile (`CL`) and Colombia (`CO`) mappings described in the original task.
4. `SimSlot` API responses include location metadata with `country_code` and `network_operator` when the carrier registry can resolve the SIM.
5. The system stores the minimum telemetry required for health evaluation, including `usage_frequency`, `burn_rate`, `at_command_latency`, and `carrier_rejection_count`, or explicitly documents any deferred field as a later increment.
6. `/analytics/prediction` returns, at minimum, `health_score`, `state`, and `recommended_action`.
7. A health evaluation flow produces a SIM-level outcome that includes a `health_score` and a mapped operational state (`ACTIVE`, `THROTTLED`, `RECOVERY`, or `EoL`).
8. The orchestrator can query `/analytics/prediction` before placing a SIM into production and, if prediction is unavailable or telemetry is insufficient, it falls back to a conservative deterministic policy while marking prediction as unavailable.
9. Legacy lifecycle labels (`Virgin`, `3M`, `7M`, `Dead`) remain supported through a temporary mapping during the transition to the health-based model.
10. The first implementation increment provides prediction consumption and operator visibility, but does not apply automatic carrier-wide throttling or policy changes.
11. Existing Chilean operation continues to work with the new registry model after migrating current carrier mappings into configuration.
12. All documentation and capability specs affected by the new topology, data model, and prediction flow are updated in English.

### Edge Cases and Error Scenarios

1. **Unknown ICCID prefix**: The carrier resolution flow must return an explicit unresolved result and avoid crashing or misclassifying the SIM.
2. **Overlapping or variable-length ICCID prefixes**: The system must apply `longest prefix match` so the most specific ICCID rule wins deterministically.
3. **Missing telemetry for a SIM**: The orchestrator must use a conservative deterministic fallback policy and mark prediction as unavailable instead of blocking unexpectedly or inventing a health result.
4. **Prediction service unavailable**: The orchestrator must continue with the same conservative deterministic fallback policy and record that prediction could not be obtained.
5. **Existing lifecycle values already stored in data sources**: A temporary compatibility rule must map legacy states to the new health model during the transition period.
6. **Country metadata exists but carrier mapping does not**: The API contract should define whether partial location data is returned.
7. **Telemetry indicates carrier-wide blocking behavior**: The first increment must report the condition and expose prediction results for operator visibility, but must not apply automatic carrier-wide operational changes.

### Dependencies

- **Prerequisites**:
  - Treat `config.json` as the canonical source of truth for carrier and country configuration in the first increment
  - Define `/analytics/prediction` to return `health_score`, `state`, and `recommended_action`
  - Define the conservative deterministic fallback policy used when prediction is unavailable or telemetry is insufficient
  - Define the temporary mapping from legacy lifecycle states to the new health-oriented model
- **External**:
  - Historical telemetry data sufficient to train or validate the classifier
  - An inference runtime or service boundary for prediction execution
  - Carrier prefix data for each supported country
- **Affected components**:
  - `openspec/specs/hardware-topology/spec.md`
  - `openspec/specs/configuration/spec.md`
  - `openspec/specs/orchestration/spec.md`
  - `openspec/specs/pool-visualization/spec.md`
  - `openspec/specs/session-management/spec.md`
  - API schemas and route definitions related to `SimSlot` and analytics

### Testing Strategy

- **Unit tests**:
  - Validate ICCID resolution for known Chile and Colombia prefixes
  - Validate unresolved ICCID behavior for unknown prefixes
  - Validate mapping from telemetry inputs to health evaluation output contract
- **Integration tests**:
  - Verify API responses include `country_code` and `network_operator`
  - Verify `/analytics/prediction` returns the contract expected by the orchestrator
  - Verify persistence of `country_code` and telemetry payload fields in the selected storage layer
- **Frontend tests**:
  - Verify any existing React pool view that consumes `SimSlot` data renders the new location and health fields correctly if those fields are exposed to the UI
- **Manual verification**:
  - Load sample CL and CO carrier mappings and confirm country/operator resolution from ICCID examples
  - Simulate missing telemetry and prediction service unavailability to verify the defined fallback behavior
  - Confirm current Chile-only flows still operate after the registry migration

### Implementation Notes

- Keep the carrier registry configuration-driven and separate from hardware-control logic so regional expansion does not require code changes in serial or switching flows.
- Use `config.json` as the first implementation source of truth for `country` and `carrier` metadata.
- Prefer a dedicated resolution service over scattered prefix checks to avoid repeating country/carrier logic across API, orchestration, and persistence layers.
- ICCID carrier resolution should use `longest prefix match` to support specific mappings without ambiguity.
- The prediction contract should remain minimal and operationally useful: `health_score`, `state`, and `recommended_action`.
- If prediction is unavailable or telemetry is incomplete, the orchestrator should fall back to a conservative deterministic policy and explicitly record that no prediction result was available.
- Legacy lifecycle labels should be preserved through a temporary mapping during the transition rather than removed immediately.
- Because this change crosses configuration, API, persistence, and orchestration concerns, a phased implementation is recommended: registry and API contract first, telemetry persistence second, inference integration third.
- The first delivery should stop at prediction consumption and operator visibility; automatic carrier-wide actions should be deferred to a later increment.
- Update capability specs in `openspec/specs/` together with implementation work because the task changes architectural assumptions currently documented in `hardware-topology`, `configuration`, `orchestration`, and related specs.
- All new technical artifacts should remain in English, while the original task text is preserved verbatim for traceability.

## Open Questions

No blocking open questions remain at this stage. The following implementation decisions have been confirmed:

1. `config.json` is the canonical source of truth for country and carrier metadata in the first increment.
2. `/analytics/prediction` returns `health_score`, `state`, and `recommended_action`.
3. If prediction is unavailable or telemetry is insufficient, the orchestrator uses a conservative deterministic fallback policy and marks prediction as unavailable.
4. The first iteration includes prediction consumption and operator visibility only; it does not include automatic carrier-wide behavior changes.
5. Legacy lifecycle values (`Virgin`, `3M`, `7M`, `Dead`) are preserved through a temporary mapping during transition.
6. ICCID carrier resolution uses `longest prefix match`.
