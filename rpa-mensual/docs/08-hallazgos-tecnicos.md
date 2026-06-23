# Hallazgos Tecnicos

## Estado general

La ultima ejecucion revisada fue exitosa a nivel operativo:

- `TOTAL_INPUT=104`
- `TOTAL_OK=104`
- `TOTAL_FAIL=0`
- Publicacion: `105` archivos para `104` centros OK
- `DRIVER_START_FAIL_COUNT=0`
- `TIMEOUT_COUNT=0`
- `FINAL_PUBLISH_RESULT` OK en principal y mirror
- `REFRESH_MENSUAL_ACTUAL` OK

## Diferencias de robustez frente al diario

El mensual todavia no incluye algunas protecciones recientes incorporadas al diario:

- Wrapper sin `flock`.
- Wrapper sin log de orquestador.
- Sin validacion explicita de ruta compartida antes de ejecutar.
- Sin preflight de ChromeDriver antes de limpiar/descargar.
- Sin logs de ChromeDriver por intento.

Como el mensual corre una vez al dia y no ha presentado fallas frecuentes, no es urgente tocar produccion, pero conviene llevar estas mejoras en una rama controlada.

## Fallback tecnico posiblemente mal ubicado

En la funcion `ejecutar_descargas_por_macro`, los errores tecnicos como `TIMEOUT_DESCARGA_PREFIJO`, `ARCHIVO_NO_ESTABLE`, `ARCHIVO_VACIO` o `EXCEPTION:*` parecen evaluarse en un `elif` asociado al caso `status == OK`. Eso hace que esos errores no entren al fallback tecnico como probablemente se pretendia.

Impacto:

- Si un centro falla por timeout o excepcion tecnica, podria no reintentarse correctamente con la misma macro.
- Hoy no impacto la corrida revisada porque no hubo timeouts ni fallas.

Recomendacion:

- Corregir la condicion para que los motivos tecnicos se evaluen dentro de `status != OK`.
- Agregar prueba o verificacion con resultado simulado.

## Warning de staging por campo grande

Existe evidencia de un archivo mensual descargado correctamente pero con fallo al cargar staging por limite de campo CSV.

Recomendacion:

- Agregar `csv.field_size_limit` alto al inicio del proceso.
- Si falla staging de un archivo, registrar estado final del archivo con claridad.
- Decidir si un `DB_FILE_WARN` debe degradar `SUCCESS` a `PARTIAL_SUCCESS`.

## Publicacion parcial

El mensual publica si `len(descargados_total_ordenado) > 0`, incluso cuando existen centros pendientes. Esto puede ser aceptable si se prioriza tener data parcial, pero para cierre mensual podria ser riesgoso.

Recomendacion:

- Definir politica: publicar parcial o exigir `TOTAL_FAIL=0`.
- Documentar esa decision en operacion.

## Publicacion de archivos sobrantes del periodo

En la corrida revisada hubo `TOTAL_OK=104`, pero `FINAL_PUBLISH_RESULT` reporto `temp_files=105` y `final_files=105`.

La funcion de publicacion mensual selecciona archivos por rango de fechas del periodo en la carpeta temporal, no exclusivamente por la lista de centros descargados en la corrida. Si queda un archivo adicional del mismo periodo en temporal, puede entrar al lote publicado.

Recomendacion:

- Antes de publicar, filtrar por centros esperados de la corrida.
- Registrar alerta cuando `final_files != TOTAL_OK`.
- Revisar la carpeta temporal si vuelve a aparecer diferencia entre centros OK y archivos publicados.
