# Contexto para IA - RPA Medico y No Medico

Leer este archivo antes de modificar el RPA.

## Objetivo

Descargar archivos mensuales separados para los procesos `MEDICO` y `NO_MEDICO`.

## Origen historico

Ruta local original:

```text
D:\RPA_DX_MED_NMED
```

Ese nombre solo debe usarse como referencia historica. Para produccion usar `RPA Medico y No Medico`, `MEDICO_NO_MEDICO`, `rpa-medico-no-medico`, `RPA_MEDICO_NO_MEDICO.py`.

## Reglas

- No nombrar este RPA como `DX` en produccion.
- No confundirlo con `rpa_dx_maestro`.
- Una corrida es correcta solo si cada centro descarga todos los tipos habilitados.
- No versionar `.env` reales ni JSON de Google.
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
scripts/run_rpa_medico_no_medico.sh
src/RPA_MEDICO_NO_MEDICO.py
```
