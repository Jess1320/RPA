# Errores Conocidos

## Estado `PARTIAL_SUCCESS` falso

**Causa probable:** el estado final se calcula antes de actualizar los indicadores de refresh, reportes derivados o etapas complementarias.

**Validacion:**

- Total OK igual al total esperado.
- Total FAIL igual a cero.
- Publicacion final OK.
- Logs posteriores indican refresh OK.
- Correo o base conservan `PARTIAL_SUCCESS`.

**Accion recomendada:**

- Mover la derivacion oficial del estado al final real de la corrida.
- Recalcular una sola vez desde estados persistidos.
- Generar correo desde el snapshot final persistido.

## Posible solapamiento de ejecuciones

**Causa probable:** una ejecucion manual coincide con la automatica.

**Validacion:**

- Dos procesos Python activos.
- Dos carpetas temporales con corridas simultaneas.
- Logs con horarios superpuestos.

**Accion recomendada:**

- Usar `flock` en el wrapper Bash.
- Evaluar advisory lock de PostgreSQL.

## Cambio visual o funcional en ExplotaDatos

**Causa probable:** cambio en combo de IPRESS, formulario, URL interna o criterios del reporteador.

**Validacion:**

- Selenium no encuentra elementos.
- La URL interna ya no abre el formulario esperado.
- Los archivos descargados cambian de nombre, cabecera o contenido.

**Accion recomendada:**

- Validar manualmente ExplotaDatos.
- Confirmar URL interna del reporte.
- Actualizar selectores y criterios.
- Registrar el cambio en esta documentacion.

## Falla de credenciales

**Causa probable:** usuario, password o permisos expirados.

**Validacion:**

- Login rechazado.
- No aparece combo de IPRESS.
- Mensaje de sesion invalida o permisos insuficientes.

**Accion recomendada:**

- Validar credenciales fuera del RPA.
- Confirmar permisos por macroregion.
- Actualizar secreto fuera de Git.

## Falla masiva de ChromeDriver al iniciar

**Sintoma:**

```text
Service /usr/bin/chromedriver unexpectedly exited. Status code was: 1
```

**Impacto:**

- La corrida puede terminar con `TOTAL_OK=0` o con muy pocos centros descargados.
- No se publica informacion nueva.
- Los consumidores mantienen data anterior o quedan sin actualizacion esperada.

**Causa probable:**

Inestabilidad del entorno Chromium/ChromeDriver bajo ejecucion automatica, especialmente cuando se inician varios navegadores headless en paralelo o quedan procesos/restos de una corrida anterior.

**Validacion:**

- Revisar `summary.log` y `run.log`.
- Buscar `DRIVER_START_FAIL`.
- Revisar `tmp_chrome/chromedriver_logs/`.
- Verificar procesos activos de `chromedriver` y `chromium-browser`.

**Accion recomendada:**

- Mantener `MAX_CONCURRENT_DRIVER_STARTS=1`.
- Usar wrapper con `flock` para impedir solapamiento entre corrida automatica y manual.
- Ejecutar preflight de ChromeDriver antes de limpiar archivos o descargar.
- Mantener varios reintentos de arranque en preflight, porque la falla puede ser intermitente y resolverse segundos despues.
- Si el preflight falla, no continuar con los 104 centros.
- Registrar alerta y enviar correo aun cuando la corrida termine durante el preflight.

## Archivo descargado no carga a staging por campo extenso

**Sintoma:**

```text
DB_FILE_WARN | <archivo>.txt | Error: field larger than field limit (131072)
```

**Impacto:**

- El archivo puede estar descargado y publicado en la carpeta compartida.
- `raw.archivo_descargado` queda con `cargado_stg=false`.
- `stg.cext_prod_diario` no recibe filas de ese archivo.
- Las vistas basadas en la ultima corrida, como `ops.vw_cext_diaria_medicos_activos_full`, no muestran registros del centro afectado.

**Causa probable:**

El TXT contiene un campo muy largo y el limite por defecto del parser CSV de Python bloquea la carga a staging.

**Validacion:**

- Buscar `DB_FILE_WARN` en `summary.log` o `run.log`.
- Confirmar que el centro aparece como descargado en `raw.archivo_descargado`.
- Confirmar que no existen filas para `id_run` e `id_archivo` en `stg.cext_prod_diario`.

**Accion recomendada:**

- Mantener ampliado `csv.field_size_limit` en el script diario.
- Reejecutar el RPA o recargar el archivo afectado para que staging y las vistas se actualicen.

## Filas omitidas por interpretacion de comillas en TXT

**Sintoma:**

- El TXT abierto en Excel muestra registros que no aparecen en `stg.cext_prod_diario` ni en las vistas.
- La cantidad de filas cargadas a staging es menor que la cantidad real de lineas del TXT.
- Al buscar un profesional por `DNI_MEDICO`, el TXT crudo contiene registros, pero la base devuelve cero.

**Causa probable:**

El archivo de ExplotaDatos es un texto delimitado plano por `|`. Si Python lo lee como CSV estandar, una comilla no balanceada dentro de algun campo puede hacer que el parser una varias lineas y omita registros posteriores.

**Validacion:**

- Comparar el conteo con `csv.reader(..., quoting=csv.QUOTE_NONE)` contra el parser estandar.
- Revisar el TXT crudo por columna, no solo por busqueda global del documento.

**Accion recomendada:**

- Leer los TXT de ExplotaDatos con `quoting=csv.QUOTE_NONE`.
- Reprocesar o esperar una nueva corrida para que staging y las vistas reflejen todas las filas.
