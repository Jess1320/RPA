# Orquestador Cronicos

## Objetivo

Ejecutar descargas diurnas para Cronicos sin modificar el orquestador de madrugada.

## Horarios

```text
08:00
11:00
12:45
16:00
```

## Cadena

```text
rpa-orquestador-cronicos.timer
  -> rpa-orquestador-cronicos.service
    -> orquestador-cronicos/scripts/run_orquestador_cronicos.sh
      -> RPA Prog Prof
      -> RPA Mensual Cronicos
```

## RPA Prog Prof

- Modulo: `rpa-prog-prof`
- Formulario: `CtrlControl?opt=adm19`
- Tab Google Sheets: `CENACRON`
- Publicacion Windows: `\\10.0.88.100\bbdd_rpa\Bases_Prog_Prof`
- Publicacion en servidor Linux: `/mnt/BBDD_RPA/Bases_Prog_Prof`
- Archivo esperado: `COD_YYYYMMDD_YYYYMMDD_ConsProgPro.txt`

## RPA Mensual Cronicos

- Modulo: `rpa-mensual-cronicos`
- Tab Google Sheets: `CENACRON`
- Publicacion Windows: `\\10.0.88.100\bbdd_rpa\Base_Consulta_Externa_2026`
- Publicacion en servidor Linux: `/mnt/BBDD_RPA/Base_Consulta_Externa_2026`
- Modo: `DOWNLOAD_ONLY=true`

Este RPA solo descarga y publica. No registra staging, no refresca reportes, no sincroniza medicos y no ejecuta cierre mensual.

## Regla Operativa

No activar este flujo dentro de `orquestador-madrugada`. El timer operativo debe ser `rpa-orquestador-cronicos.timer`.
