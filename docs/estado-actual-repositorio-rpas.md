# Estado actual del repositorio de RPAs CENATE

Fecha de corte: 2026-07-02  
Repositorio local: `C:\Users\cenate.proyectosti\Documents\RPAs`  
Repositorio remoto: `https://github.com/Jess1320/RPA.git`  
Rama principal remota: `origin/main`  
Rama de trabajo actual: `codex/preparar-rpa-diario-controlado`

Este documento resume el estado funcional, tecnico, operativo y documental definido hasta ahora para que otra IA pueda continuar el trabajo sin tener que reanalizar todo el historial.

## 1. Objetivo del repositorio

El repositorio organiza los RPAs de CENATE de forma versionada, documentada y entendible para humanos e IA.

El objetivo principal es dejar de trabajar cada RPA como codigo aislado generado o modificado manualmente, y pasar a un modelo ordenado con:

- Codigo fuente versionado.
- Documentacion funcional y tecnica por RPA.
- Configuracion de ejemplo sin secretos.
- Scripts de ejecucion controlada.
- Reglas de operacion y recuperacion.
- Contexto especifico para que una IA pueda leer antes de modificar.

Los RPAs actuales documentados son:

- `rpa-diario`: RPA de Consulta Externa diario/futuro corto.
- `rpa-mensual`: RPA de Consulta Externa mensual por periodo completo.

Ambos usan el mismo patron base de ExplotaDatos:

1. Entrar a una ruta unica de ExplotaDatos.
2. Autenticarse con credenciales por macroregion.
3. Permanecer dentro del reporteador.
4. Seleccionar centro/IPRESS desde un combo.
5. Consultar Google Sheets para saber que centros procesar.
6. Cambiar centro/IPRESS segun codigo.
7. Navegar a una URL interna especifica del formulario.
8. Completar criterios.
9. Descargar archivos `PacCitCExt.txt`.

La diferencia funcional aparece despues de seleccionar el centro/IPRESS:

- Diario usa un rango operativo corto: dia actual y futuro cercano.
- Mensual usa el mes completo: desde el dia 1 hasta el ultimo dia calendario.

## 2. Estado GitHub y ramas

Remoto configurado:

```text
origin  https://github.com/Jess1320/RPA.git
```

Ramas observadas:

```text
main
origin/main
codex/preparar-rpa-diario-controlado
origin/codex/preparar-rpa-diario-controlado
```

`origin/HEAD` apunta a `origin/main`. La rama `main` quedo como rama principal del repositorio. La rama `master` no se mantiene como rama necesaria.

La rama actual de trabajo es:

```text
codex/preparar-rpa-diario-controlado
```

Ultimos commits relevantes de la rama de trabajo:

```text
e209c7a docs: documentar excepcion temporal de sabado a 5 dias
78a569a docs: actualizar perfil operativo diario a 4 hilos
0018d60 docs: documentar runtime systemd para chromium snap
88a725f fix: ampliar escudo de preflight chromedriver
6fa108d fix: proteger vistas ante corridas incompletas
66f6059 fix: reforzar reintento de preflight chromedriver
01abc19 fix: reintentar corrida si falla preflight chromedriver
28c7a60 fix: aumentar reintentos de preflight chromedriver
ff217e2 fix: notificar fallo temprano de chromedriver
875d309 fix: leer txt de explotadatos sin interpretar comillas
```

Estado local al generar este resumen:

```text
?? artifacts/
```

La carpeta `artifacts/` contiene al menos:

```text
artifacts/captura_rpa_mensual_cierre_junio_20260701.png
```

Esta carpeta no esta versionada todavia. Revisar si debe mantenerse fuera de Git o agregarse como evidencia operativa.

## 3. Estructura actual del repositorio

