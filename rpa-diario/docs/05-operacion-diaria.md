# Operacion Diaria

## Programacion

El RPA se ejecuta mediante systemd durante la ventana aproximada de 07:00 a 22:00. La mayoria de corridas se programa cada 30 minutos, con algunos intervalos mayores para evitar colisiones.

## Ejecucion manual

La ejecucion manual debe respetar el mismo bloqueo que la ejecucion automatica para evitar solapamientos.

```bash
systemctl start rpa-diario.service
```

O, si se ejecuta por wrapper:

```bash
/home/cenate/rpa_cext_diario/run_rpa_diario.sh
```

El wrapper versionado valida:

- Existencia del Python del entorno virtual.
- Existencia del script principal.
- Montaje de `/mnt/abandonos`.
- Bloqueo exclusivo con `flock`.
- Registro en `orchestrator_logs`.

## Validacion de una corrida correcta

Una corrida correcta debe cumplir:

- Total de centros/IPRESS esperados procesados.
- Archivos descargados y validados.
- Staging cargado.
- Publicacion final OK.
- Refresh de reportes OK.
- `overall_status = SUCCESS` o `SUCCESS_WITH_WARNINGS`.
- `data_ready = true`.
- Correo enviado o registrado como warning no critico.

En una corrida con descargas y publicacion correctas debe aparecer en `summary.log` un evento `REFRESH_REPORTES_DIARIO` antes de `RUN_END`. Si aparece `REFRESH_REPORTES_DIARIO_SKIP`, revisar el motivo indicado.

## Revision ante falla

1. Revisar log de corrida.
2. Revisar `summary.log`.
3. Consultar estado persistido en PostgreSQL.
4. Identificar etapa fallida.
5. Validar si hay archivos temporales incompletos.
6. Confirmar si la carpeta compartida fue publicada.
7. Revisar si hubo timeout, falla de ChromeDriver, cambio de cabecera o error de credenciales.
