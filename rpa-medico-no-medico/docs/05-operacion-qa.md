# Operacion QA - RPA Medico y No Medico

## Horario objetivo

```text
02:30 America/Lima
```

## Ejecucion manual

```bash
cd /ruta/al/rpa-medico-no-medico
ENV_FILE=.env.qa scripts/run_rpa_medico_no_medico.sh
```

## Credenciales maestras

El archivo real de usuarios debe estar fuera de Git:

```text
/Users/cenate2/rpas/shared/config/.env_usuarios
```

El `.env.qa` debe apuntar a esa ruta con `RPA_USERS_ENV_FILE`. Para pruebas de transicion se permite `REQUIRE_MACRO=false` y `DEFAULT_MACRO=CENTRO`; antes de produccion la hoja debe tener columna `MACRO` y se debe usar `REQUIRE_MACRO=true`.

## Validacion

Revisar:

```text
logs/RUN_MEDICO_NO_MEDICO_*/run.log
orchestrator_logs/orchestrator_YYYYMMDD.log
```

Criterios:

- Existe `CONFIG_OK`.
- Google Sheets selecciona centros.
- El log muestra `MACRO_START` y `MACRO_END`.
- Cada centro esperado descarga `MEDICO` si `RUN_MEDICO=true`.
- Cada centro esperado descarga `NO_MEDICO` si `RUN_NO_MEDICO=true`.
- `Centros FAIL` queda `0`.
- El wrapper termina con `exit_code=0`.

## Diferencias QA / produccion

QA puede usar rutas locales de prueba para no publicar archivos sobre carpetas finales. Produccion requiere montar el recurso de `BD_CControl` o definir una ruta final equivalente.

## Pendientes

- Validar correo con `MAIL_ENABLED=true` cuando QA tenga SMTP configurado.
- Registrar corrida en PostgreSQL `rpa_control`.
- Exponer estado para panel.
- Definir montaje definitivo para las dos salidas.
