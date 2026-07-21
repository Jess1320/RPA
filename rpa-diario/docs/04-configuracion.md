# Configuracion

## Principio

Las credenciales reales no deben almacenarse en Git. Cada RPA debe incluir solo archivos de ejemplo y documentacion de variables.

## Variables esperadas

Ver tambien `config/.env.example`.

```text
EXPLOTADATOS_URL=Ruta unica de entrada al reporteador
EXPLOTADATOS_REPORT_URL=URL interna del formulario especifico del RPA Diario
GOOGLE_SHEETS_ID=ID del spreadsheet funcional
GOOGLE_SHEETS_TABS=Pestanas a leer
POSTGRES_DSN=Cadena de conexion a rpa_control
SMTP_HOST=Servidor SMTP
SMTP_PORT=Puerto SMTP
SMTP_FROM=Correo remitente
SMTP_TO=Destinatarios
MAX_WORKERS=Nivel de paralelismo
DOWNLOAD_TIMEOUT_SECONDS=Timeout de descarga
```

## Credenciales compartidas

Como todos los RPAs usan el mismo proceso base de login, las credenciales de descarga deben centralizarse:

- Archivo privado recomendado: `shared/config/.env_usuarios`.
- Ruta alternativa por entorno: `RPA_USERS_ENV_FILE`.
- Variables esperadas: `USER_CENTRO`, `PASSWORD_CENTRO`, `USER_NORTE`, `PASSWORD_NORTE`, `USER_SUR`, `PASSWORD_SUR`, `USER_LIMA_ORIENTE`, `PASSWORD_LIMA_ORIENTE`.

El `.env` del RPA debe conservar rutas, Google Sheets, correo, base de control y parametros propios del job. Si el `.env` existente aun contiene credenciales por macro, el RPA sigue siendo compatible, pero el archivo maestro tiene prioridad cuando existe.

## Configuracion por RPA

Cada RPA debe documentar:

- URL interna del reporte.
- Nombre funcional del reporte.
- Criterios requeridos.
- Formato de descarga.
- Rango de fechas.
- Nombre esperado de archivo.
- Tablas destino.
- Indicadores de exito.
