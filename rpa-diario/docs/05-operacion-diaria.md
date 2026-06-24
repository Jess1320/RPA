# Operacion Diaria

## Programacion

El RPA se ejecuta mediante systemd durante la ventana aproximada de 07:00 a 22:00. La mayoria de corridas se programa cada 30 minutos, con algunos intervalos mayores para evitar colisiones.

## Ejecucion manual

La ejecucion manual debe respetar el mismo bloqueo que la ejecucion automatica para evitar solapamientos.

```bash
systemctl start rpa-diario.service
```

O, si se ejecuta por wrapper:

```bash
/home/cenate/rpa_cext_diario/run_rpa_diario.sh
```

El wrapper versionado valida:

- Existencia del Python del entorno virtual.
- Existencia del script principal.
- Montaje de `/mnt/abandonos`.
- Bloqueo exclusivo con `flock`.
- Registro en `orchestrator_logs`.
- Reintento automatico controlado si el script sale con codigo `4` por `CHROMEDRIVER_PREFLIGHT_FAIL`.

## Validacion de una corrida correcta

Una corrida correcta debe cumplir:

- Total de centros/IPRESS esperados procesados.
- Archivos descargados y validados.
- Staging cargado.
- Publicacion final OK.
- Refresh de reportes OK.
- `overall_status = SUCCESS` o `SUCCESS_WITH_WARNINGS`.
- `data_ready = true`.
- Correo enviado o registrado como warning no critico.

En una corrida con descargas y publicacion correctas debe aparecer en `summary.log` un evento `REFRESH_REPORTES_DIARIO` antes de `RUN_END`. Si aparece `REFRESH_REPORTES_DIARIO_SKIP`, revisar el motivo indicado.

Antes de limpiar archivos o iniciar descargas, la version controlada ejecuta un preflight de ChromeDriver. Si falla, se registra `CHROMEDRIVER_PREFLIGHT_FAIL` y la corrida termina sin borrar los archivos del TAG.

Si el preflight de ChromeDriver falla, la corrida debe quedar como `FAILED`, registrar alerta `CHROMEDRIVER_PREFLIGHT_FAIL` y enviar correo con el log adjunto. Si no llega correo, revisar `MAIL_SEND_WARN` o `MAIL_SEND_SKIP` en `run.log`.

Como escudo operativo, el wrapper relanza la corrida cuando el Python termina con codigo `4`, reservado para fallo temprano de preflight. El reintento ocurre antes de cualquier limpieza o descarga efectiva del siguiente intento. No reintenta fallas de descarga, staging, publicacion, refresh ni base de datos.

Variables del wrapper:

- `PREFLIGHT_RETRY_EXIT_CODE`: codigo que dispara reintento; por defecto `4`.
- `PREFLIGHT_RETRY_MAX`: cantidad de reintentos luego del primer intento; por defecto `2`.
- `PREFLIGHT_RETRY_DELAY_SECONDS`: espera antes del reintento; por defecto `120`.

Antes de cada relanzamiento por preflight, el wrapper limpia procesos `chromedriver` del usuario y perfiles temporales de preflight bajo `tmp_chrome` para reducir residuos del intento fallido.

El wrapper tambien evita corridas redundantes muy cercanas: si detecta una corrida completa con `TOTAL_FAIL=0`, publicacion final OK, refresh OK y `RUN_END` dentro de los ultimos `RECENT_SUCCESS_SKIP_MINUTES` minutos, salta la nueva ejecucion con salida exitosa. Por defecto son `10` minutos.

## Revision ante falla

1. Revisar log de corrida.
2. Revisar `summary.log`.
3. Consultar estado persistido en PostgreSQL.
4. Identificar etapa fallida.
5. Validar si hay archivos temporales incompletos.
6. Confirmar si la carpeta compartida fue publicada.
7. Revisar si hubo timeout, falla de ChromeDriver, cambio de cabecera o error de credenciales.
8. Buscar `DB_FILE_WARN`; si existe, el archivo puede haberse descargado y publicado, pero no cargado a staging.

Para incidentes de ChromeDriver revisar tambien:

- `tmp_chrome/chromedriver_logs/`
- Conteo de procesos `chromedriver` y `chromium-browser`.
- Variable `MAX_CONCURRENT_DRIVER_STARTS`; en produccion se recomienda `1`.
