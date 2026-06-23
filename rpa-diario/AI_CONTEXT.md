# Contexto para IA - RPA Diario

Leer este archivo antes de analizar o modificar el RPA Diario.

## Objetivo

Automatizar la descarga periodica de informacion de Consulta Externa desde ExplotaDatos/ESSI para centros/IPRESS definidos en Google Sheets, publicar los archivos validados y dejar un estado confiable para consumidores internos de CENATE.

## Patron comun a todos los RPAs

Todos los RPAs que usan ExplotaDatos comparten esta secuencia base:

1. Abrir la ruta unica de ExplotaDatos.
2. Solicitar credenciales.
3. Iniciar sesion.
4. Permanecer dentro del reporteador.
5. Seleccionar centro/IPRESS desde un combo visual.
6. Consultar Google Sheets para saber que codigos de centro/IPRESS procesar.
7. Cambiar el centro/IPRESS activo segun cada codigo.
8. Navegar al formulario especifico del reporte.
9. Completar criterios y descargar.

La diferencia entre RPAs aparece despues de seleccionar el centro/IPRESS: cada RPA usa una URL interna especifica del reporteador para llegar directamente al formulario requerido.

## Restricciones importantes

- No subir credenciales reales.
- No repetir credenciales en cada proyecto si se puede centralizar la configuracion.
- No considerar a la IA como fuente autoritativa del estado transaccional.
- El estado oficial debe derivarse por reglas deterministicas.
- No calcular `overall_status` antes de cerrar las etapas criticas.
- No enviar notificaciones usando estados provisionales como si fueran finales.
- No solapar ejecuciones manuales y automaticas.

## Componentes criticos

- Selenium y Chromium para navegar ExplotaDatos.
- Google Sheets como fuente funcional de centros/IPRESS.
- PostgreSQL `rpa_control` como control de corrida, staging y auditoria.
- Carpeta temporal local para descargas.
- Carpeta compartida para publicacion.
- systemd timer/service para ejecucion programada.
- SMTP para notificaciones.

## Problema tecnico principal documentado

El RPA puede reportar `PARTIAL_SUCCESS` aunque las descargas, publicacion y refresh hayan terminado correctamente, si el estado final se calcula antes de actualizar los indicadores de etapas complementarias.

La correccion recomendada es tener una funcion unica de derivacion del estado final y ejecutarla solo despues de persistir estados terminales de todas las etapas obligatorias.

## Archivos que una IA debe revisar antes de cambiar codigo

1. `README.md`
2. `docs/02-arquitectura.md`
3. `docs/03-flujo-proceso.md`
4. `docs/06-estados-y-control.md`
5. `docs/07-errores-conocidos.md`
6. Codigo fuente principal cuando sea incorporado al repositorio.

## Criterio de exito operativo

Una corrida solo debe considerarse lista para consumo cuando:

- Descarga finalizo.
- Staging finalizo.
- Publicacion finalizo.
- Sincronizacion y refresh criticos finalizaron.
- `data_ready = true`.
- `overall_status` esta en `SUCCESS` o `SUCCESS_WITH_WARNINGS`.

