# Operacion QA - RPA Prog Prof

## Objetivo

Validar descarga mensual de programacion de profesionales para centros marcados en `CENACRON`.

## Variables clave

```text
GSHEET_TAB=CENACRON
FRM_PROG_PROF=http://appsgasistexpl.essalud.gob.pe/explotaDatos/servlet/CtrlControl?opt=adm19
DOWNLOAD_DIR_PROG_PROF=//10.0.88.100/bbdd_rpa/Bases_Prog_Prof
FILE_SUFFIX_PROG_PROF=ConsProgPro
AREA=00
SERVICIO=00
FORMATO_ARCHIVO=xls
```

## Validacion

- Confirmar que lee solo `CENACRON`.
- Confirmar que agrupa centros por `MACRO`.
- Confirmar que publica archivos `COD_YYYYMMDD_YYYYMMDD_ConsProgPro.txt`.
- Confirmar que limpia staging y perfiles Chrome temporales al finalizar.

No activar timers individuales si el flujo completo sera controlado por `orquestador-cronicos`.
