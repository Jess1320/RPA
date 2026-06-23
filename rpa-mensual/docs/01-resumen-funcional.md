# Resumen Funcional

## Proposito

El RPA Mensual descarga informacion de Consulta Externa desde ExplotaDatos para un mes calendario completo. La data permite mantener reportes mensuales vigentes para consumo operativo, BI y seguimiento institucional.

## Alcance de datos

El archivo descargado corresponde al reporte `PacCitCExt` e incluye citas, pacientes, profesionales, servicios, actividades, consultorios, estados de cita, modalidad, procedencia y datos adicionales del proceso asistencial.

## Periodo de trabajo

El periodo se calcula con `MES_A_PROCESAR`.

Valores soportados:

- `ACTUAL`: mes calendario actual.
- `ANTERIOR`: mes calendario anterior.
- `SIGUIENTE`: mes calendario siguiente.
- `YYYY-MM`: mes explicito, por ejemplo `2026-06`.
- Lista separada por comas: permite procesar mas de un mes en una corrida.

Para cada mes se genera:

- Fecha inicial: primer dia del mes.
- Fecha final: ultimo dia del mes.
- TAG: `YYYYMMDD_YYYYMMDD`.
- Periodo de proceso: `YYYY-MM`.

## Uso posterior

La informacion se usa para:

- Publicar bases mensuales de Consulta Externa.
- Alimentar reportes mensuales del periodo.
- Cargar staging mensual en PostgreSQL.
- Refrescar el reporte `REP_MENSUAL_ACTUAL`.
- Conservar historico o cierre mensual si se activa `CLOSE_MONTH`.

## Criticidad

Alta. El proceso mensual consolida volumen mayor que el diario y publica archivos usados por BI y reportes de periodo. Una descarga parcial puede dejar el mes actualizado solo para algunos centros/IPRESS.

