# RPA Tele Triaje

## Resumen

Descarga archivos mensuales de Tele Triaje desde ExplotaDatos para las IPRESS marcadas en Google Sheets.

Este RPA viene de la ruta local historica `D:\RPA_TELE_TRIAJE` y queda preparado para pruebas en QA antes de pasar a produccion.

## Datos principales

| Campo | Valor |
| --- | --- |
| Codigo del job | `TELE_TRIAJE` |
| Sistema origen | ESSI / ExplotaDatos |
| Fuente funcional | Google Sheets |
| Salida principal | `PacAtenTriaje.txt` |
| Frecuencia actual | Diaria en madrugada |
| Hora local actual | 03:00 |
| Estado actual | Descarga y publicacion de archivos |

## Flujo

1. Carga configuracion desde `.env` o `ENV_FILE`.
2. Carga usuarios maestros por macroregion desde `RPA_USERS_ENV_FILE` o `shared/config/.env_usuarios`.
3. Lee centros/IPRESS marcados en Google Sheets para el mes objetivo y su `MACRO`.
4. Ingresa a ExplotaDatos con el usuario maestro asignado a la macroregion.
5. Selecciona centro/IPRESS.
6. Navega al formulario de Tele Triaje.
7. Descarga el archivo mensual.
8. Valida nombre, sufijo, estabilidad y archivo no vacio.
9. Registra `run.log` y `summary.csv`.

## Credenciales y macroregion

El RPA usa los mismos usuarios maestros de Diario y Mensual:

```text
USER_CENTRO / PASSWORD_CENTRO
USER_NORTE / PASSWORD_NORTE
USER_SUR / PASSWORD_SUR
USER_LIMA_ORIENTE / PASSWORD_LIMA_ORIENTE
```

La hoja debe incluir columna `MACRO` para produccion. En QA se permite `REQUIRE_MACRO=false` y `DEFAULT_MACRO=CENTRO` solo como transicion.

## Limitaciones actuales

- No registra aun en PostgreSQL `rpa_control`.
- Envia reporte de corrida por correo cuando `MAIL_ENABLED=true`.
- No expone `data_ready` para panel.
- No tiene carga a staging; solo descarga/publica archivos.

## Documentacion

- [Contexto para IA](AI_CONTEXT.md)
- [Operacion QA](docs/05-operacion-qa.md)
