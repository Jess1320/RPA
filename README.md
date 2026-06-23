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
  shared/
    README.md
  docs/
    plantilla-rpa.md
```

## RPAs documentados

- `rpa-diario`: descarga diaria y futuro corto desde ExplotaDatos.
- `rpa-mensual`: descarga mensual de periodo completo desde ExplotaDatos.

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
- Registrar cambios funcionales junto con cambios de documentacion.
- Reutilizar componentes comunes para login, seleccion de IPRESS, descarga, logging y manejo de estados.
