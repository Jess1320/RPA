# Orquestador madrugada

Ejecuta en cadena los RPAs que alimentan el reporte de descargas de madrugada:

- RPA Mensual
- RPA Tele Triaje
- RPA Tele Urgencia
- RPA Medico y No Medico

El orquestador no reemplaza la logica interna de cada RPA. Solo controla orden, espera a que termine cada ejecucion, no detiene la cadena si un RPA falla y envia un unico correo consolidado.

## Reporte

El correo incluye:

- resumen general `OK` o `CON OBSERVACIONES`;
- mensaje sugerido para WhatsApp;
- tabla por RPA con inicio, fin, duracion, OK y fallas;
- detalle de incidencias con IPRESS, tipo, usuario logico, login enmascarado, fase y motivo;
- rutas de auditoria;
- adjuntos `reporte_madrugada.csv` y `reporte_madrugada.json`.

Los RPAs hijos se ejecutan con `MAIL_ENABLED=false` por defecto para evitar correos individuales durante la madrugada.

## Produccion

Ruta sugerida:

```text
/home/cenate/rpa_orquestador_madrugada
```

Timer:

```text
rpa-orquestador-madrugada.timer
```

Hora sugerida:

```text
01:00
```

Al activar este orquestador, se deben desactivar los timers individuales de los RPAs incluidos para evitar duplicados:

```text
rpa-cext-mensual.timer
rpa-tele-triaje.timer
rpa-tele-urgencia.timer
rpa-medico-no-medico.timer
```
