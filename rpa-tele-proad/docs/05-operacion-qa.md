# Operacion QA - RPA Tele Proad

## Prueba minima

Usar variables de prueba:

```env
MAX_CENTERS=1
MAIL_ENABLED=false
STAGING_DOWNLOAD_DIR=tmp/downloads
```

Para probar solo una ruta:

```env
RUN_HOSPITALIZACION=true
RUN_EMERGENCIA=false
```

## Criterios

- Lee IPRESS desde `TELE_PROAD`.
- Usa usuarios maestros por macroregion.
- Selecciona `SERVICIO=AJ1`.
- Descarga primero en staging.
- Valida prefijo `centro_YYYYMMDD_YYYYMMDD_`.
- Valida sufijo `IntercxServ` o `EmerInterconsultaxServ`.
- Publica solo despues de validar.
- No elimina archivos de otros periodos.
- Elimina staging y perfiles `chrome-profile-*` al finalizar.
