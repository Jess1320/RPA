# Estandar para perfiles temporales de Chrome/Selenium

Este patron aplica a todo RPA que use Selenium con Chrome o Chromium en servidor Linux o Windows.

## Regla principal

Cada ejecucion de `webdriver.Chrome` debe usar un perfil temporal propio y controlado con `--user-data-dir`. Ese perfil debe eliminarse siempre en un bloque `finally`, despues de `driver.quit()`.

No se debe depender del temporal por defecto de Chromium, porque puede crear perfiles en rutas como `/tmp/snap-private-tmp/snap.chromium/tmp` y acumular miles de carpetas `chrome-profile-*`.

## Variables obligatorias

Cada RPA debe soportar estas variables:

```env
CHROME_PROFILE_BASE_DIR=tmp/chrome_profiles
CHROME_PROFILE_MAX_AGE_HOURS=12
CHROMEDRIVER_LOGS_ENABLED=false
```

Los scripts `.sh` de systemd deben exportarlas con una ruta absoluta basada en el proyecto:

```bash
export CHROME_PROFILE_BASE_DIR="${CHROME_PROFILE_BASE_DIR:-$PROJECT_DIR/tmp/chrome_profiles}"
export CHROME_PROFILE_MAX_AGE_HOURS="${CHROME_PROFILE_MAX_AGE_HOURS:-12}"
mkdir -p "$CHROME_PROFILE_BASE_DIR"
```

Los logs de Chromedriver deben estar desactivados por defecto. Si se activan para diagnostico, deben guardarse dentro de la carpeta temporal controlada y limpiarse al finalizar o por retencion corta.

## Patron obligatorio

1. Crear el perfil con `tempfile.mkdtemp(prefix="chrome-profile-...", dir=CHROME_PROFILE_BASE_DIR)`.
2. Pasar el perfil a Chrome con `opts.add_argument(f"--user-data-dir={profile_dir}")`.
3. Crear el driver dentro de `try`.
4. Ejecutar siempre `driver.quit()` en `finally`.
5. Eliminar siempre `profile_dir` en `finally` con una funcion segura tipo `safe_rmtree`.
6. Ejecutar limpieza preventiva al inicio y final, solo de carpetas propias `chrome-profile-*` dentro de `CHROME_PROFILE_BASE_DIR`.
7. No generar logs permanentes de Chromedriver en operacion normal.

## Prohibido

- No borrar `/tmp` completo.
- No borrar carpetas finales de descarga.
- No reutilizar el mismo perfil entre hilos o centros.
- No crear `webdriver.Chrome` sin perfil temporal controlado.
- No dejar `driver.quit()` fuera de `finally`.
- No dejar `chromedriver_logs` creciendo sin retencion dentro de temporales.

## Validacion minima

Antes de pasar a produccion:

```bash
python -m py_compile src/RPA_*.py
find "$CHROME_PROFILE_BASE_DIR" -mindepth 1 -maxdepth 1 -type d -name 'chrome-profile-*' | wc -l
ps -eo pid,etime,cmd | grep -Ei 'chromium|chrome|chromedriver|selenium' | grep -v grep
```

El contador de perfiles debe volver a cero despues de una ejecucion normal o fallida.
