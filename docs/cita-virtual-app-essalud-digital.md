# CITA_VIRTUAL - App EsSalud Digital

## Contexto funcional

ExplotaDatos incorporo la columna `CITA_VIRTUAL` en los reportes de Consulta Externa.

Esta columna identifica el origen de la cita cuando el paciente usa la App EsSalud Digital:

| Valor | Interpretacion |
| --- | --- |
| `APP_TELE` | Cita generada desde el boton `Agendar cita virtual` de la App EsSalud Digital |
| vacio / null | Cita generada desde ESSI o desde el boton `Agendar cita para su CAS de Adscripcion` |

La columna debe conservarse porque permite diferenciar citas virtuales gestionadas por la App frente a citas regulares u otros flujos de agendamiento.

## Alcance RPA

Los RPAs de Consulta Externa deben tratar `CITA_VIRTUAL` como columna conocida, no como schema drift.

Aplica a:

- RPA Diario CEXT.
- RPA Mensual CEXT.
- RPA Mensual Cronicos, por compatibilidad con la estructura CEXT.

## Mapeo tecnico

| TXT ExplotaDatos | Staging / vistas |
| --- | --- |
| `CITA_VIRTUAL` | `cita_virtual` |

Tablas con columna formal:

- `stg.cext_prod_diario.cita_virtual`
- `stg.cext_prod_mensual.cita_virtual`
- `ops.rep_mensual_actual.cita_virtual`

Vistas expuestas:

- `ops.vw_cext_diaria_full.cita_virtual`
- `ops.vw_cext_diaria_medicos_activos_full.cita_virtual`
- `ops.vw_cext_mensual_full.cita_virtual`
- `ops.vw_cext_mensual_medicos_activos_full.cita_virtual`
- `ops.vw_rep_mensual_actual.cita_virtual`

Catalogo de columnas:

- `config.explotadatos_columna.canonical_name = 'CITA_VIRTUAL'`
- `es_requerida = false`
- `es_texto_critico = true`
- `activa = true`

## Regla de compatibilidad

Para corridas historicas cargadas antes de que exista la columna formal, el valor puede estar en `extra_columns ->> 'CITA_VIRTUAL'`.

Las vistas y el refresh mensual deben resolver el valor con esta prioridad:

```sql
nullif(trim(coalesce(cita_virtual, extra_columns->>'CITA_VIRTUAL', '')), '')
```

Esto permite que:

- Las nuevas corridas escriban directamente en `cita_virtual`.
- Las corridas anteriores sigan exponiendo el dato si quedo almacenado como columna extra.

## Validacion productiva inicial

El 2026-08-03 se actualizo produccion para soportar la columna.

Validacion sobre cierre Julio 2026:

- `ops.rep_mensual_actual` periodo `2026-07`: 58,474 registros.
- Registros con `cita_virtual = 'APP_TELE'`: 4,934.

Esta validacion confirma que la columna quedo disponible para consumo desde la publicacion mensual actual.
