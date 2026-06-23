# RPA Mensual CEXT

## Proposito

El RPA Mensual descarga desde ExplotaDatos la informacion de Consulta Externa correspondiente a un mes completo. Usa el mismo acceso base que el RPA Diario: login, seleccion de centro/IPRESS y navegacion directa a la URL interna del formulario `PacCitCExt`.

## Diferencia principal contra el diario

- Diario: trabaja con una ventana corta operativa, actualmente dia operativo y futuro cercano.
- Mensual: trabaja siempre con el rango completo del mes procesado, desde el dia 1 hasta el ultimo dia calendario del mes.

## Ejecucion en produccion

```text
systemd timer
  -> rpa-cext-mensual.service
    -> /home/cenate/rpa_cext_diario/run_rpa_mensual.sh
      -> ENV_FILE=.env_mensual
        -> RPA_CEXT_PROD_MENSUAL.py
```

El timer de produccion ejecuta una vez al dia a las `04:00`.

## Documentacion

- [Resumen funcional](docs/01-resumen-funcional.md)
- [Arquitectura](docs/02-arquitectura.md)
- [Flujo del proceso](docs/03-flujo-proceso.md)
- [Configuracion](docs/04-configuracion.md)
- [Operacion mensual](docs/05-operacion-mensual.md)
- [Estados y control](docs/06-estados-y-control.md)
- [Errores conocidos](docs/07-errores-conocidos.md)
- [Hallazgos tecnicos](docs/08-hallazgos-tecnicos.md)

