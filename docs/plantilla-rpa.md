# Plantilla de Documentacion para un RPA

Usar esta plantilla para crear nuevos RPAs en el repositorio.

## 1. Resumen

- Nombre del RPA:
- Codigo del job:
- Tipo de ejecucion: ordenador / servidor
- Criticidad:
- Responsable funcional:
- Responsable tecnico:
- Sistema origen:
- Sistema destino:

## 2. Proposito funcional

Describir en lenguaje de usuario que problema resuelve el RPA y que informacion produce.

## 3. Flujo general

1. Inicio de ejecucion.
2. Lectura de configuracion.
3. Login en sistema origen.
4. Seleccion de centro/IPRESS.
5. Navegacion al reporte o formulario.
6. Descarga o procesamiento.
7. Validacion.
8. Publicacion.
9. Notificacion.

## 3.1 Patron de usuarios maestros, macroregion y fallback

Para RPAs que descargan desde ExplotaDatos con centros/IPRESS por macroregion, tomar como referencia operativa el RPA Diario.

Reglas obligatorias:

- Usar usuarios maestros por macroregion.
- Agrupar los centros/IPRESS por macroregion antes de descargar.
- Intentar primero la descarga primaria con el usuario maestro de la macroregion declarada.
- Si el centro no aparece para esa macroregion, usar fallback con los demas usuarios maestros.
- No usar el healthcheck como bloqueo duro de una macroregion.
- El healthcheck puede registrar diagnostico, pero no debe impedir la descarga primaria si el flujo real de descarga puede validar el acceso.
- Considerar `NO_ENCONTRADO_EN_WEB` como senal de centro no visible en el selector del formulario para ese usuario/macroregion, no como prueba automatica de falta de acceso.
- Diferenciar en logs los casos de centro no encontrado, timeout de descarga y excepciones tecnicas de navegador.

Motivo: en ExplotaDatos el healthcheck puede dar falsos negativos aunque el usuario maestro luego descargue correctamente. El criterio operativo validado es el del RPA Diario: ejecutar la descarga primaria y usar fallback solo cuando el formulario no muestra el centro o la descarga falla.

## 4. Configuracion

Documentar variables requeridas sin incluir secretos reales.

```text
VARIABLE=descripcion
```

## 5. Operacion

- Como ejecutar manualmente.
- Como validar una corrida correcta.
- Donde revisar logs.
- Como detener o reiniciar.

## 6. Errores conocidos

```text
Error:
Causa probable:
Validacion:
Accion recomendada:
```

## 7. Contexto para IA

Indicar que archivos debe leer la IA antes de modificar el RPA y que reglas no debe romper.
