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

