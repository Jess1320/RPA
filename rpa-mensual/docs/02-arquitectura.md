# Arquitectura

## Plataforma

- Python 3.
- Selenium WebDriver.
- Chromium + ChromeDriver.
- ThreadPoolExecutor.
- Google Sheets.
- PostgreSQL `rpa_control`.
- systemd timer y service.
- Bash wrapper.
- SMTP.

## Componentes

| Componente | Responsabilidad |
| --- | --- |
| `rpa-cext-mensual.timer` | Disparar la ejecucion diaria a las `04:00` |
| `rpa-cext-mensual.service` | Ejecutar el wrapper mensual como usuario `cenate` |
| `run_rpa_mensual.sh` | Activar venv, exportar `ENV_FILE=.env_mensual` y lanzar Python |
| `RPA_CEXT_PROD_MENSUAL.py` | Orquestar descarga, staging, publicacion, refresh y notificacion |
| `.env_mensual` | Configuracion real fuera de Git |
| Google Sheets | Lista de centros/IPRESS marcados por mes y macroregion |
| ExplotaDatos | Fuente web de descarga |
| PostgreSQL | Control de ejecucion, staging mensual, estados y alertas |
| Carpeta temporal | Recibir descargas del navegador |
| Carpeta final | Publicar archivos mensuales vigentes |
| Carpeta espejo | Replicar publicacion mensual a ruta adicional |

## Patron ExplotaDatos

El mensual comparte con el diario:

1. Entrada por `URL_HOME`.
2. Login con credenciales por macroregion.
3. Cambio al frame `cuerpo`.
4. Seleccion de `centroAsistencial`.
5. Envio del formulario base.
6. Navegacion directa a `FRM_MASIVAS`.
7. Carga del formulario `PacCitCExt`.

La diferencia visual del formulario es el rango de fechas:

- Mensual: `fe_ini = 01/MM/YYYY`.
- Mensual: `fechaFin = ultimo dia del mes`.

## Publicacion

La publicacion mensual no reemplaza toda la carpeta final. Solo elimina y reemplaza archivos cuyo nombre pertenece al periodo procesado. Esto permite convivir con otros meses si la ruta contiene historico mensual.

## Diferencias contra el diario

| Area | Diario | Mensual |
| --- | --- | --- |
| Periodo | Dia operativo/futuro corto | Mes completo |
| Env | `.env` | `.env_mensual` |
| Timer | Muchos horarios diarios | Una vez al dia a las `04:00` |
| Staging | `stg.cext_prod_diario` | `stg.cext_prod_mensual` |
| Refresh | `REFRESH_REPORTES_DIARIO` | `REFRESH_MENSUAL_ACTUAL` |
| Publicacion | Ruta diaria | Ruta mensual principal y espejo |
| Cierre | No aplica | `CLOSE_MONTH` opcional |
| Healthcheck macro | No en la version diaria actual | Si |