```text
RPAs/
  README.md
  .gitignore
  .gitattributes
  docs/
    plantilla-rpa.md
    estado-actual-repositorio-rpas.md
  shared/
    README.md
  rpa-diario/
    README.md
    AI_CONTEXT.md
    requirements.txt
    config/
      .env.example
    docs/
      01-resumen-funcional.md
      02-arquitectura.md
      03-flujo-proceso.md
      04-configuracion.md
      05-operacion-diaria.md
      06-estados-y-control.md
      07-errores-conocidos.md
      08-roadmap-tecnico.md
    scripts/
      run_rpa_diario.sh
    src/
      RPA_CEXT_PROD_DIARIO.py
      db_pg.py
      mailer.py
  rpa-mensual/
    README.md
    AI_CONTEXT.md
    requirements.txt
    config/
      .env.example
    docs/
      01-resumen-funcional.md
      02-arquitectura.md
      03-flujo-proceso.md
      04-configuracion.md
      05-operacion-mensual.md
      06-estados-y-control.md
      07-errores-conocidos.md
      08-hallazgos-tecnicos.md
    scripts/
      run_rpa_mensual.sh
    src/
      RPA_CEXT_PROD_MENSUAL.py
      db_pg.py
      mailer.py
```

## 4. Reglas generales del repositorio

No se deben versionar:

- `.env` reales.
- Credenciales.
- JSON reales de Google.
- Logs pesados.
- Archivos descargados `.txt`, `.xls`, `.xlsx`, `.csv`.
- Temporales de navegador.
- Entornos virtuales.

Si se cambia funcionalidad, debe actualizarse documentacion:

- Cambio de flujo: `docs/03-flujo-proceso.md`.
- Cambio de variables: `docs/04-configuracion.md`.
- Error nuevo: `docs/07-errores-conocidos.md`.
- Cambio operativo: `docs/05-operacion-*.md`.
- Hallazgo tecnico mensual: `rpa-mensual/docs/08-hallazgos-tecnicos.md`.
- Mejora futura: `rpa-diario/docs/08-roadmap-tecnico.md`.

## 5. RPA Diario

### 5.1 Proposito

El RPA Diario descarga informacion asistencial de Consulta Externa desde ExplotaDatos/ESSI para centros/IPRESS definidos en Google Sheets.

La informacion se usa para:

- Visualizar citas en intranet.
- Identificar pacientes pendientes.
- Gestionar captacion y confirmacion.
- Alimentar reportes operativos.
- Mantener data actualizada para equipos tecnicos y consumidores internos.

Criticidad: alta. Si no descarga o no publica, los desarrolladores y usuarios consumen data desactualizada.

### 5.2 Produccion

Produccion observada:

```text
Servidor: 10.0.89.241
Usuario operativo: cenate
Directorio: /home/cenate/rpa_cext_diario
Script: RPA_CEXT_PROD_DIARIO.py
Wrapper: run_rpa_diario.sh
Env real: .env
Timer: rpa-cext-diario.timer
Service: rpa-cext-diario.service
```

No incluir contrasenas reales en este repositorio ni en documentacion.

### 5.3 Flujo diario

Cadena:

```text
rpa-cext-diario.timer
  -> rpa-cext-diario.service
    -> run_rpa_diario.sh
      -> .venv/bin/python
        -> RPA_CEXT_PROD_DIARIO.py
```

Etapas logicas:

1. `CONFIGURATION`
2. `CONTROL_DB_INIT`
3. `SOURCE_SELECTION`
4. `DOWNLOAD`
5. `STAGING_LOAD`
6. `PUBLICATION`
7. `MEDICAL_STAFF_SYNC`
8. `REPORT_REFRESH`
9. `STAGING_PRUNE`
10. `STATE_FINALIZATION`
11. `NOTIFICATION`

### 5.4 Configuracion diaria

Archivo de ejemplo:

```text
rpa-diario/config/.env.example
```

Variables principales:

