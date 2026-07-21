# RPA Tele Psicoprofilaxis

Descarga mensual de Tele Psicoprofilaxis desde ExplotaDatos para centros marcados en la pestaña `TELE_PSI`.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `TELE_PSICOPROFILAXIS` |
| Nombre funcional | `RPA Tele Psicoprofilaxis` |
| Spreadsheet tab | `TELE_PSI` |
| Tipo de atencion | `2` |
| Mostrar por | `2` |
| Servicio | `F21` |
| Actividad | `A1` |
| Subactividad | `142` |
| Formato | `xls` |
| Sufijo esperado | `AtenNoMedxSubAct` |

## Ruta

- Formulario: `CtrlControl?opt=cext13`
- Carpeta base: `/mnt/BD_CControl/BASE TCEX 2026/OBSTETRICIA`
- Carpeta mensual: `MM. MES`, por ejemplo `07. JULIO`

Este RPA publica en una subcarpeta distinta por mes. `DOWNLOAD_DIR` debe quedar vacio y la ruta se calcula con `DOWNLOAD_DIR_BASE` + `MM. MES`; si la carpeta mensual no existe, el RPA la crea antes de publicar.

## Publicacion segura

El RPA descarga primero en `STAGING_DOWNLOAD_DIR`, valida el archivo y recien publica en la ruta final.

Solo despues de validar el nuevo TXT se eliminan archivos finales del mismo centro, periodo y sufijo. No se eliminan archivos de otros periodos.

## Temporales

Cumple el estandar de perfiles temporales:

- `CHROME_PROFILE_BASE_DIR=tmp/chrome_profiles`
- `CHROME_PROFILE_MAX_AGE_HOURS=12`
- `CHROMEDRIVER_LOGS_ENABLED=false`

Cada driver usa un perfil `chrome-profile-*` propio y lo elimina en `finally`.
