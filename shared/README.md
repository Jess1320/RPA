# Componentes Compartidos

Esta carpeta queda reservada para logica reutilizable entre RPAs.

Componentes candidatos:

- Login comun a ExplotaDatos.
- Seleccion comun de centro/IPRESS.
- Lectura de Google Sheets.
- Manejo de credenciales por macroregion.
- Descarga controlada con Selenium.
- Validacion de archivos descargados.
- Registro de estados por etapa.
- Notificaciones.

La logica compartida debe incorporarse gradualmente. Primero se documenta el patron comun y luego se extrae codigo cuando haya estabilidad suficiente.

## Usuarios maestros

Los RPAs que descargan desde ExplotaDatos deben usar un archivo privado compartido para los usuarios por macroregion:

- Archivo real fuera de Git: `shared/config/.env_usuarios`
- Ejemplo versionado: `shared/config/.env_usuarios.example`
- Variable opcional para apuntar a otra ruta: `RPA_USERS_ENV_FILE`

Variables esperadas:

- `USER_CENTRO` / `PASSWORD_CENTRO`
- `USER_NORTE` / `PASSWORD_NORTE`
- `USER_SUR` / `PASSWORD_SUR`
- `USER_LIMA_ORIENTE` / `PASSWORD_LIMA_ORIENTE`

El archivo especifico de cada RPA sigue manejando rutas, Google Sheets, logs, correo y otros parametros. Las credenciales de descarga quedan centralizadas para que un cambio de clave o usuario se haga una sola vez.
