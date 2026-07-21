# RPA Mensual Cronicos

Variante separada del RPA Mensual para el flujo diurno de Cronicos.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `CEXT_CRONICOS_MENSUAL` |
| Spreadsheet tab | `CENACRON` |
| Rango | Primer dia del mes hasta ultimo dia del mes |
| Formulario | El mismo formulario mensual de Consulta Externa (`FRM_MASIVAS`) |
| Publicacion | `//10.0.88.100/bbdd_rpa/Base_Consulta_Externa_2026` |
| BD/control | Deshabilitado por `DOWNLOAD_ONLY=true` |

## Diferencia con el Mensual de madrugada

Este modulo solo descarga y publica archivos TXT. No registra staging, no refresca vistas, no sincroniza medicos y no ejecuta cierre mensual.

La carpeta final es la misma que usa el Mensual productivo. El reemplazo de TXT del mismo centro y periodo es esperado para el flujo de Cronicos.

## Operacion

Este RPA no debe ir en `orquestador-madrugada`. Se ejecuta desde `orquestador-cronicos` despues de `rpa-prog-prof`.
