# RPA Tele Proad

Descarga mensual de Tele Proad desde ExplotaDatos para centros marcados en la pestaña `TELE_PROAD`.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `TELE_PROAD` |
| Nombre funcional | `RPA Tele Proad` |
| Spreadsheet tab | `TELE_PROAD` |
| Servicio | `AJ1` |
| Formato | `xls` |
| Rutas | `HOSPITALIZACION`, `EMERGENCIA` |

## Rutas

- Hospitalizacion: `CtrlControl?opt=hosinterser`
- Emergencia: `CtrlControl?opt=emerinterconsulta`

## Publicacion segura

El RPA no descarga directamente sobre las carpetas finales. Cada intento descarga primero en `STAGING_DOWNLOAD_DIR`, valida el archivo y recien publica en la ruta final.

Solo despues de validar el nuevo TXT se eliminan archivos finales del mismo centro, periodo y sufijo. No se eliminan archivos de otros periodos.

Sufijos esperados:

- `IntercxServ`
- `EmerInterconsultaxServ`

## Temporales

Cumple el estandar de perfiles temporales:

- `CHROME_PROFILE_BASE_DIR=tmp/chrome_profiles`
- `CHROME_PROFILE_MAX_AGE_HOURS=12`
- `CHROMEDRIVER_LOGS_ENABLED=false`

Cada driver usa un perfil `chrome-profile-*` propio y lo elimina en `finally`.
