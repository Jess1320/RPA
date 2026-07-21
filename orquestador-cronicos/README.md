# Orquestador Cronicos

Orquesta las descargas diurnas para el equipo de Cronicos. No reemplaza ni modifica `orquestador-madrugada`.

## Horarios

```ini
OnCalendar=*-*-* 08:00:00
OnCalendar=*-*-* 11:00:00
OnCalendar=*-*-* 12:45:00
OnCalendar=*-*-* 16:00:00
Persistent=false
```

## Orden

```text
PROG_PROF
MENSUAL_CRONICOS
```

## Criterio operativo

El correo consolidado indica si quedaron listas:

- las descargas de programacion de profesionales (`RPA Prog Prof`);
- las descargas mensuales de Consulta Externa solo para la pestaña `CENACRON`.

El mensaje sugerido del correo se usa como base para notificar por WhatsApp.

## Restricciones

- No incluir este orquestador en la cadena de madrugada.
- No activar timers individuales de los RPAs si el timer activo sera `rpa-orquestador-cronicos.timer`.
- `rpa-mensual-cronicos` debe correr con `DOWNLOAD_ONLY=true`; no registra ni refresca base de datos.
