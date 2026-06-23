# AI Context - RPA Mensual CEXT

## Lectura rapida

El RPA Mensual es una variante del RPA Diario para el reporte `PacCitCExt`, pero procesa meses completos. La ruta visual de ExplotaDatos es la misma hasta seleccionar centro/IPRESS. Luego navega a una URL interna del formulario masivo y completa `fe_ini` y `fechaFin` con el primer y ultimo dia del mes.

## Produccion

- Servidor: `10.0.89.241`.
- Directorio: `/home/cenate/rpa_cext_diario`.
- Script Python: `RPA_CEXT_PROD_MENSUAL.py`.
- Wrapper: `run_rpa_mensual.sh`.
- Env real: `.env_mensual` fuera de Git.
- Timer: `rpa-cext-mensual.timer`.
- Service: `rpa-cext-mensual.service`.
- Horario actual: `04:00` todos los dias.

## Reglas de seguridad

- No ejecutar el RPA mensual sin autorizacion explicita.
- No copiar `.env_mensual` real al repositorio.
- No exponer credenciales, URLs privadas ni JSON de Google en documentacion publica.
- Si se revisan logs, resumir metricas y eventos; no versionar logs.

## Flujo funcional

1. Carga `.env_mensual`.
2. Calcula mes o meses desde `MES_A_PROCESAR`.
3. Lee centros/IPRESS marcados en Google Sheets por columna del mes.
4. Deduplica centros entre tabs y conserva macroregion.
5. Aplica overrides aprendidos si existen.
6. Ejecuta healthcheck por usuario/macro.
7. Descarga por macro en paralelo.
8. Aplica fallback para centros no encontrados en macro declarada.
9. Carga archivos a `stg.cext_prod_mensual`.
10. Publica archivos del periodo en carpeta final y espejos.
11. Sincroniza medicos desde la fuente 241.
12. Ejecuta refresh mensual.
13. Poda staging mensual para conservar el run vigente del periodo.
14. Opcionalmente cierra periodo mensual si `CLOSE_MONTH=true`.
15. Finaliza control DB y envia correo.

## Ultima evidencia revisada

Ejecucion `RUN_CEXT_PROD_MENSUAL_20260623_040037`:

- Periodo: `2026-06`.
- Rango: `2026-06-01` a `2026-06-30`.
- Centros input: `104`.
- Centros OK: `104`.
- Centros fallidos: `0`.
- Archivos publicados: `105`.
- Refresh mensual: OK.
- Duracion: `2951.4` segundos.
- Warning observado: `DB_FILE_WARN` en archivo `406_20260601_20260630_PacCitCExt.txt` por campo mayor a `131072`.
- Archivo extra investigado: `436_20260601_20260630_PacCitCExt.txt`; no pertenecia al input de 104 centros y fue publicado por estar en el periodo.

## Cierre mensual

El cierre mensual se usa para reprocesar un periodo completo, normalmente el mes anterior durante los primeros dias del mes nuevo, aunque puede ejecutarse el ultimo dia por solicitud de direccion.

Comando operativo conocido:

```bash
cd /home/cenate/rpa_cext_diario
source .venv/bin/activate
MES_A_PROCESAR=2026-05 CLOSE_MONTH=true CLOSE_MONTH_PERIOD=2026-05 ENV_FILE=.env_mensual python -u RPA_CEXT_PROD_MENSUAL.py
```

El cierre mensual tiene dos objetivos:

- Operativo: republicar archivos para Observatorio/BI tras validaciones de coordinadores y correcciones de atenciones medicas.
- Base de datos: archivar el mes cerrado como historico, porque la corrida diaria mensual normal solo mantiene el periodo vigente sin guardar historico completo cada dia.