```text
URL_HOME
FRM_MASIVAS
GSHEET_URL
CREDS_JSON
GSHEET_TABS
USER_CENTRO / PASSWORD_CENTRO
USER_NORTE / PASSWORD_NORTE
USER_SUR / PASSWORD_SUR
USER_LIMA_ORIENTE / PASSWORD_LIMA_ORIENTE
DOWNLOAD_DIRS
FINAL_PUBLISH_DIR
HEADLESS
DOWNLOAD_TIMEOUT
BETWEEN_CENTERS_DELAY
RETRY_PER_CENTER
MAX_THREADS
MAX_CONCURRENT_DRIVER_STARTS
DATE_OFFSET_DAYS
END_OFFSET_DAYS
SPECIAL_RANGE_WEEKDAYS
SPECIAL_END_OFFSET_DAYS
FORCE_REDOWNLOAD
FILE_SUFFIX
KEEP_ONLY_CURRENT_TAG
LOGS_DIR
LOG_RETENTION_DAYS
CHROME_TMP_ROOT
CHROME_TMP_RETENTION_HOURS
PG_*
SRC241_*
RPA_JOB_CODE
RPA_RUN_TYPE
RPA_FAIL_IF_DB_DOWN
MAIL_ENABLED
SMTP_*
```

Perfil operativo actual en produccion:

```text
MAX_THREADS=4
MAX_CONCURRENT_DRIVER_STARTS=1
```

Interpretacion:

- `MAX_THREADS=4`: cuatro descargas concurrentes por bloque/macro.
- `MAX_CONCURRENT_DRIVER_STARTS=1`: arranque de ChromeDriver serializado para evitar choques; no reduce los hilos de descarga a 1.

### 5.5 Rango de fechas diario

Configuracion base:

```text
DATE_OFFSET_DAYS=0
END_OFFSET_DAYS=2
SPECIAL_RANGE_WEEKDAYS=4
SPECIAL_END_OFFSET_DAYS=3
```

Regla:

- Diario normal: dia operativo + futuro cercano.
- Viernes (`weekday=4`): usa rango especial hasta lunes.
- Excepcion temporal trabajada: viernes y sabado a 5 dias cuando se requiera cubrir martes por feriado o necesidad operativa.

Para una excepcion temporal:

```text
SPECIAL_RANGE_WEEKDAYS=4,5
SPECIAL_END_OFFSET_DAYS=4
```

Luego debe revertirse a:

```text
SPECIAL_RANGE_WEEKDAYS=4
SPECIAL_END_OFFSET_DAYS=3
```

### 5.6 Wrapper diario

Archivo versionado:

```text
rpa-diario/scripts/run_rpa_diario.sh
```

Responsabilidades:

- Exporta `TZ=America/Lima`.
- Usa `ENV_FILE=.env` por defecto.
- Define `PROJECT_DIR=/home/cenate/rpa_cext_diario`.
- Verifica Python del `.venv`.
- Verifica script principal.
- Verifica escritura en `/mnt/abandonos/BASES_DIARIAS`.
- Usa `flock` con `/tmp/rpa_cext_diario.lock`.
- Escribe log de orquestador en `orchestrator_logs`.
- Evita ejecuciones redundantes recientes con `RECENT_SUCCESS_SKIP_MINUTES`.
- Reintenta automaticamente si el RPA termina con codigo reservado de preflight ChromeDriver.

Parametros del wrapper:

```text
PREFLIGHT_RETRY_EXIT_CODE=4
PREFLIGHT_RETRY_MAX=4
PREFLIGHT_RETRY_DELAY_SECONDS=180
RECENT_SUCCESS_SKIP_MINUTES=10
```

Esto significa 5 intentos totales de preflight: primer intento + 4 reintentos.

Antes de reintentar por preflight, limpia procesos/perfiles temporales de Chrome del propio RPA.

### 5.7 Codigo diario

Archivo principal:

```text
rpa-diario/src/RPA_CEXT_PROD_DIARIO.py
```

Capacidades importantes:

