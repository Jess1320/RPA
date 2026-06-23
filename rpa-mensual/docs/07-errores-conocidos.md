# Errores Conocidos

## `DB_FILE_WARN | field larger than field limit`

**Sintoma:**

```text
DB_FILE_WARN | <archivo> | Error: field larger than field limit (131072)
```

**Impacto:**

- La descarga puede quedar OK.
- La publicacion puede quedar OK.
- La carga del archivo afectado a staging puede quedar incompleta o no cargada.

**Evidencia observada:**

En la corrida `RUN_CEXT_PROD_MENSUAL_20260623_040037` ocurrio con:

```text
406_20260601_20260630_PacCitCExt.txt
```

**Causa probable:**

El parser CSV de Python encuentra un campo individual mayor al limite por defecto.

**Accion recomendada:**

- Aumentar `csv.field_size_limit`.
- Registrar el archivo como no cargado a staging si falla.
- Validar si el refresh mensual depende de ese archivo cargado o de la publicacion TXT.

## Falla de ChromeDriver

El mensual incorpora preflight de ChromeDriver y logs por intento. Si aparece falla, revisar:

```text
<CHROME_PROFILE_BASE_DIR>/chromedriver_logs/
```

**Accion recomendada:**

- Confirmar `CHROMEDRIVER_PREFLIGHT_OK`.
- Revisar `DRIVER_START_FAIL`.
- Mantener `MAX_CONCURRENT_DRIVER_STARTS=1` si aparecen fallas intermitentes.

## Timer con `Persistent=true`

Si el timer estuvo detenido y se reactiva despues de un horario perdido, systemd puede ejecutar el servicio inmediatamente.

**Accion recomendada:**

- Antes de reactivar, revisar si ya existe una corrida manual o reciente.
- Si no se desea ejecucion inmediata, evaluar procedimiento controlado con stop del servicio tras restart o ajustar temporalmente el timer.

## Publicacion parcial

Si hay centros fallidos pero al menos uno OK, el RPA publica el lote disponible y marca `FINAL_PUBLISH_PARTIAL`.

**Riesgo:**

La carpeta final puede quedar con un mes incompleto si se acepta una corrida parcial.

**Accion recomendada:**

- Definir si mensual debe bloquear publicacion cuando `TOTAL_FAIL > 0`.
- Si la politica exige mes completo, ajustar la condicion de publicacion.

## Filas omitidas por interpretacion de comillas en TXT

**Sintoma:**

- El TXT abierto en Excel muestra registros que no aparecen en staging mensual.
- La cantidad de filas cargadas es menor que la cantidad real de lineas del TXT.
- Un profesional aparece en el archivo crudo, pero no aparece al consultar la base.

**Causa probable:**

El archivo de ExplotaDatos es texto delimitado plano por `|`. Si Python lo interpreta como CSV estandar, una comilla no balanceada dentro de un campo puede unir varias lineas y omitir registros.

**Accion recomendada:**

- Leer los TXT con `quoting=csv.QUOTE_NONE`.
- Reprocesar el periodo afectado si la diferencia impacta reportes o cierre mensual.
