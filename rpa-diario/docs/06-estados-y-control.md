# Estados y Control

## Problema actual

Se ha observado que el RPA puede reportar `PARTIAL_SUCCESS` aunque las descargas y la publicacion hayan finalizado correctamente. La causa probable es que `final_status` se calcula antes de ejecutar o confirmar etapas complementarias como sync, refresh y reportes derivados.

## Regla principal

No calcular el estado oficial hasta que todas las etapas obligatorias tengan estado terminal.

Estados terminales:

- `SUCCEEDED`
- `FAILED`
- `PARTIAL`
- `SKIPPED`
- `CANCELLED`
- `TIMED_OUT`

## Estados recomendados por etapa

```text
download_status
staging_status
publication_status
sync_status
report_refresh_status
prune_status
notification_status
overall_status
data_ready
```

## Estados generales recomendados

- `SUCCESS`: todas las etapas criticas terminaron correctamente.
- `SUCCESS_WITH_WARNINGS`: los datos estan listos, pero fallo algo no critico como el correo.
- `PARTIAL_SUCCESS`: existe informacion parcial o una etapa critica no termino completamente.
- `FAILED`: no existe dataset utilizable.
- `CANCELLED`: interrupcion controlada.
- `TIMED_OUT`: se supero el SLA o lease.
- `RUNNING`: ejecucion activa.
- `STALE`: no hay heartbeat dentro del tiempo permitido.

## Matriz base

| Descarga | Publicacion | Refresh | Resultado | data_ready |
| --- | --- | --- | --- | --- |
| 100% OK | OK | OK | `SUCCESS` | true |
| Parcial | OK parcial | OK | `PARTIAL_SUCCESS` | segun politica |
| 100% OK | OK | FAIL | `PARTIAL_SUCCESS` | false |
| 100% OK | FAIL | No ejecutado | `FAILED` | false |
| 0 OK | No ejecutado | No ejecutado | `FAILED` | false |
| 100% OK | OK | OK, correo FAIL | `SUCCESS_WITH_WARNINGS` | true |
| Cancelada | Cualquiera | Cualquiera | `CANCELLED` | false |

## Recomendacion tecnica

Implementar una funcion unica de derivacion del estado final, usada por:

- `finish_run`.
- Correo.
- Alertas.
- Exit code.
- Watermark.
- Dashboard.

La notificacion no debe modificar la disponibilidad de datos. Si el correo falla, el estado puede ser `SUCCESS_WITH_WARNINGS`, pero `data_ready` puede seguir siendo `true`.

## Correccion preparada en version controlada

La version controlada mueve el cierre oficial despues de las fases complementarias:

1. Descargas.
2. Carga a staging.
3. Publicacion final.
4. Sync de medicos.
5. Refresh de reportes diarios.
6. Prune de staging.
7. Calculo de duracion final.
8. Derivacion de `final_status`.
9. Persistencia en PostgreSQL.
10. Notificacion.

El refresh ya no depende de un `final_status` inicial o provisional. Se ejecuta cuando existe base operativa suficiente:

- Hay al menos una descarga correcta.
- La publicacion final fue correcta.
- Existe conexion de control a PostgreSQL.
- La ejecucion no fue cancelada.

Si el refresh no se ejecuta, el summary registra `REFRESH_REPORTES_DIARIO_SKIP` con un motivo explicito.