- Carga configuracion desde `.env`.
- Lee Google Sheets con retries.
- Normaliza codigos de centro/IPRESS.
- Deduplica centros entre tabs.
- Agrupa por macroregion.
- Usa Selenium/Chromium.
- Crea perfiles temporales de Chrome por worker.
- Aplica `ThreadPoolExecutor(max_workers=MAX_THREADS)`.
- Limita arranques de driver con `MAX_CONCURRENT_DRIVER_STARTS`.
- Tiene preflight de ChromeDriver antes de limpiar/descargar.
- Valida archivo por prefijo, TAG, sufijo, estabilidad y no vacio.
- Publica con staging/swap a carpeta final.
- Carga TXT a staging PostgreSQL.
- Sincroniza medicos desde fuente 241.
- Ejecuta `REFRESH_REPORTES_DIARIO`.
- Poda staging diario conservando el run vigente.
- Deriva estado final al cierre real.
- Envia correo via SMTP.
- Maneja senales y limpieza de navegadores/perfiles.

Mejoras criticas aplicadas:

- `csv.field_size_limit` ampliado para evitar `field larger than field limit`.
- Lectura de TXT con `quoting=csv.QUOTE_NONE` porque ExplotaDatos genera texto plano delimitado por `|`; esto evita omitir filas por comillas no balanceadas.
- `derive_final_status()` centraliza estado final.
- Refresh diario ya no depende de estado provisional.
- Si no hay publicacion final completa, la corrida no debe quedar como `PARTIAL_SUCCESS` elegible.
- Preflight ChromeDriver falla temprano con codigo `4` para que el wrapper reintente.
- Correos de preflight intermedio se omiten; solo se notifica al agotarse la recuperacion.

### 5.8 Control DB diario

Modulo:

```text
rpa-diario/src/db_pg.py
```

Funciones clave:

- Crear/obtener job.
- Crear run.
- Registrar eventos.
- Registrar archivos.
- Obtener columnas esperadas y alias.
- Insertar version de cabecera.
- Marcar archivo cargado a staging.
- Insertar bulk en `stg.cext_prod_diario`.
- Sincronizar medicos activos.
- Ejecutar refresh diario.
- Podar staging.
- Cerrar run con estado final.

Vista operacional mencionada:

```sql
ops.vw_cext_diaria_medicos_activos_full
```

Esta vista toma el ultimo `id_run` de corridas con estado `SUCCESS` o `PARTIAL_SUCCESS` cuyo `run_uuid` inicia con `RUN_CEXT_PROD_DIARIO`.

Riesgo documentado:

Si una corrida incompleta queda como `PARTIAL_SUCCESS`, la vista podria seleccionar data incompleta. Por eso se reforzo la regla: una corrida sin publicacion final completa no debe quedar como `PARTIAL_SUCCESS`.

### 5.9 Incidentes diarios investigados

#### ChromeDriver intermitente

Sintoma:

```text
Service /usr/bin/chromedriver unexpectedly exited. Status code was: 1
```

Medidas:

- Preflight antes de limpiar/descargar.
- Reintentos automaticos del wrapper.
- `MAX_CONCURRENT_DRIVER_STARTS=1`.
- Limpieza de perfiles/procesos antes de reintentos.
- Drop-in systemd para runtime snap.

#### Runtime systemd para Chromium snap

Drop-in documentado:

```ini
/etc/systemd/system/rpa-cext-diario.service.d/10-snap-runtime.conf

[Service]
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
```

Validar tambien:

```bash
loginctl show-user cenate -p RuntimePath -p Linger -p State
```

#### Timeout de systemd durante carga BD

El 2026-07-01 una corrida diaria descargo `113/113`, pero systemd la corto al cumplir 1 hora mientras estaba en `STAGING_LOAD`. Resultado: no hubo publicacion final ni refresh.

Correccion operativa aplicada en produccion:

```ini
/etc/systemd/system/rpa-cext-diario.service.d/20-timeout.conf

[Service]
TimeoutStartSec=3h
TimeoutStopSec=10min
```

Luego se ejecuto:

```bash
sudo systemctl daemon-reload
sudo systemctl reset-failed rpa-cext-diario.service
```

