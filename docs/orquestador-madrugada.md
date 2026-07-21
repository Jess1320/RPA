# Orquestador madrugada

Fecha de activacion: 2026-07-04

## Objetivo

Consolidar en un solo correo el resultado de las descargas nocturnas:

- RPA Mensual
- RPA Tele Triaje
- RPA Tele Urgencia
- RPA Medico y No Medico
- RPA Tele Proad
- RPA Tele Psicoprofilaxis
- RPA TAD

## Modelo operativo

El servidor productivo ejecuta un unico timer:

```text
rpa-orquestador-madrugada.timer
```

Hora:

```text
01:00
```

Los timers individuales incluidos en la cadena quedan deshabilitados para evitar duplicados:

```text
rpa-cext-mensual.timer
rpa-tele-triaje.timer
rpa-tele-urgencia.timer
rpa-medico-no-medico.timer
```

## Regla de inicio de mes

La cadena de madrugada tiene una regla especial para cierre mensual. Cuando el dia de ejecucion coincide con `MONTH_START_CLOSE_DAYS` y `MONTH_START_CLOSE_ENABLED=true`, el orquestador ejecuta dos fases:

1. `CIERRE_MES_ANTERIOR`: todos los RPAs activos descargan el mes anterior completo con `MES_A_PROCESAR=ANTERIOR`.
2. `MES_ACTUAL`: todos los RPAs activos descargan el mes actual con `MES_A_PROCESAR=ACTUAL`.

El orden es global: primero se completan todos los cierres del mes anterior y luego se ejecutan todos los RPAs del mes actual. Si una ejecucion falla, la siguiente continua y el correo consolidado indica la fase, el periodo y el detalle de la incidencia.

Para el RPA Mensual, la fase `CIERRE_MES_ANTERIOR` tambien recibe `CLOSE_MONTH=true` y `CLOSE_MONTH_PERIOD=YYYY-MM` del mes anterior.

Para no tocar descargas de meses ya cerrados, el orquestador guarda un candado por periodo y por RPA en `MONTH_START_CLOSE_LOCK_DIR`. Cuando un RPA termina OK en `CIERRE_MES_ANTERIOR`, ese periodo queda marcado como cerrado para ese RPA. Si se vuelve a ejecutar el orquestador, el cierre de ese RPA se omite y solo se reintentan los cierres que no tengan candado.

Variables:

```text
MONTH_START_CLOSE_LOCK_ENABLED=true
MONTH_START_CLOSE_LOCK_DIR=state/month_start_close
MONTH_START_CLOSE_FORCE=false
```

`MONTH_START_CLOSE_FORCE=true` solo debe usarse manualmente si se autoriza reprocesar un periodo ya cerrado.

## Reporte por correo

El correo consolidado contiene:

- estado general `OK` o `CON OBSERVACIONES`;
- mensaje listo para usar como base del reporte por WhatsApp;
- tabla por RPA con fase, periodo, inicio, fin, duracion, total OK y total fallas;
- detalle de incidencias por IPRESS;
- tipo de descarga cuando aplique;
- usuario logico, por ejemplo `MACRO_CENTRO`;
- login enmascarado, por ejemplo `us***ro`;
- motivo y fase de falla;
- rutas de auditoria.

Adjuntos:

```text
reporte_madrugada.csv
reporte_madrugada.json
```

## Regla de continuidad

Si un RPA falla, el orquestador registra la falla y continua con el siguiente. El objetivo es llegar al correo de las 08:00 con el estado completo de toda la madrugada, no detener la cadena en la primera falla.
