# Pase operativo QA - RPAs locales migrados

Fecha: 2026-07-04

## Alcance

Se deja operativo en QA el arranque automatico de los tres RPAs migrados desde ejecucion local:

| RPA | Label launchd | Hora QA |
| --- | --- | --- |
| Medico y No Medico | `pe.gob.essalud.rpa-medico-no-medico` | 02:30 |
| Tele Triaje | `pe.gob.essalud.rpa-tele-triaje` | 03:00 |
| Tele Urgencia | `pe.gob.essalud.rpa-tele-urgencia` | 06:00 |

No corresponde a pase productivo. Produccion queda pendiente de montaje final, control DB y aprobacion operativa.

## Rutas QA

```text
/Users/cenate2/rpas
/Users/cenate2/rpas/shared/config/.env_usuarios
/Users/cenate2/Library/LaunchAgents
/Users/cenate2/rpas_qa_outputs
```

Los `.env.qa` privados de cada RPA quedaron con:

```text
RPA_USERS_ENV_FILE=/Users/cenate2/rpas/shared/config/.env_usuarios
REQUIRE_MACRO=true
```

## Jobs instalados

```bash
launchctl print gui/$(id -u)/pe.gob.essalud.rpa-medico-no-medico
launchctl print gui/$(id -u)/pe.gob.essalud.rpa-tele-triaje
launchctl print gui/$(id -u)/pe.gob.essalud.rpa-tele-urgencia
```

Estado esperado despues de instalar:

```text
state = not running
last exit code = (never exited)
```

Ese estado es normal mientras no llegue la hora programada.

## Validacion despues de la primera madrugada

Revisar:

```bash
tail -80 /Users/cenate2/rpas/rpa-medico-no-medico/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
tail -80 /Users/cenate2/rpas/rpa-tele-triaje/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
tail -80 /Users/cenate2/rpas/rpa-tele-urgencia/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
```

Criterios:

- Existe `ORCH_START`.
- Existe `ORCH_END | exit_code=0`.
- Los logs del run muestran `CONFIG_OK`.
- Los logs del run muestran `MACRO_START` y `MACRO_END`.
- No aparece `SIN_MACRO`.
- No hay `TOTAL_FAIL`, `Centros FAIL` o `MONTH_SUMMARY` con fallas.

## Ejecucion manual QA

```bash
cd /Users/cenate2/rpas/rpa-medico-no-medico
ENV_FILE=.env.qa scripts/run_rpa_medico_no_medico.sh

cd /Users/cenate2/rpas/rpa-tele-triaje
ENV_FILE=.env.qa scripts/run_rpa_tele_triaje.sh

cd /Users/cenate2/rpas/rpa-tele-urgencia
ENV_FILE=.env.qa scripts/run_rpa_tele_urgencia.sh
```

## Pausar schedulers QA

```bash
launchctl bootout gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-medico-no-medico.plist
launchctl bootout gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-tele-triaje.plist
launchctl bootout gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-tele-urgencia.plist
```

## Reactivar schedulers QA

```bash
launchctl bootstrap gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-medico-no-medico.plist
launchctl bootstrap gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-tele-triaje.plist
launchctl bootstrap gui/$(id -u) /Users/cenate2/Library/LaunchAgents/pe.gob.essalud.rpa-tele-urgencia.plist
```

## Pendientes para produccion

- Definir montaje definitivo para `BD_CControl` en el servidor Linux de produccion.
- Crear archivo maestro productivo de usuarios, fuera de Git.
- Decidir rutas finales de publicacion para Medico y No Medico.
- Agregar control DB para panel.
- Preparar unidades `systemd` productivas con `RPA_USERS_ENV_FILE`.
- Ejecutar corrida manual productiva controlada antes de activar timers.
