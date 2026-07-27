# Operacion QA - RPA Tele CAM

## Prueba minima

Usar variables de prueba:

```env
MAX_CENTERS=1
MAIL_ENABLED=false
STAGING_DOWNLOAD_DIR=tmp/downloads
```

## Criterios

- Lee IPRESS desde `DIRECT_CENTERS`, inicialmente `739`.
- Usa usuarios maestros por macroregion.
- Selecciona valores por codigo: `2`, `2`, `F41`, `A1`, `142`, `xls`.
- Descarga primero en staging.
- Valida prefijo `centro_YYYYMMDD_YYYYMMDD_`.
- Valida sufijo `AtenNoMedxSubAct`.
- Publica solo despues de validar.
- No elimina archivos de otros periodos.
- Elimina staging y perfiles `chrome-profile-*` al finalizar.
