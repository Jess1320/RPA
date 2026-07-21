# Configuracion

## Archivo real

Produccion usa `.env_mensual` en `/home/cenate/rpa_cext_diario`. Ese archivo no debe versionarse porque contiene credenciales y rutas internas.

## Variables principales

| Variable | Uso |
| --- | --- |
| `URL_HOME` | Entrada al reporteador ExplotaDatos |
| `FRM_MASIVAS` | URL interna del formulario `PacCitCExt` |
| `INPUT_SOURCE` | Fuente funcional de centros: `GSHEET` o `DB_VIEW` |
| `GSHEET_URL` | Spreadsheet con centros/IPRESS, usado si `INPUT_SOURCE=GSHEET` |
| `CREDS_JSON` | Credencial de servicio Google, usado si `INPUT_SOURCE=GSHEET` |
| `GSHEET_TABS` | Tabs a leer, separadas por coma, usado si `INPUT_SOURCE=GSHEET` |
| `DB_VIEW_NAME` | Vista con centros objetivo, usado si `INPUT_SOURCE=DB_VIEW` |
| `INPUT_DB_HOST` | Host de la base donde vive la vista de centros |
| `INPUT_DB_PORT` | Puerto PostgreSQL de la fuente de centros |
| `INPUT_DB_DATABASE` | Base de datos de la fuente de centros, normalmente `maestro_cenate` |
| `INPUT_DB_USER` | Usuario de lectura para la fuente de centros |
| `INPUT_DB_PASSWORD` | Password del usuario de lectura para la fuente de centros |
| `MES_A_PROCESAR` | Mes objetivo: `ACTUAL`, `ANTERIOR`, `SIGUIENTE`, `YYYY-MM` |
| `DOWNLOAD_DIRS` | Rutas temporales de descarga |
| `FINAL_PUBLISH_DIR` | Carpeta principal de publicacion mensual |
| `FINAL_PUBLISH_MIRRORS` | Carpetas espejo |
| `FINAL_PUBLISH_REPLACE_PERIOD` | Si es `true`, reemplaza todo el periodo en carpeta final; si es `false`, actualiza solo archivos descargados OK |
| `FILE_SUFFIX` | Sufijo esperado, normalmente `PacCitCExt.txt` |
| `FORCE_REDOWNLOAD` | Si es `true`, elimina archivos del TAG antes de descargar |
| `KEEP_ONLY_CURRENT_TAG` | Limpieza por TAG vigente |
| `HEADLESS` | Ejecuta navegador sin UI |
| `DOWNLOAD_TIMEOUT` | Timeout por descarga |
| `MAX_THREADS` | Paralelismo por macro |
| `MAX_CONCURRENT_DRIVER_STARTS` | Limite de arranques simultaneos de ChromeDriver |
| `HEALTHCHECK_ENABLED` | Activa validacion previa de usuario/macro |
| `HEALTHCHECK_BLOCKING` | Bloquea macro si credencial falla |
| `OVERRIDES_ENABLED` | Usa overrides aprendidos de centro/macro efectiva |
| `FALLBACK_ENABLED` | Intenta usuarios maestros alternativos cuando falla la macro declarada |
| `OVERRIDE_LEARNING_ENABLED` | Registra nuevos aprendizajes de macro efectiva |
| `STAGING_LOAD_ENABLED` | Registra y carga TXT a staging mensual |
| `REFRESH_MENSUAL_ENABLED` | Ejecuta sincronizacion, refresh mensual, poda staging y cierre si aplica |
| `DB_PRECHECK_ENABLED` | Valida puerto PostgreSQL antes de correr |
| `RPA_FAIL_IF_DB_DOWN` | Falla la corrida si no hay control DB |
| `CLOSE_MONTH` | Ejecuta cierre mensual si esta activo |
| `CLOSE_MONTH_PERIOD` | Periodo a cerrar; si esta vacio usa el periodo procesado |
| `MAIL_ENABLED` | Activa notificacion por correo |

## Credenciales por macro

El mensual usa los mismos usuarios maestros que Diario y los demas RPAs de descarga. Deben quedar en un archivo privado compartido, no duplicados por RPA:

```text
shared/config/.env_usuarios
```

Tambien se puede definir otra ruta con `RPA_USERS_ENV_FILE`.

Variables esperadas:

- `USER_CENTRO` / `PASSWORD_CENTRO`
- `USER_NORTE` / `PASSWORD_NORTE`
- `USER_SUR` / `PASSWORD_SUR`
- `USER_LIMA_ORIENTE` / `PASSWORD_LIMA_ORIENTE`

El `.env_mensual` puede conservar credenciales antiguas por compatibilidad, pero el archivo maestro tiene prioridad cuando existe.

## Bases de datos

Usa dos conexiones:

- `PG_*`: base de control, staging, refresh y estados.
- `SRC241_*`: fuente para sincronizar catalogo de medicos.
- `INPUT_DB_*`: fuente funcional de centros/IPRESS cuando `INPUT_SOURCE=DB_VIEW`.

## Fuente DB View mensual

Para que el mensual deje de depender de Google Sheets:

```text
INPUT_SOURCE=DB_VIEW
DB_VIEW_NAME=essi.vw_rpa_mensual_centros_objetivo_v1
INPUT_DB_DATABASE=maestro_cenate
```

La vista esperada es:

```sql
SELECT *
FROM essi.vw_rpa_mensual_centros_objetivo_v1
WHERE activo = true
ORDER BY desc_macro, desc_red, codigo_centro;
```

Columnas minimas para el RPA:

- `codigo_centro`
- `desc_macro`

Columnas adicionales usadas para trazabilidad:

- `desc_red`
- `ipress`
- `cod_ori_ipress`
- `total_programaciones`
- `total_profesionales`
- `estado_prioritario`

La vista incluye programaciones aprobadas, bloqueadas y suspendidas. No consulta citas, no llena `stg_citas_preconfirmadas` y no modifica `dim_solicitud_bolsa`.

La vista ya viene filtrada para Consulta Externa y Areas Administrativas. El RPA Mensual CEXT debe tratarla como fuente autoritativa de centros objetivo y no debe incorporar Ayuda al Diagnostico ni Urgencia/Emergencia en este flujo, porque esos alcances corresponden a otros RPAs.

## Modo diagnostico de accesos

Cuando se necesite identificar centros/IPRESS que aun no estan habilitados en el usuario maestro de su macroregion declarada, ejecutar con:

```text
INPUT_SOURCE=DB_VIEW
OVERRIDES_ENABLED=false
FALLBACK_ENABLED=false
OVERRIDE_LEARNING_ENABLED=false
STAGING_LOAD_ENABLED=false
REFRESH_MENSUAL_ENABLED=false
FINAL_PUBLISH_REPLACE_PERIOD=false
CLOSE_MONTH=false
```

Este modo fuerza que cada centro se pruebe solo con el usuario maestro de su `desc_macro` declarada en la vista. No usa aprendizajes previos, no busca con usuarios alternativos y no aprende nuevas asociaciones. Tambien publica solo los TXT descargados correctamente sin borrar archivos previos de centros que fallen en esa corrida. El objetivo es obtener una lista limpia para solicitar habilitacion.

Para pedir accesos al area responsable, reportar por cada centro fallido:

- codigo de IPRESS / centro
- nombre de IPRESS / centro
- red asistencial
- macroregion
- usuario maestro al que debe habilitarse

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