Este ajuste debe documentarse o versionarse formalmente si aun no esta en los docs del repo.

#### Paciente/profesional no aparecia en vista

Caso analizado:

- Centro/IPRESS: `739`.
- Profesional: Nathaly Medina Lopez.
- DNI profesional: `73863933`.
- El TXT manual mostraba registros, pero la vista no.

Causa raiz documentada:

El TXT de ExplotaDatos puede contener comillas no balanceadas. Si se lee como CSV estandar, el parser puede unir lineas y omitir registros posteriores.

Correccion:

Leer los TXT con:

```python
csv.reader(f, delimiter=delimiter, quoting=csv.QUOTE_NONE)
```

#### Paciente con campos corridos

Caso:

- Paciente: `09019956`.
- Profesional: `46362458`.
- Centro/IPRESS: `410`.

Se investigo porque el telefono aparecia en `cod_tipseguro`, lo que sugeria corrimiento de columnas posterior al campo `sexo`.

Conclusion operativa:

El analisis debe comparar TXT crudo del centro con staging y vista para determinar si el problema viene desde ExplotaDatos o de la carga a BD. El hallazgo de comillas no balanceadas llevo a reforzar el parser como texto plano delimitado.

### 5.10 Ultima ejecucion diaria monitoreada

Corrida:

```text
RUN_CEXT_PROD_DIARIO_20260701_171753
```

Resultado:

```text
TOTAL_INPUT=113
TOTAL_OK=113
TOTAL_FAIL=0
STAGING_LOAD=113/113
FINAL_PUBLISH_RESULT final_files=113
REFRESH_REPORTES_DIARIO OK
RUN_END 18:00:03
MAIL_SEND_OK en run.log
Duracion=2529s aprox.
```

Timer validado despues:

```text
rpa-cext-diario.timer: active
rpa-cext-diario.service: inactive
Proxima ejecucion observada: 2026-07-01 18:30 -05
```

## 6. RPA Mensual

### 6.1 Proposito

El RPA Mensual descarga informacion de Consulta Externa para un mes calendario completo.

Usos:

- Publicar bases mensuales.
- Alimentar BI del Observatorio.
- Mantener reportes mensuales actualizados.
- Cargar staging mensual en PostgreSQL.
- Ejecutar cierre mensual e historico cuando se indique.

Criticidad: alta. Se usa para produccion institucional, informes y dashboards.

### 6.2 Produccion

```text
Servidor: 10.0.89.241
Directorio: /home/cenate/rpa_cext_diario
Script: RPA_CEXT_PROD_MENSUAL.py
Wrapper: run_rpa_mensual.sh
Env real: .env_mensual
Timer: rpa-cext-mensual.timer
Service: rpa-cext-mensual.service
Horario: 04:00 diario
```

### 6.3 Flujo mensual

Cadena:

```text
rpa-cext-mensual.timer
  -> rpa-cext-mensual.service
    -> run_rpa_mensual.sh
      -> source .venv/bin/activate
        -> ENV_FILE=.env_mensual
          -> python -u RPA_CEXT_PROD_MENSUAL.py
```

Etapas:

1. `CONFIGURATION`
2. `LOG_INIT`
3. `MONTH_CONTEXT`
4. `DB_PRECHECK`
5. `CONTROL_DB_INIT`
6. `GSHEET_READ`
7. `OVERRIDE_CACHE`
8. `USER_HEALTH`
9. `DOWNLOAD`
10. `FALLBACK`
11. `STAGING_LOAD`
12. `FINAL_PUBLICATION`
13. `MEDICAL_STAFF_SYNC`
14. `REFRESH_MENSUAL`
15. `STAGING_PRUNE`
16. `MONTH_CLOSE`
17. `STATE_FINALIZATION`
18. `MAIL_NOTIFICATION`

### 6.4 Periodos soportados

Variable:

```text
MES_A_PROCESAR
```

Valores:

