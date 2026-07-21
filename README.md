# Repositorio de RPAs CENATE

Este repositorio organiza los RPAs desarrollados para CENATE, separando codigo, configuracion, documentacion operativa y contexto tecnico para IA.

## Estructura

```text
RPAs/
  rpa-diario/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
    tests/
  rpa-mensual/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  rpa-tele-triaje/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  rpa-tele-urgencia/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  rpa-medico-no-medico/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  rpa-prog-prof/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  rpa-mensual-cronicos/
    README.md
    AI_CONTEXT.md
    docs/
    config/
    src/
    scripts/
  orquestador-madrugada/
    README.md
    config/
    src/
    scripts/
  orquestador-cronicos/
    README.md
    config/
    src/
    scripts/
  shared/
    README.md
    config/
      .env_usuarios.example
  docs/
    plantilla-rpa.md
```

## RPAs documentados

- `rpa-diario`: descarga diaria y futuro corto desde ExplotaDatos.
- `rpa-mensual`: descarga mensual de periodo completo desde ExplotaDatos.
- `rpa-tele-triaje`: descarga mensual de Tele Triaje. En migracion QA.
- `rpa-tele-urgencia`: descarga mensual de Tele Urgencia. En migracion QA.
- `rpa-medico-no-medico`: descarga mensual separada para Medico y No Medico. En migracion QA.
- `orquestador-madrugada`: ejecuta en cadena los RPAs nocturnos y envia un unico correo consolidado.
- `rpa-prog-prof`: descarga mensual de programacion de profesionales para Cronicos desde la pestaña `CENACRON`.
- `rpa-mensual-cronicos`: variante de descarga/publicacion mensual para Cronicos; no registra ni refresca BD.
- `orquestador-cronicos`: ejecuta `rpa-prog-prof` y luego `rpa-mensual-cronicos` a las 08:00, 11:00, 12:45 y 16:00.

Los tres RPAs migrados descargan/publican archivos y soportan reporte por correo via `MAIL_*`/`SMTP_*`. Aun no registran en `rpa_control`, staging ni panel.

## Modelo de trabajo

Cada RPA debe tener documentacion propia y actualizada. La documentacion no reemplaza al codigo, pero debe permitir entender rapidamente:

- Que hace el RPA.
- Donde se ejecuta.
- Que sistemas toca.
- Que entradas y salidas maneja.
- Como se opera diariamente.
- Que hacer cuando falla.
- Que contexto debe leer una IA antes de modificarlo.

## Reglas generales

- No subir credenciales reales.
- No subir archivos descargados, logs pesados ni temporales.
- Mantener `.env.example` como referencia de configuracion.
- Centralizar credenciales de descarga en `shared/config/.env_usuarios` o en la ruta definida por `RPA_USERS_ENV_FILE`.
- Registrar cambios funcionales junto con cambios de documentacion.
- Reutilizar componentes comunes para login, seleccion de IPRESS, descarga, logging y manejo de estados.
