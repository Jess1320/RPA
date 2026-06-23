# Errores Conocidos

## Estado `PARTIAL_SUCCESS` falso

**Causa probable:** el estado final se calcula antes de actualizar los indicadores de refresh, reportes derivados o etapas complementarias.

**Validacion:**

- Total OK igual al total esperado.
- Total FAIL igual a cero.
- Publicacion final OK.
- Logs posteriores indican refresh OK.
- Correo o base conservan `PARTIAL_SUCCESS`.

**Accion recomendada:**

- Mover la derivacion oficial del estado al final real de la corrida.
- Recalcular una sola vez desde estados persistidos.
- Generar correo desde el snapshot final persistido.

## Posible solapamiento de ejecuciones

**Causa probable:** una ejecucion manual coincide con la automatica.

**Validacion:**

- Dos procesos Python activos.
- Dos carpetas temporales con corridas simultaneas.
- Logs con horarios superpuestos.

**Accion recomendada:**

- Usar `flock` en el wrapper Bash.
- Evaluar advisory lock de PostgreSQL.

## Cambio visual o funcional en ExplotaDatos

**Causa probable:** cambio en combo de IPRESS, formulario, URL interna o criterios del reporteador.

**Validacion:**

- Selenium no encuentra elementos.
- La URL interna ya no abre el formulario esperado.
- Los archivos descargados cambian de nombre, cabecera o contenido.

**Accion recomendada:**

- Validar manualmente ExplotaDatos.
- Confirmar URL interna del reporte.
- Actualizar selectores y criterios.
- Registrar el cambio en esta documentacion.

## Falla de credenciales

**Causa probable:** usuario, password o permisos expirados.

**Validacion:**

- Login rechazado.
- No aparece combo de IPRESS.
- Mensaje de sesion invalida o permisos insuficientes.

**Accion recomendada:**

- Validar credenciales fuera del RPA.
- Confirmar permisos por macroregion.
- Actualizar secreto fuera de Git.