```text
ACTUAL
ANTERIOR
SIGUIENTE
YYYY-MM
lista separada por comas
```

Para cada periodo:

- Fecha inicial: primer dia del mes.
- Fecha final: ultimo dia del mes.
- TAG: `YYYYMMDD_YYYYMMDD`.
- Periodo: `YYYY-MM`.

### 6.5 Configuracion mensual

Archivo de ejemplo:

```text
rpa-mensual/config/.env.example
```

Variables clave:

```text
URL_HOME
FRM_MASIVAS
GSHEET_URL
CREDS_JSON
GSHEET_TABS
MES_A_PROCESAR
CLOSE_MONTH
CLOSE_MONTH_PERIOD
USER_* / PASSWORD_*
DOWNLOAD_DIRS
FINAL_PUBLISH_DIR
FINAL_PUBLISH_MIRRORS
HEADLESS
DOWNLOAD_TIMEOUT
BETWEEN_CENTERS_DELAY
RETRY_PER_CENTER
MAX_THREADS
MAX_CONCURRENT_DRIVER_STARTS
FORCE_REDOWNLOAD
FILE_SUFFIX
KEEP_ONLY_CURRENT_TAG
PG_*
SRC241_*
RPA_JOB_CODE
RPA_RUN_TYPE
CHROME_PROFILE_BASE_DIR
CHROME_PROFILE_MAX_AGE_HOURS
HEALTHCHECK_ENABLED
HEALTHCHECK_BLOCKING
DB_PRECHECK_ENABLED
DB_CONNECT_TIMEOUT_SECONDS
MAIL_ENABLED
SMTP_*
```

Valores de ejemplo:

```text
MAX_THREADS=6
MAX_CONCURRENT_DRIVER_STARTS=1
HEALTHCHECK_ENABLED=true
HEALTHCHECK_BLOCKING=true
DB_PRECHECK_ENABLED=true
```

### 6.6 Wrapper mensual

Archivo:

```text
rpa-mensual/scripts/run_rpa_mensual.sh
```

Responsabilidades:

- Exporta `TZ=America/Lima`.
- Exporta `ENV_FILE=.env_mensual`.
- Verifica Python del `.venv`.
- Verifica script principal.
- Verifica escritura en rutas compartidas:
  - `/mnt/comp_observatorio/BI_2025/Base_Consulta_Externa_2026`
  - `/mnt/abandonos/BASES`
- Usa `flock` con `/tmp/rpa_cext_mensual.lock`.
- Escribe log de orquestador mensual.
- Evita solapamiento de ejecuciones mensuales.

### 6.7 Codigo mensual

Archivo:

```text
rpa-mensual/src/RPA_CEXT_PROD_MENSUAL.py
```

Capacidades:

- Calcula uno o varios periodos desde `MES_A_PROCESAR`.
- Lee Google Sheets por columna del mes en espanol.
- Deduplica centros.
- Usa overrides aprendidos de macro efectiva.
- Ejecuta healthcheck por usuario/macro.
- Ejecuta fallback si el centro no esta en macro declarada.
- Descarga por macro usando `ThreadPoolExecutor`.
- Carga staging en `stg.cext_prod_mensual`.
- Publica en carpeta mensual principal.
- Publica en mirrors.
- Sincroniza medicos.
- Ejecuta `REFRESH_MENSUAL_ACTUAL`.
- Poda staging mensual por periodo.
- Ejecuta cierre mensual opcional si `CLOSE_MONTH=true`.
- Envia correo.

Mejoras incorporadas:

- `csv.field_size_limit` ampliado.
- Lectura con `csv.QUOTE_NONE`.
- Preflight ChromeDriver.
- `MAX_CONCURRENT_DRIVER_STARTS=1`.
- Publicacion mensual filtrada por centros descargados OK.
- Registro `FINAL_PUBLISH_SKIP_UNEXPECTED_FILES` para archivos sobrantes del periodo.

### 6.8 Cierre mensual

El cierre mensual sirve para:

