# Contexto para IA - RPA Tele Psicoprofilaxis

## Objetivo

Descargar el reporte mensual de Tele Psicoprofilaxis por IPRESS marcada en Google Sheets.

Formulario:

- `CtrlControl?opt=cext13`

Selecciones por `value`:

- `tipoReporte=2`
- `tipo=2`
- `servicio=F21`
- `actividad=A1`
- `subactividad=142`
- `formatoArchivo=xls`

## Entradas

- Spreadsheet compartido del proyecto.
- Pestaña `TELE_PSI`.
- Credenciales maestras desde `../shared/config/.env_usuarios`.
- Macroregion por IPRESS igual que los otros RPAs.

## Salidas

- Base: `/mnt/BD_CControl/BASE TCEX 2026/OBSTETRICIA`.
- Subcarpeta mensual: `MM. MES`.
- Sufijo esperado: `AtenNoMedxSubAct`.

`DOWNLOAD_DIR` debe estar vacio en produccion para no fijar un mes. La ruta final se resuelve con `DOWNLOAD_DIR_BASE` y `USE_MONTH_SUBDIR=true`; el RPA crea la subcarpeta mensual si no existe.

## Regla de publicacion

No descargar directo a la carpeta final. Descargar en staging, validar y luego publicar.

No eliminar periodos antiguos. Solo reemplazar archivos del mismo centro, mismo periodo y mismo sufijo despues de tener la nueva descarga validada.

## Temporales

Debe cumplir `docs/estandar-perfiles-chrome-selenium.md`.
