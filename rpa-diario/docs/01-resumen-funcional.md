# Resumen Funcional

## Proposito

El RPA Diario extrae informacion asistencial desde ExplotaDatos, reporteador asociado a ESSI/EsSalud. CENATE utiliza esta automatizacion porque no dispone de acceso directo a la base transaccional de ESSI.

## Informacion obtenida

- Citas programadas.
- Fecha y hora de citas.
- Estado y condicion de cita.
- Pacientes.
- Profesionales de salud.
- Servicios y actividades asistenciales.
- Programaciones profesionales.
- Centros asistenciales e IPRESS.
- Consultorios.
- Modalidad de atencion.
- Datos para reportes de pendientes y citados a futuro.

## Uso posterior

La informacion descargada se usa para:

- Visualizar citas en la intranet de CENATE.
- Identificar pacientes pendientes.
- Gestionar captacion y confirmacion de citas.
- Generar reportes operativos y directivos.
- Sincronizar datos hacia la plataforma institucional.
- Confirmar disponibilidad de datos para equipos tecnicos.

## Criticidad

Alta. Un estado incorrecto puede generar la misma incertidumbre operativa que una falla real, porque los usuarios no pueden distinguir si los datos fueron descargados, publicados, sincronizados o si solo fallo la notificacion.