- Reprocesar un mes completo.
- Republicar archivos para Observatorio/BI.
- Incorporar correcciones de atenciones cerradas tarde.
- Guardar historico mensual cerrado en BD.

Comando operativo conocido:

```bash
cd /home/cenate/rpa_cext_diario
source .venv/bin/activate
MES_A_PROCESAR=2026-06 CLOSE_MONTH=true CLOSE_MONTH_PERIOD=2026-06 ENV_FILE=.env_mensual python -u RPA_CEXT_PROD_MENSUAL.py
```

La corrida mensual diaria normal no guarda historico completo cada dia para evitar crecimiento innecesario. El historico se guarda al ejecutar cierre.

Si `CLOSE_MONTH=true`, el RPA intenta:

1. `CLOSE_MONTH_RAW_OK`
2. `CLOSE_MONTH_OK`

Si falla la rutina de cierre, puede registrar:

```text
CLOSE_MONTH_WARN
```

Esto no necesariamente invalida la descarga/publicacion mensual si `TOTAL_OK`, publicacion y refresh fueron correctos.

### 6.9 Incidentes mensuales investigados

#### Input 104 y publicacion 105

Corrida revisada:

```text
RUN_CEXT_PROD_MENSUAL_20260623_040037
Periodo=2026-06
TOTAL_INPUT=104
TOTAL_OK=104
TOTAL_FAIL=0
FINAL_PUBLISH_RESULT final_files=105
```

Causa:

Habia un archivo sobrante del mismo periodo en temporal:

```text
436_20260601_20260630_PacCitCExt.txt
```

No pertenecia al input ni estaba registrado en `raw.archivo_descargado` del run.

Correccion:

- Filtrar publicacion mensual por centros descargados correctamente.
- Omitir archivos sobrantes.
- Registrar `FINAL_PUBLISH_SKIP_UNEXPECTED_FILES`.

#### DB_FILE_WARN

Archivo observado:

```text
406_20260601_20260630_PacCitCExt.txt
```

Sintoma:

```text
field larger than field limit (131072)
```

Correccion:

`csv.field_size_limit` ampliado en diario y mensual.

#### Cierre Junio 2026

Se ejecuto cierre mensual de junio 2026 de forma manual en produccion por necesidad operativa.

Evidencia de una corrida de cierre:

```text
TOTAL_INPUT=105
TOTAL_OK=105
TOTAL_FAIL=0
FINAL_PUBLISH_RESULT final_files=105
REFRESH_MENSUAL_ACTUAL periodo=2026-06
RUN_END
MAIL_SEND_OK
CLOSE_MONTH_WARN | periodo=2026-06 | No se encontro una corrida mensual valida para el periodo 2026-06
```

Interpretacion:

- Descarga/publicacion/refresh terminaron.
- Warning corresponde a la rutina historica de cierre BD.
- El warning no significa que los archivos mensuales no se hayan publicado.

## 7. Componentes compartidos

Carpeta:

```text
shared/
```

Actualmente reservada para extraer logica comun cuando haya estabilidad suficiente.

Candidatos:

- Login comun a ExplotaDatos.
- Seleccion comun de centro/IPRESS.
- Lectura Google Sheets.
- Credenciales por macroregion.
- Selenium/ChromeDriver.
- Validacion de descargas.
- Publicacion con staging/swap.
- Registro de estados.
- Notificaciones.

Decision actual:

Primero documentar patron comun. Luego extraer codigo cuando diario y mensual esten estables.

## 8. Plantilla para nuevos RPAs

Archivo:

```text
docs/plantilla-rpa.md
```

Cada nuevo RPA debe documentar:

1. Resumen.
2. Proposito funcional.
3. Flujo general.
4. Configuracion.
5. Operacion.
6. Errores conocidos.
7. Contexto para IA.

## 9. Modelo de trabajo recomendado

Para cualquier nuevo cambio:

