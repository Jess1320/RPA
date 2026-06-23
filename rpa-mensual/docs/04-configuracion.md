# Configuracion

## Archivo real

Produccion usa `.env_mensual` en `/home/cenate/rpa_cext_diario`. Ese archivo no debe versionarse porque contiene credenciales y rutas internas.

## Variables principales

| Variable | Uso |
| --- | --- |
| `URL_HOME` | Entrada al reporteador ExplotaDatos |
| `FRM_MASIVAS` | URL interna del formulario `PacCitCExt` |
| `GSHEET_URL` | Spreadsheet con centros/IPRESS |
| `CREDS_JSON` | Credencial de servicio Google |
| `GSHEET_TABS` | Tabs a leer, separadas por coma |
| `MES_A_PROCESAR` | Mes objetivo: `ACTUAL`, `ANTERIOR`, `SIGUIENTE`, `YYYY-MM` |
| `DOWNLOAD_DIRS` | Rutas temporales de descarga |
| `FINAL_PUBLISH_DIR` | Carpeta principal de publicacion mensual |
| `FINAL_PUBLISH_MIRRORS` | Carpetas espejo |
| `FILE_SUFFIX` | Sufijo esperado, normalmente `PacCitCExt.txt` |
| `FORCE_REDOWNLOAD` | Si es `true`, elimina archivos del TAG antes de descargar |
| `KEEP_ONLY_CURRENT_TAG` | Limpieza por TAG vigente |
| `HEADLESS` | Ejecuta navegador sin UI |
| `DOWNLOAD_TIMEOUT` | Timeout por descarga |
| `MAX_THREADS` | Paralelismo por macro |
| `MAX_CONCURRENT_DRIVER_STARTS` | Limite de arranques simultaneos de ChromeDriver |
| `HEALTHCHECK_ENABLED` | Activa validacion previa de usuario/macro |
| `HEALTHCHECK_BLOCKING` | Bloquea macro si credencial falla |
| `DB_PRECHECK_ENABLED` | Valida puerto PostgreSQL antes de correr |
| `RPA_FAIL_IF_DB_DOWN` | Falla la corrida si no hay control DB |
| `CLOSE_MONTH` | Ejecuta cierre mensual si esta activo |
| `CLOSE_MONTH_PERIOD` | Periodo a cerrar; si esta vacio usa el periodo procesado |
| `MAIL_ENABLED` | Activa notificacion por correo |

## Credenciales por macro

El mensual usa cuatro pares usuario/password:

- `USER_CENTRO` / `PASSWORD_CENTRO`
- `USER_NORTE` / `PASSWORD_NORTE`
- `USER_SUR` / `PASSWORD_SUR`
- `USER_LIMA_ORIENTE` / `PASSWORD_LIMA_ORIENTE`

## Bases de datos

Usa dos conexiones:

- `PG_*`: base de control, staging, refresh y estados.
- `SRC241_*`: fuente para sincronizar catalogo de medicos.

## Systemd

Unidad observada en produccion:

```ini
[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
Unit=rpa-cext-mensual.service
```

`Persistent=true` implica que, si el timer estuvo apagado y se reactiva despues de un horario perdido, systemd puede disparar una ejecucion inmediata.

## Ejecucion de cierre mensual

Ejemplo operativo:

```bash
cd /home/cenate/rpa_cext_diario
source .venv/bin/activate
MES_A_PROCESAR=2026-05 CLOSE_MONTH=true CLOSE_MONTH_PERIOD=2026-05 ENV_FILE=.env_mensual python -u RPA_CEXT_PROD_MENSUAL.py
```

Uso:

- Reprocesar un mes completo despues de validaciones del Observatorio.
- Actualizar archivos que alimentan BI institucional.
- Guardar historico cerrado en BD.

Antes de ejecutarlo durante el dia, validar que no exista una corrida mensual en curso.
