# Contexto para IA - RPA Tele Proad

## Objetivo

Descargar dos reportes mensuales de Tele Proad por IPRESS marcada en Google Sheets:

- `HOSPITALIZACION`: `CtrlControl?opt=hosinterser`, sufijo `IntercxServ`.
- `EMERGENCIA`: `CtrlControl?opt=emerinterconsulta`, sufijo `EmerInterconsultaxServ`.

Ambas rutas usan el servicio `AJ1` (`ENF.INFEC.Y TROPIC.`), seleccionado siempre por `value`, no por texto visible.

## Entradas

- Spreadsheet compartido del proyecto.
- Pestaña `TELE_PROAD`.
- Credenciales maestras desde `../shared/config/.env_usuarios`.
- Macroregion por IPRESS igual que los otros RPAs.

## Salidas

- Hospitalizacion: `/mnt/BD_CControl/BASE TELEPROA 2026/HOSPITALIZACION`.
- Emergencia: `/mnt/BD_CControl/BASE TELEPROA 2026/EMERGENCIAS`.

## Regla de publicacion

No descargar directo a la carpeta final. Descargar en staging, validar y luego publicar.

No eliminar periodos antiguos. Solo reemplazar archivos del mismo centro, mismo periodo y mismo sufijo despues de tener la nueva descarga validada.

## Temporales

Debe cumplir `docs/estandar-perfiles-chrome-selenium.md`.
