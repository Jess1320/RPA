# RPA Tele CAM

Descarga mensual de RPA Tele CAM desde ExplotaDatos para centros configurados directamente.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `TELE_CAM` |
| Nombre funcional | `RPA Tele CAM` |
| Entrada centros | `DIRECT_CENTERS=739` |
| Tipo de atencion | `2` |
| Mostrar por | `2` |
| Servicio | `F41` |
| Actividad | `A1` |
| Subactividad | `142` |
| Formato | `xls` |
| Sufijo esperado | `AtenNoMedxSubAct` |

## Ruta

- Formulario: `CtrlControl?opt=cext13`
- Carpeta final: `\\10.0.88.100\bbdd_rpa\Bases_TELECAM_2026`
- Equivalente Linux: `/mnt/BBDD_RPA/Bases_TELECAM_2026`

Este RPA publica directamente en la carpeta final. `USE_MONTH_SUBDIR=false` porque el periodo ya viene en el nombre del archivo.

## Publicacion segura

El RPA descarga primero en `STAGING_DOWNLOAD_DIR`, valida el archivo y recien publica en la ruta final.

Solo despues de validar el nuevo TXT se eliminan archivos finales del mismo centro, periodo y sufijo. No se eliminan archivos de otros periodos.

## Temporales

Cumple el estandar de perfiles temporales:

- `CHROME_PROFILE_BASE_DIR=tmp/chrome_profiles`
- `CHROME_PROFILE_MAX_AGE_HOURS=12`
- `CHROMEDRIVER_LOGS_ENABLED=false`

Cada driver usa un perfil `chrome-profile-*` propio y lo elimina en `finally`.
