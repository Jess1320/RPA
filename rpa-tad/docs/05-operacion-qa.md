# Operacion QA - RPA TAD

## Ejecucion controlada

Usar filtros para pruebas:

```env
MAX_CENTERS=1
CENTERS_FILTER=739
RUN_RESULTADO_TIPO_EXAMEN=true
RUN_TRATAMIENTO_PENDIENTES=true
RUN_TRATAMIENTO_ASIGNADOS=true
```

Ejecutar:

```bash
scripts/run_rpa_tad.sh
```

## Validaciones esperadas

- Lee centros desde la pestaña `TAD`.
- Usa credenciales maestras por macroregion.
- Descarga en staging y publica solo despues de validar archivo no vacio y estable.
- Valida sufijos `ResulExam_Imagen`, `TratImagenesPendientes` y `TratImagenesAsignados`.
- Renombra solo `RESULTADO_TIPO_EXAMEN` a `COD_YYYYMM01_YYYYMMDD_MES.txt`.
- Limpia staging y perfiles temporales al finalizar.

## Produccion

Antes de activar en el orquestador:

1. Confirmar montaje de `\\10.0.88.100\comp_observatorio`.
2. Ejecutar corrida controlada con uno o pocos centros.
3. Validar archivos finales y temporales.
4. Agregar `TAD` al `JOB_ORDER` y activar `TAD_ENABLED=true`.