1. Crear rama desde `main` o continuar en rama `codex/*` segun corresponda.
2. Revisar `AI_CONTEXT.md` del RPA.
3. Revisar docs afectados.
4. Modificar codigo y wrapper si aplica.
5. Actualizar `.env.example` si se agregan variables.
6. Actualizar docs operativos.
7. Probar en servidor con ejecucion controlada.
8. Verificar:
   - `TOTAL_INPUT`
   - `TOTAL_OK`
   - `TOTAL_FAIL`
   - `STAGING_LOAD`
   - `FINAL_PUBLISH_RESULT`
   - `REFRESH_*`
   - `RUN_END`
   - `MAIL_SEND_OK`
   - estado systemd
   - timer activo
9. Commit con mensaje claro.
10. Push a GitHub.
11. Merge a `main` solo cuando este validado.

## 10. Criterios de exito operativo

Una corrida diaria o mensual solo debe considerarse lista para consumo cuando:

- Descargas terminaron.
- No hay fallas criticas.
- Archivos pasaron validacion.
- Staging cargo lo esperado.
- Publicacion final termino.
- Sync de medicos termino si aplica.
- Refresh termino.
- Prune termino o registro warning no critico.
- Run llego a `RUN_END`.
- Servicio systemd queda `inactive` o `dead` con codigo exitoso.
- Timer queda `active`.

Correo:

- Si falla el correo pero la data esta lista, el estado puede ser `SUCCESS_WITH_WARNINGS`.
- La notificacion no debe decidir disponibilidad de data.

## 11. Riesgos pendientes

1. Consolidar en docs el drop-in `20-timeout.conf` aplicado en produccion.
2. Definir si el mensual debe publicar parcial cuando `TOTAL_FAIL > 0`.
3. Crear pruebas automaticas para `derive_final_status`.
4. Crear pruebas para parser TXT con comillas no balanceadas.
5. Evaluar migracion de Chromium snap a Chrome/ChromeDriver no snap si reaparecen fallas.
6. Versionar o documentar mejor units systemd completos.
7. Decidir si `artifacts/` se versiona o se ignora.
8. Separar logica comun en `shared/` cuando haya estabilidad.

## 12. Archivos que otra IA debe leer primero

Para RPA Diario:

```text
README.md
rpa-diario/AI_CONTEXT.md
rpa-diario/README.md
rpa-diario/docs/02-arquitectura.md
rpa-diario/docs/03-flujo-proceso.md
rpa-diario/docs/05-operacion-diaria.md
rpa-diario/docs/06-estados-y-control.md
rpa-diario/docs/07-errores-conocidos.md
rpa-diario/src/RPA_CEXT_PROD_DIARIO.py
rpa-diario/scripts/run_rpa_diario.sh
```

Para RPA Mensual:

```text
README.md
rpa-mensual/AI_CONTEXT.md
rpa-mensual/README.md
rpa-mensual/docs/02-arquitectura.md
rpa-mensual/docs/03-flujo-proceso.md
rpa-mensual/docs/05-operacion-mensual.md
rpa-mensual/docs/06-estados-y-control.md
rpa-mensual/docs/07-errores-conocidos.md
rpa-mensual/docs/08-hallazgos-tecnicos.md
rpa-mensual/src/RPA_CEXT_PROD_MENSUAL.py
rpa-mensual/scripts/run_rpa_mensual.sh
```

## 13. Regla final para futuras IAs

No asumir que una corrida fue exitosa solo por ver descargas OK.

Validar siempre en este orden:

1. No hay ejecucion activa inesperada.
2. `TOTAL_OK/TOTAL_FAIL`.
3. `STAGING_LOAD`.
4. `FINAL_PUBLISH_RESULT`.
5. `REFRESH_*`.
6. `RUN_END`.
7. `MAIL_SEND_OK` o warning de correo.
8. Estado systemd.
9. Timer activo y proxima ejecucion.

No exponer credenciales reales. No ejecutar mensual o cierre mensual sin autorizacion explicita. No solapar ejecuciones manuales con timers activos.
