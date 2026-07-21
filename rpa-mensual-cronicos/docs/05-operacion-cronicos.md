# Operacion - RPA Mensual Cronicos

## Alcance

Descarga y publica archivos mensuales de Consulta Externa para la pestaña `CENACRON`.

## Configuracion obligatoria

```text
GSHEET_TABS=CENACRON
DOWNLOAD_ONLY=true
DB_PRECHECK_ENABLED=false
RPA_FAIL_IF_DB_DOWN=false
FINAL_PUBLISH_DIR=//10.0.88.100/bbdd_rpa/Base_Consulta_Externa_2026
```

## Flujo

1. Lee centros/IPRESS marcados en `CENACRON`.
2. Agrupa por `MACRO`.
3. Usa usuarios maestros por macroregion.
4. Descarga el periodo mensual completo.
5. Publica TXT en la ruta final.
6. Envia resultado al orquestador.

## Criterio de healthcheck y fallback

Este modulo debe seguir el mismo criterio operativo del RPA Diario:

- El healthcheck no debe bloquear una macroregion completa.
- La descarga primaria debe intentarse con el usuario maestro de la macroregion declarada.
- Si el centro no aparece en el selector del formulario, se envia a fallback con otros usuarios maestros.
- Un resultado `NO_ENCONTRADO_EN_WEB` indica que el centro no fue visible para ese usuario/macroregion en el formulario, no confirma por si solo falta de acceso del usuario.
- Los errores `EXCEPTION:*`, timeouts o archivos incompletos deben tratarse como fallas tecnicas reintentables segun la logica del RPA.

Motivo: el healthcheck puede producir falsos negativos aunque el usuario maestro descargue correctamente. La referencia estable es el comportamiento del RPA Diario, que corre durante el dia sin bloquear por healthcheck.

## Restriccion de BD

Este modulo no debe registrar ni refrescar BD. El unico Mensual que publica a base de datos es el de madrugada.
