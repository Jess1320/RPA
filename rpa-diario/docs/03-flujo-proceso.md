# Flujo del Proceso

## Cadena de ejecucion

```text
systemd timer
  -> systemd service
    -> run_rpa_diario.sh
      -> entorno virtual Python
        -> RPA_CEXT_PROD_DIARIO.py
```

## Etapas logicas

1. `CONFIGURATION`
2. `CONTROL_DB_INIT`
3. `SOURCE_SELECTION`
4. `DOWNLOAD`
5. `STAGING_LOAD`
6. `PUBLICATION`
7. `MEDICAL_STAFF_SYNC`
8. `REPORT_REFRESH`
9. `STAGING_PRUNE`
10. `STATE_FINALIZATION`
11. `NOTIFICATION`

## Flujo por centro/IPRESS

1. Leer codigo de centro/IPRESS desde Google Sheets.
2. Determinar macroregion y credencial aplicable.
3. Iniciar sesion en ExplotaDatos.
4. Seleccionar centro/IPRESS en el combo.
5. Navegar a la URL interna del reporte `PacCitCExt`.
6. Completar rango de fechas y criterios.
7. Solicitar generacion del reporte.
8. Esperar descarga.
9. Validar nombre, TAG, sufijo, tamano y estabilidad del archivo.
10. Registrar resultado por centro/IPRESS.
11. Cargar archivo a staging.

## Flujo posterior a descargas

1. Ejecutar retry y fallback de centros pendientes.
2. Publicar archivos mediante staging y swap.
3. Sincronizar catalogo de medicos.
4. Ejecutar refresh de reportes diarios.
5. Podar staging si corresponde.
6. Persistir estados finales.
7. Derivar `overall_status`.
8. Marcar `data_ready` si aplica.
9. Enviar notificacion.

