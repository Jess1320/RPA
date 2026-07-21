# Contexto para IA - RPA Tele Urgencia

Leer este archivo antes de modificar el RPA.

## Objetivo

Descargar el archivo mensual de Tele Urgencia desde ExplotaDatos para los centros marcados en Google Sheets.

## Origen historico

Ruta local original:

```text
D:\RPA_TELE_URGENCIA
```

El script fue incorporado al repositorio sin `.env` real ni credenciales.

## Reglas

- No versionar `.env` reales ni JSON de Google.
- No cambiar rutas de publicacion sin revisar QA y produccion.
- No asumir exito solo por exit code `0`; revisar `run.log` y `summary.csv`.
- Mantener `ENV_FILE` para diferenciar QA y produccion.
- Usar `RPA_USERS_ENV_FILE` para credenciales maestras por macroregion; no volver a credenciales por RPA.
- Para produccion, exigir columna `MACRO` en Google Sheets con `REQUIRE_MACRO=true`.
- No agregar hilos hasta validar estabilidad en QA.

## Estado actual

Descarga/publica archivos y soporta reporte por correo via `MAIL_*`/`SMTP_*`. Todavia no registra estados en `rpa_control` ni alimenta panel.

## Archivos principales

```text
README.md
config/.env.example
docs/05-operacion-qa.md
scripts/run_rpa_tele_urgencia.sh
src/RPA_TELE_URGENCIA.py
```
