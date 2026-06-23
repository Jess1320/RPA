# Roadmap Tecnico

## Prioridad 0

- Mover el calculo de `final_status` al final real de la corrida. Preparado en version controlada.
- Usar una funcion unica para derivar estado. Preparado en version controlada.
- Calcular duracion despues de todas las etapas obligatorias. Preparado en version controlada.
- Restaurar bloqueo `flock` y validacion de mount en el wrapper. Preparado en version controlada.
- Registrar version y hash del codigo.
- Registrar inicio y fin de cada etapa.

## Prioridad 1

- Persistir estado por etapa en PostgreSQL.
- Generar correo desde snapshot persistido.
- Separar estado de descarga, publicacion, refresh y notificacion.

## Prioridad 2

- Crear contrato de disponibilidad para consumidores.
- Exponer `data_ready`.
- Crear vista de ultimo run listo.

## Prioridad 3

- Agregar pruebas automatizadas para derivacion de estados.
- Probar escenarios de falla, cancelacion, timeout y correo fallido.

## Prioridad 4

- Incorporar idempotencia por etapa.
- Permitir reintento parcial sin redescargar todo.
- Reenviar notificaciones desde outbox.

## Prioridad 5

- Mejorar observabilidad.
- Medir duracion por etapa e IPRESS.
- Registrar timeouts, reintentos, archivos publicados y antiguedad del ultimo `data_ready`.

## Prioridad 6

- Usar IA solo para diagnostico.
- Clasificar errores y resumir logs.
- Mantener `state_change_authorized = false` para diagnosticos generados por IA.
