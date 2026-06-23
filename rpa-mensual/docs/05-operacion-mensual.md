# Operacion Mensual

## Horario actual

El RPA Mensual corre todos los dias a las `04:00` en produccion.

## Comandos de revision

```bash
systemctl status rpa-cext-mensual.timer --no-pager -l
systemctl list-timers --all rpa-cext-mensual.timer --no-pager
systemctl status rpa-cext-mensual.service --no-pager -l
journalctl -u rpa-cext-mensual.service -n 120 --no-pager
```

## Logs

Los logs se guardan en:

```text
/home/cenate/rpa_cext_diario/logs/RUN_CEXT_PROD_MENSUAL_*
```

Cada corrida tiene:

- `run.log`: salida completa.
- `summary.log`: eventos principales.

## Eventos esperados

Una corrida mensual saludable debe mostrar:

```text
RUN_START
MODE | MONTHLY
TARGET_MONTH
RANGE
GSHEET_MERGE
TOTAL_INPUT
TOTAL_OK
TOTAL_FAIL | 0
FINAL_PUBLISH_RESULT
FINAL_PUBLISH_MIRROR_OK
SYNC_MEDICOS_241
REFRESH_MENSUAL_ACTUAL
STG_PRUNE_MENSUAL
RUN_END
MAIL_SEND_OK
```

## Evidencia de referencia

Corrida revisada:

```text
RUN_CEXT_PROD_MENSUAL_20260623_040037
Periodo: 2026-06
Rango: 2026-06-01 a 2026-06-30
Input: 104
OK: 104
Fail: 0
Publicados: 105 archivos
Refresh: REFRESH_MENSUAL_ACTUAL OK
Duracion: 2951.4 segundos
```

Nota: la diferencia `Input=104` y `Publicados=105` debe investigarse antes de modificar la logica de publicacion. El publicador mensual selecciona archivos por periodo en la carpeta temporal; si existe un archivo adicional del mismo periodo, puede publicarse aunque no venga del set de centros seleccionado en esa corrida.

## Publicacion observada

La ultima corrida publico en:

- Carpeta principal mensual.
- Mirror `/mnt/abandonos/BASES`.

La carpeta diaria no es la misma que la carpeta mensual. El diario publica en la ruta diaria; el mensual publica en ruta mensual y mirror.

## Criterios de revision diaria

1. Confirmar que el timer sigue activo.
2. Confirmar que el servicio termino `inactive/dead` y no `failed`.
3. Revisar `TOTAL_OK` y `TOTAL_FAIL`.
4. Confirmar `FINAL_PUBLISH_RESULT`.
5. Confirmar `REFRESH_MENSUAL_ACTUAL`.
6. Confirmar `MAIL_SEND_OK`.
7. Revisar warnings `DB_FILE_WARN`, `SCHEMA_DRIFT`, `FINAL_PUBLISH_MIRROR_FAIL`.
8. Comparar `TOTAL_OK` contra `final_files`; si no coinciden, revisar si hay archivos sobrantes del periodo en la carpeta temporal.
