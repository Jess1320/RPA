# RPA Diario - Consulta Externa Produccion

## Resumen

El RPA Diario extrae informacion asistencial desde ExplotaDatos de ESSI para centros/IPRESS configurados en Google Sheets. La informacion descargada se valida, registra, carga en PostgreSQL, publica en una carpeta compartida y queda disponible para procesos de CENATE.

## Datos principales

| Campo | Valor |
| --- | --- |
| Codigo del job | `CEXT_PROD_DIARIO` |
| Lenguaje | Python 3.12 |
| Automatizacion web | Selenium WebDriver |
| Navegador | Chromium |
| Ejecucion | Ubuntu Server 24.04 LTS |
| Orquestacion | systemd timer + systemd service + Bash |
| Base de control | PostgreSQL `rpa_control` |
| Configuracion funcional | Google Sheets |
| Sistema origen | ESSI / ExplotaDatos |
| Criticidad | Alta |

## Flujo resumido

1. systemd inicia el wrapper `run_rpa_diario.sh`.
2. El wrapper activa el entorno Python y ejecuta el RPA.
3. El RPA carga configuracion desde `.env`.
4. Consulta Google Sheets para obtener centros/IPRESS habilitados.
5. Ingresa a ExplotaDatos con credenciales institucionales.
6. Selecciona el centro/IPRESS en el combo del reporteador.
7. Navega directamente al formulario del reporte usando la URL especifica del modulo.
8. Completa criterios de consulta y descarga el archivo.
9. Valida archivos, cabeceras, TAG, tamano y estabilidad.
10. Registra resultados y carga staging en PostgreSQL.
11. Publica archivos en carpeta compartida.
12. Ejecuta sincronizacion y refresh de reportes derivados.
13. Cierra estados y envia notificacion.

## Documentacion

- [Contexto funcional](docs/01-resumen-funcional.md)
- [Arquitectura](docs/02-arquitectura.md)
- [Flujo del proceso](docs/03-flujo-proceso.md)
- [Configuracion](docs/04-configuracion.md)
- [Operacion diaria](docs/05-operacion-diaria.md)
- [Estados y control](docs/06-estados-y-control.md)
- [Errores conocidos](docs/07-errores-conocidos.md)
- [Roadmap tecnico](docs/08-roadmap-tecnico.md)
- [Contexto para IA](AI_CONTEXT.md)

## Regla de mantenimiento

Todo cambio funcional debe actualizar la documentacion afectada. Si cambia el flujo, se actualiza `docs/03-flujo-proceso.md`. Si cambia una variable, se actualiza `docs/04-configuracion.md`. Si se detecta un error nuevo, se registra en `docs/07-errores-conocidos.md`.

