# RPA TAD

Descarga de Tele Apoyo al Diagnostico desde ExplotaDatos para los centros marcados en la pestaña `TAD`.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `TAD` |
| Nombre funcional | `RPA TAD` |
| Spreadsheet tab | `TAD` |
| Rango | Primer dia del mes hasta ultimo dia del mes |
| Formato | `xls` |
| Rutas | `RESULTADO_TIPO_EXAMEN`, `TRATAMIENTO_PENDIENTES`, `TRATAMIENTO_ASIGNADOS` |

## Formularios

- Resultado por Tipo de Examen: `CtrlControl?opt=ayudaDx04A_B`
- Tratamiento de Imagenes - Pendientes: `CtrlControl?opt=atentraimagPen`
- Tratamiento de Imagenes - Asignados: `CtrlControl?opt=atentraimagAsig`

## Selecciones

- Tipo de Examen: `1`
- Area: `00`
- Servicio: `00`
- Tipo Archivo: `xls`

Las selecciones se hacen por `value`, no por texto visible.

## Publicacion segura

El RPA no descarga directamente sobre las carpetas finales. Cada intento descarga primero en `STAGING_DOWNLOAD_DIR`, valida el archivo y recien publica en la ruta final.

Solo despues de validar el nuevo TXT se eliminan archivos finales del mismo centro, periodo y sufijo. No se eliminan archivos de otros periodos.

Sufijos descargados esperados:

- `ResulExam_Imagen`
- `TratImagenesPendientes`
- `TratImagenesAsignados`

La ruta `RESULTADO_TIPO_EXAMEN` se publica renombrada con el mes: `COD_YYYYMM01_YYYYMMDD_MES.txt`.

## Temporales

Cumple el estandar de perfiles temporales:

- `CHROME_PROFILE_BASE_DIR=tmp/chrome_profiles`
- `CHROME_PROFILE_MAX_AGE_HOURS=12`
- `CHROMEDRIVER_LOGS_ENABLED=false`

Cada driver usa un perfil `chrome-profile-*` propio y lo elimina en `finally`.
