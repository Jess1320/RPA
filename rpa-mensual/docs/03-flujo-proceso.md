# Flujo del Proceso

## Cadena de ejecucion

```text
rpa-cext-mensual.timer
  -> rpa-cext-mensual.service
    -> run_rpa_mensual.sh
      -> source .venv/bin/activate
        -> ENV_FILE=.env_mensual
          -> python -u RPA_CEXT_PROD_MENSUAL.py
```

## Etapas logicas

1. `CONFIGURATION`
2. `LOG_INIT`
3. `MONTH_CONTEXT`
4. `DB_PRECHECK`
5. `CONTROL_DB_INIT`
6. `GSHEET_READ`
7. `OVERRIDE_CACHE`
8. `USER_HEALTH`
9. `DOWNLOAD`
10. `FALLBACK`
11. `STAGING_LOAD`
12. `FINAL_PUBLICATION`
13. `MEDICAL_STAFF_SYNC`
14. `REFRESH_MENSUAL`
15. `STAGING_PRUNE`
16. `MONTH_CLOSE`
17. `STATE_FINALIZATION`
18. `MAIL_NOTIFICATION`

## Seleccion de centros/IPRESS

El RPA lee `GSHEET_TABS` desde `.env_mensual`. En produccion se observaron las tabs:

- `ESPECIALIDADES`
- `CENACRON`

Para el mes procesado busca la columna del mes en espanol, por ejemplo `JUNIO`. Acepta tambien alias para septiembre/setiembre.

Una fila entra al proceso cuando:

- Tiene codigo en columna `COD_IPRESS`.
- Tiene macroregion valida en columna `MACRO`.
- La celda del mes esta marcada como `TRUE`, `VERDADERO`, `SI`, `SÍ`, `1`, `X`, `✔`, `✅` o `V`.

Luego deduplica centros entre tabs usando codigo canonico, por ejemplo `039` y `39` se consideran el mismo centro.

## Descarga por centro

Para cada centro/IPRESS:

1. Crea perfil temporal de Chrome.
2. Abre `URL_HOME`.
3. Ingresa usuario y password.
4. Selecciona el centro/IPRESS en `centroAsistencial`.
5. Navega a `FRM_MASIVAS`.
6. Completa `fe_ini` y `fechaFin`.
7. Selecciona `formatoArchivo = xls`.
8. Ejecuta descarga.
9. Espera archivo por prefijo `centro_TAG_`.
10. Valida TAG, sufijo, estabilidad y archivo no vacio.
11. Replica a mirrors temporales si estan configurados.
12. Cierra Chrome y elimina perfil temporal.

## Fallback

El mensual tiene tres mecanismos:

- Overrides aprendidos: primero intenta centros que ya tienen macro efectiva conocida.
- Healthcheck por macro: valida credenciales antes de procesar los centros de esa macro.
- Fallback: si un centro no existe en la macro declarada, intenta con macros alternativas.

Los overrides se guardan en DB para reusar la macro efectiva en futuras corridas.

## Carga a staging

Cada archivo descargado se registra en control DB y luego se carga a `stg.cext_prod_mensual`.

Validaciones aplicadas:

- Deteccion de delimitador.
- Normalizacion de cabecera.
- Uso de alias de columnas desde DB.
- Deteccion de columnas desconocidas.
- Deteccion de columnas requeridas faltantes.
- Insercion de version de cabecera.
- Hash por fila.
- Registro de estado `LOADED_TO_STG`.

## Publicacion

Cuando hay al menos un centro OK:

1. Busca archivos del periodo en la carpeta temporal.
2. Filtra los archivos para publicar solo centros descargados correctamente en la corrida.
3. Si encuentra archivos del periodo fuera de la lista esperada, registra `FINAL_PUBLISH_SKIP_UNEXPECTED_FILES`.
4. Copia a staging local dentro del padre de la carpeta final.
5. Elimina de la carpeta final solo los archivos del mismo periodo.
6. Mueve el nuevo lote a la carpeta final.
7. Repite la operacion para cada mirror configurado.

## Refresh y cierre

Si el estado final es `SUCCESS` o `PARTIAL_SUCCESS`:

1. Sincroniza catalogo de medicos desde fuente 241.
2. Ejecuta `call_refresh_mensual_actual`.
3. Marca `REP_MENSUAL_ACTUAL` como actualizado.
4. Ejecuta poda de staging mensual con `prune_stg_cext_prod_mensual_keep_run`.
5. Si `CLOSE_MONTH=true`, archiva raw mensual cerrado y llama cierre de periodo mensual.

El cierre mensual se usa cuando se requiere consolidar historico del periodo. La corrida normal diaria del mensual no archiva historico completo cada dia para evitar crecimiento innecesario de almacenamiento.
