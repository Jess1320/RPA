# Contexto para IA - RPA Tele CAM

## Objetivo

Descargar el reporte mensual de RPA Tele CAM por IPRESS configurada en entrada directa.

Formulario:

- `CtrlControl?opt=cext13`

Selecciones por `value`:

- `tipoReporte=2`
- `tipo=2`
- `servicio=F41`
- `actividad=A1`
- `subactividad=142`
- `formatoArchivo=xls`

## Entradas

- Entrada directa `DIRECT_CENTERS`, inicialmente `739`.
- Credenciales maestras desde `../shared/config/.env_usuarios`.
- Macroregion por IPRESS igual que los otros RPAs.

## Salidas

- Final Windows: `\\10.0.88.100\bbdd_rpa\Bases_TELECAM_2026`.
- Final Linux: `/mnt/BBDD_RPA/Bases_TELECAM_2026`.
- Sufijo esperado: `AtenNoMedxSubAct`.

`DOWNLOAD_DIR` debe estar vacio en produccion. La ruta final se resuelve con `DOWNLOAD_DIR_BASE` y `USE_MONTH_SUBDIR=false`.

## Regla de publicacion

No descargar directo a la carpeta final. Descargar en staging, validar y luego publicar.

No eliminar periodos antiguos. Solo reemplazar archivos del mismo centro, mismo periodo y mismo sufijo despues de tener la nueva descarga validada.

## Temporales

Debe cumplir `docs/estandar-perfiles-chrome-selenium.md`.
