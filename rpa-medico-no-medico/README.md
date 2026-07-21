# RPA Medico y No Medico

## Resumen

Descarga archivos mensuales separados para el proceso Medico y No Medico desde ExplotaDatos.

Este RPA viene de la ruta local historica `D:\RPA_DX_MED_NMED`, pero en produccion no debe nombrarse como `DX` para evitar confusion con `rpa_dx_maestro` y otros RPAs de diagnostico.

## Datos principales

| Campo | Valor |
| --- | --- |
| Codigo del job | `MEDICO_NO_MEDICO` |
| Nombre funcional | `RPA Medico y No Medico` |
| Sistema origen | ESSI / ExplotaDatos |
| Fuente funcional | Google Sheets |
| Salidas | `DxMedSer.txt` y `DxNoMedSer.txt` |
| Frecuencia actual | Diaria en madrugada |
| Hora local actual | 02:30 |
| Estado actual | Descarga y publicacion de archivos |

## Flujo

1. Carga configuracion desde `.env` o `ENV_FILE`.
2. Carga usuarios maestros por macroregion desde `RPA_USERS_ENV_FILE` o `shared/config/.env_usuarios`.
3. Lee centros/IPRESS marcados en Google Sheets para el mes objetivo y su `MACRO`.
4. Ingresa a ExplotaDatos con el usuario maestro asignado a la macroregion.
5. Selecciona centro/IPRESS.
6. Descarga el archivo para `MEDICO` si `RUN_MEDICO=true`.
7. Descarga el archivo para `NO_MEDICO` si `RUN_NO_MEDICO=true`.
8. Valida nombre, estabilidad y archivo no vacio.
9. Registra `run.log`.

## Credenciales y macroregion

El RPA usa los mismos usuarios maestros de Diario y Mensual:

```text
USER_CENTRO / PASSWORD_CENTRO
USER_NORTE / PASSWORD_NORTE
USER_SUR / PASSWORD_SUR
USER_LIMA_ORIENTE / PASSWORD_LIMA_ORIENTE
```

La hoja debe incluir columna `MACRO` para produccion. En QA se permite `REQUIRE_MACRO=false` y `DEFAULT_MACRO=CENTRO` solo como transicion.

## Criterio de exito

Una corrida solo debe considerarse correcta si todos los centros configurados descargan todos los tipos habilitados. Si un centro descarga `MEDICO` pero falla `NO_MEDICO`, el centro debe quedar fallido.

## Limitaciones actuales

- No registra aun en PostgreSQL `rpa_control`.
- Envia reporte de corrida por correo cuando `MAIL_ENABLED=true`.
- No expone `data_ready` para panel.
- No tiene carga a staging; solo descarga/publica archivos.

## Documentacion

- [Contexto para IA](AI_CONTEXT.md)
- [Operacion QA](docs/05-operacion-qa.md)
