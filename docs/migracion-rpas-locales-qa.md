# Migracion inicial de RPAs locales a QA

Fecha de inicio: 2026-07-04

## Objetivo

Preparar en el repositorio los RPAs que actualmente corren en la PC local para probarlos en QA y luego migrarlos al servidor de produccion.

## RPAs incluidos

| RPA local | Nombre en repositorio | Nombre productivo | Hora actual |
| --- | --- | --- | --- |
| `D:\RPA_DX_MED_NMED` | `rpa-medico-no-medico` | RPA Medico y No Medico | 02:30 |
| `D:\RPA_TELE_TRIAJE` | `rpa-tele-triaje` | RPA Tele Triaje | 03:00 |
| `D:\RPA_TELE_URGENCIA` | `rpa-tele-urgencia` | RPA Tele Urgencia | 06:00 |

## Estado local observado

Las ultimas ejecuciones locales revisadas del 2026-07-04 terminaron con exit code `0`.

| RPA | Resultado observado |
| --- | --- |
| Medico y No Medico | 1 centro OK, `MEDICO` y `NO_MEDICO` descargados |
| Tele Triaje | 5 centros OK, 0 fallas |
| Tele Urgencia | 4 centros OK, 0 fallas |

## Estado QA observado

Servidor QA:

```text
Host: SERVER-QA
Usuario: cenate2
Sistema: macOS
Python: 3.9.6
Scheduler objetivo: launchd
```

QA no tiene `systemd` ni rutas `/mnt`. Tiene Google Chrome instalado, pero no se encontro `chromedriver` en PATH durante la revision inicial.

## Estado produccion observado

Servidor produccion:

```text
Host: bd
Sistema: Ubuntu
Scheduler objetivo: systemd
Python: 3.12.3
Chromium/ChromeDriver: snap, version 150.0.7871.46
```

Rutas ya montadas en produccion:

```text
/mnt/comp_observatorio/BI_2025/Bases_Teletriaje_2026
/mnt/comp_observatorio/BI_2025/Bases_Teleurgencias_2026
```

Pendiente para Medico y No Medico:

```text
//10.0.89.147/BD_CControl
```

## Alcance de esta etapa

Esta etapa estandariza codigo, configuracion, wrappers y documentacion para correr en QA con control basico. El soporte de correo se activa por configuracion `MAIL_*`/`SMTP_*`; `rpa_control` y panel quedan para una fase posterior.

## Decision de arquitectura: usuarios maestros

Los RPAs de descarga desde ExplotaDatos deben usar los mismos usuarios maestros que Diario y Mensual, agrupados por macroregion:

```text
USER_CENTRO / PASSWORD_CENTRO
USER_NORTE / PASSWORD_NORTE
USER_SUR / PASSWORD_SUR
USER_LIMA_ORIENTE / PASSWORD_LIMA_ORIENTE
```

El archivo real debe quedar fuera de Git:

```text
shared/config/.env_usuarios
```

Cada RPA mantiene su `.env` propio para rutas, Google Sheets, logs y parametros del job, pero las credenciales de descarga se toman desde `RPA_USERS_ENV_FILE` o desde la ruta compartida por defecto.

Para quedar alineados con Diario y Mensual, las hojas de los tres RPAs deben tener columna `MACRO`. Durante QA se permite `REQUIRE_MACRO=false` con `DEFAULT_MACRO=CENTRO` para no bloquear pruebas si una hoja aun no tiene la columna. Antes de produccion, usar `REQUIRE_MACRO=true`.

## Prueba smoke QA

Fecha: 2026-07-04

Se desplego el codigo en:

```text
/Users/cenate2/rpas
```

Se crearon `.env.qa` privados fuera de Git con salidas locales de prueba:

```text
/Users/cenate2/rpas_qa_outputs/medico-no-medico/medico
/Users/cenate2/rpas_qa_outputs/medico-no-medico/no_medico
/Users/cenate2/rpas_qa_outputs/tele-triaje
/Users/cenate2/rpas_qa_outputs/tele-urgencia
```

Resultado con `MAX_CENTERS=1`:

| RPA | Resultado QA |
| --- | --- |
| Medico y No Medico | `exit_code=0`, centro `739`, archivos `MEDICO` y `NO_MEDICO` descargados |
| Tele Triaje | `exit_code=0`, centro `127`, archivo descargado |
| Tele Urgencia | `exit_code=0`, centro `127`, archivo descargado |

No se activaron schedulers en QA durante esta prueba.

Resultado completo con `MAX_CENTERS=0`:

| RPA | Resultado QA completo |
| --- | --- |
| Medico y No Medico | `exit_code=0`, 1/1 centro OK, 2 archivos descargados |
| Tele Triaje | `exit_code=0`, 5/5 centros OK, 5 archivos descargados |
| Tele Urgencia | `exit_code=0`, 4/4 centros OK, 4 archivos descargados |

