# Arquitectura

## Plataforma

- Python 3.12.
- Selenium WebDriver.
- Chromium + ChromeDriver.
- ThreadPoolExecutor con hasta 6 workers.
- Ubuntu Server 24.04 LTS.
- systemd timer + systemd service + script Bash.
- PostgreSQL `rpa_control`.
- Google Sheets.
- SMTP.

## Componentes

| Componente | Responsabilidad |
| --- | --- |
| systemd timer | Programar ejecuciones |
| systemd service | Iniciar el proceso controlado |
| `run_rpa_diario.sh` | Preparar entorno y lanzar Python |
| RPA Python | Orquestar descarga, validacion, carga, publicacion y estado |
| Google Sheets | Definir centros/IPRESS habilitados |
| Selenium | Automatizar ExplotaDatos |
| PostgreSQL | Control, auditoria, staging y estados |
| Carpeta temporal | Recibir descargas |
| Carpeta compartida | Publicar dataset vigente |
| SMTP | Notificar resultado |

## Patron comun de ExplotaDatos

Todos los RPAs que usan ExplotaDatos comparten:

1. Una ruta unica de entrada.
2. Solicitud de credenciales.
3. Login.
4. Pantalla base del reporteador.
5. Combo de centro/IPRESS.
6. Seleccion de centro segun codigo.
7. Navegacion hacia una URL interna del reporte especifico.

La recomendacion arquitectonica es extraer esta logica comun a `shared/` cuando haya codigo consolidado, para evitar duplicar login, credenciales, seleccion de IPRESS y manejo de sesion en cada RPA.

## Navegacion por URL interna

Actualmente cada RPA usa una URL especifica obtenida desde herramientas de desarrollador del navegador. Esta decision evita depender de menus y submenus visuales complejos del reporteador.

Esta estrategia es valida, pero debe documentarse por RPA:

- URL interna del formulario.
- Reporte al que corresponde.
- Parametros esperados.
- Riesgo si cambia el reporteador.
- Validacion que confirma que se llego al formulario correcto.

