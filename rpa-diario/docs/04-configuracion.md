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

Como todos los RPAs usan el mismo proceso base de login, se recomienda no repetir credenciales en cada proyecto sin control. Opciones:

- Archivo `.env` por entorno, fuera de Git.
- Variables de entorno del servidor.
- Secret manager.
- Archivo comun local no versionado para credenciales de ExplotaDatos.

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