Archivos generados en QA:

```text
/Users/cenate2/rpas_qa_outputs/medico-no-medico/medico/739_20260701_20260731_DxMedSer.txt
/Users/cenate2/rpas_qa_outputs/medico-no-medico/no_medico/739_20260701_20260731_DxNoMedSer.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/007_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/038_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/127_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/405_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/407_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/038_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/127_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/405_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/407_20260701_20260731_PacAtendxTopico.txt
```

No se cargaron jobs `launchd`; las pruebas fueron manuales.

## Prueba QA con usuarios maestros

Fecha: 2026-07-04

Se creo el archivo privado:

```text
/Users/cenate2/rpas/shared/config/.env_usuarios
```

El archivo contiene las 8 variables de usuarios maestros por macroregion usadas por Diario/Mensual. No se versiona en Git.

Resultado con `MAX_CENTERS=1` despues de migrar a `RPA_USERS_ENV_FILE`:

| RPA | Resultado QA |
| --- | --- |
| Medico y No Medico | `exit_code=0`, macro `CENTRO`, 1/1 centro OK, `MEDICO` y `NO_MEDICO` descargados |
| Tele Triaje | `exit_code=0`, macro `SUR`, 1/1 centro OK |
| Tele Urgencia | `exit_code=0`, macro `SUR`, 1/1 centro OK |

Las hojas de Tele Triaje y Tele Urgencia ya devolvieron columna `MACRO` sin registros `SIN_MACRO` en esta prueba. Los schedulers siguen sin activarse.

Resultado completo con `MAX_CENTERS=0` y `REQUIRE_MACRO=true`:

| RPA | Resultado QA completo |
| --- | --- |
| Medico y No Medico | `exit_code=0`, macro `CENTRO`, 1/1 centro OK, 2 archivos descargados |
| Tele Triaje | `exit_code=0`, macros `SUR` y `LIMA ORIENTE`, 5/5 centros OK, 5 archivos descargados |
| Tele Urgencia | `exit_code=0`, macros `SUR` y `LIMA ORIENTE`, 4/4 centros OK, 4 archivos descargados |

Archivos confirmados en carpetas QA:

```text
/Users/cenate2/rpas_qa_outputs/medico-no-medico/medico/739_20260701_20260731_DxMedSer.txt
/Users/cenate2/rpas_qa_outputs/medico-no-medico/no_medico/739_20260701_20260731_DxNoMedSer.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/007_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/038_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/127_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/405_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-triaje/407_20260701_20260731_PacAtenTriaje.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/038_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/127_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/405_20260701_20260731_PacAtendxTopico.txt
/Users/cenate2/rpas_qa_outputs/tele-urgencia/407_20260701_20260731_PacAtendxTopico.txt
```

## Reglas

- No versionar `.env` reales.
- No versionar JSON reales de Google.
- Usar `ENV_FILE=.env.qa` en QA.
- Usar rutas locales de prueba en QA si no hay montajes definitivos.
- No usar `DX` como nombre productivo para `rpa-medico-no-medico`.
- No activar timers/schedulers sin una corrida manual exitosa.
- No duplicar credenciales por RPA; usar `shared/config/.env_usuarios`.
- Exigir columna `MACRO` antes de activar produccion.

## Pase operativo QA

Fecha: 2026-07-04

Se instalaron y activaron los `LaunchAgents` QA:

| RPA | Label | Horario |
| --- | --- | --- |
| Medico y No Medico | `pe.gob.essalud.rpa-medico-no-medico` | 02:30 |
| Tele Triaje | `pe.gob.essalud.rpa-tele-triaje` | 03:00 |
| Tele Urgencia | `pe.gob.essalud.rpa-tele-urgencia` | 06:00 |

Estado verificado con `launchctl print`: los tres jobs quedaron cargados, `state = not running`, `last exit code = (never exited)`, lo esperado antes de la primera ejecucion programada.

Runbook: `docs/pase-operativo-qa-rpas-locales.md`.

## Pase productivo parcial

Fecha: 2026-07-04

Se desplego codigo y configuracion privada en el servidor productivo `10.0.89.241`.

| RPA | Estado produccion |
| --- | --- |
| Tele Triaje | Timer activo para 03:00; smoke productivo `MAX_CENTERS=1` OK |
| Tele Urgencia | Timer activo para 06:00; smoke productivo `MAX_CENTERS=1` OK |
| Medico y No Medico | Timer activo para 02:30; smoke productivo `MAX_CENTERS=1` OK |

Runbook: `docs/pase-productivo-rpas-locales.md`.
