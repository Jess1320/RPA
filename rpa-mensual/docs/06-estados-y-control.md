# Estados y Control

## Estado de corrida

El RPA calcula estado por periodo:

| Estado | Condicion |
| --- | --- |
| `SUCCESS` | Todos los centros descargaron y no hubo falla de publicacion espejo |
| `PARTIAL_SUCCESS` | Hay descargas OK y fallas en algunos centros, o falla en mirror |
| `FAILED` | No se descargo ningun centro solicitado |
| `CANCELLED` | Se recibio senal de cancelacion |

## Control DB

El proceso:

1. Crea o actualiza job `CEXT_PROD_MENSUAL`.
2. Crea `rpa_job_run`.
3. Registra eventos principales.
4. Registra cada archivo descargado.
5. Inserta filas en `stg.cext_prod_mensual`.
6. Actualiza `REP_MENSUAL_ACTUAL`.
7. Finaliza run con totales.
8. Crea eventos de alerta para correo y WhatsApp.

## Report status

Al iniciar marca:

```text
REP_MENSUAL_ACTUAL = EN_EJECUCION
```

Si refresh termina correctamente marca:

```text
REP_MENSUAL_ACTUAL = ACTUALIZADO
```

Si el refresh falla marca:

```text
REP_MENSUAL_ACTUAL = ERROR
```

## Poda de staging

Despues del refresh correcto ejecuta:

```text
STG_PRUNE_MENSUAL | periodo=<YYYY-MM> | keep_id_run=<id_run>
```

Esto conserva el staging del run vigente para el periodo procesado.

## Cierre mensual opcional

Si `CLOSE_MONTH=true`, luego del refresh:

1. Ejecuta archivo raw mensual cerrado.
2. Ejecuta cierre de periodo mensual.
3. Registra `CLOSE_MONTH_RAW_OK` y `CLOSE_MONTH_OK`.

Si falla, registra `CLOSE_MONTH_WARN` pero no necesariamente invalida toda la descarga.

