# RPA Prog Prof

Descarga la programacion de profesionales desde ExplotaDatos para los centros/IPRESS marcados en la pestaña `CENACRON`.

## Alcance

| Item | Valor |
| --- | --- |
| Codigo del job | `PROG_PROF` |
| Nombre funcional | `RPA Prog Prof` |
| Spreadsheet tab | `CENACRON` |
| Rango | Primer dia del mes hasta ultimo dia del mes |
| Formato | `xls` |
| Formulario | `CtrlControl?opt=adm19` |
| Publicacion | `//10.0.88.100/bbdd_rpa/Bases_Prog_Prof` |

## Selecciones

- Area: `00` (`TODOS`)
- Servicio: `00` (`TODOS`)
- Fecha Inicio: primer dia del mes objetivo
- Fecha Fin: ultimo dia del mes objetivo
- Tipo Archivo: `xls` (`*.TXT para XLS`)
- Boton: `Imprimir`

## Archivos esperados

El formulario descarga archivos con el patron:

```text
COD_YYYYMMDD_YYYYMMDD_ConsProgPro.txt
```

Ejemplos:

```text
008_20260701_20260731_ConsProgPro.txt
405_20260701_20260731_ConsProgPro.txt
```

## Operacion

Este RPA no pertenece al orquestador de madrugada. Para el flujo de Cronicos se ejecuta desde `orquestador-cronicos` antes de `rpa-mensual-cronicos`.

El RPA descarga primero en `STAGING_DOWNLOAD_DIR`, valida el archivo y despues publica en la ruta final. Solo elimina/reemplaza archivos finales del mismo centro, periodo y sufijo.
