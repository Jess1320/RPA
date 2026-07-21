# Contexto para IA - RPA Mensual Cronicos

Variante diurna del RPA Mensual para Cronicos.

## Objetivo

Descargar Consulta Externa mensual solo para centros/IPRESS marcados en la pestaña `CENACRON` y publicar los TXT en la carpeta final del Observatorio.

## Restricciones

- No pertenece al orquestador de madrugada.
- No registra en PostgreSQL.
- No carga staging.
- No ejecuta refresh.
- No sincroniza medicos.
- No ejecuta cierre mensual.
- Debe correr con `DOWNLOAD_ONLY=true`.

## Publicacion

```text
//10.0.88.100/bbdd_rpa/Base_Consulta_Externa_2026
```

La ruta coincide con la del Mensual productivo. El reemplazo de TXT del mismo centro y periodo es esperado para el flujo de Cronicos.

## Orquestacion

Se ejecuta despues de `rpa-prog-prof` desde `orquestador-cronicos`.
