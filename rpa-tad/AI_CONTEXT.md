# Contexto para IA - RPA TAD

## Objetivo

Descargar tres reportes de Tele Apoyo al Diagnostico por IPRESS marcada en Google Sheets:

- `RESULTADO_TIPO_EXAMEN`: `CtrlControl?opt=ayudaDx04A_B`, valida `ResulExam_Imagen`.
- `TRATAMIENTO_PENDIENTES`: `CtrlControl?opt=atentraimagPen`, valida `TratImagenesPendientes`.
- `TRATAMIENTO_ASIGNADOS`: `CtrlControl?opt=atentraimagAsig`, valida `TratImagenesAsignados`.

Las tres rutas usan la pestaña `TAD`.

## Rango

Usa siempre desde el primer dia del mes hasta el ultimo dia del mes, tambien para `MES_A_PROCESAR=ACTUAL`.

## Entradas

- Spreadsheet compartido del proyecto.
- Pestaña `TAD`.
- Credenciales maestras desde `../shared/config/.env_usuarios`.
- Macroregion por IPRESS igual que los otros RPAs.

## Salidas

- Resultado por Tipo de Examen: `/mnt/comp_observatorio/BI_2025/Bases_Teleradio/2026 ESSI`.
- Pendientes: `/mnt/comp_observatorio/BI_2025/Bases_Teleradio/DIFERIMIENTO_ESSI_PENDIENTES`.
- Asignados: `/mnt/comp_observatorio/BI_2025/Bases_Teleradio/DIFERIMIENTO_ESSI_ASIGNADOS`.

## Renombramiento

Solo `RESULTADO_TIPO_EXAMEN` se renombra al publicar:

`COD_YYYYMM01_YYYYMMDD_MES.txt`

Antes de renombrar se valida el archivo descargado con el sufijo real `ResulExam_Imagen`.

## Regla de publicacion

No descargar directo a la carpeta final. Descargar en staging, validar y luego publicar.

No eliminar periodos antiguos. Solo reemplazar archivos del mismo centro, mismo periodo y mismo sufijo despues de tener la nueva descarga validada.

## Temporales

Debe cumplir `docs/estandar-perfiles-chrome-selenium.md`.
