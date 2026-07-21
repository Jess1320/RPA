# Operacion QA - RPA Tele Urgencia

## Horario objetivo

```text
06:00 America/Lima
```

## Ejecucion manual

```bash
cd /ruta/al/rpa-tele-urgencia
ENV_FILE=.env.qa scripts/run_rpa_tele_urgencia.sh
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
logs/RUN_TELE_URGENCIA_*/run.log
logs/RUN_TELE_URGENCIA_*/summary.csv
orchestrator_logs/orchestrator_YYYYMMDD.log
```

Criterios:

- Existe `CONFIG_OK`.
- Google Sheets selecciona centros.
- El log muestra `MACRO_START` y `MACRO_END`.
- Cada centro esperado queda `OK`.
- `summary.csv` contiene una fila por centro/mes descargado.
- El wrapper termina con `exit_code=0`.

## Diferencias QA / produccion

QA puede usar rutas locales de prueba para no publicar archivos sobre carpetas finales. Produccion debe usar la ruta montada definitiva.

## Pendientes

- Validar correo con `MAIL_ENABLED=true` cuando QA tenga SMTP configurado.
- Registrar corrida en PostgreSQL `rpa_control`.
- Exponer estado para panel.
