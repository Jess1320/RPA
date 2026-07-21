# Pase productivo - RPAs migrados

Fecha: 2026-07-04

## Estado

Se desplego codigo y configuracion privada en el servidor productivo `10.0.89.241`.

| RPA | Ruta codigo | Timer | Estado |
| --- | --- | --- | --- |
| Orquestador madrugada | `/home/cenate/rpa_orquestador_madrugada` | `rpa-orquestador-madrugada.timer` | Activo |
| Tele Triaje | `/home/cenate/rpa_tele_triaje` | `rpa-tele-triaje.timer` | Deshabilitado; lo ejecuta el orquestador |
| Tele Urgencia | `/home/cenate/rpa_tele_urgencia` | `rpa-tele-urgencia.timer` | Deshabilitado; lo ejecuta el orquestador |
| Medico y No Medico | `/home/cenate/rpa_medico_no_medico` | `rpa-medico-no-medico.timer` | Deshabilitado; lo ejecuta el orquestador |
| Mensual | `/home/cenate/rpa_cext_diario` | `rpa-cext-mensual.timer` | Deshabilitado; lo ejecuta el orquestador |

## Horarios productivos

| RPA | Hora |
| --- | --- |
| Orquestador madrugada | 01:00 |

El timer del orquestador quedo con `Persistent=false` para evitar ejecuciones inmediatas por horarios vencidos al activarlo el mismo dia del pase. Los timers individuales de los RPAs incluidos quedaron deshabilitados para evitar duplicados.

## Rutas de publicacion

Tele Triaje:

```text
/mnt/comp_observatorio/BI_2025/Bases_Teletriaje_2026
```

Tele Urgencia:

```text
/mnt/comp_observatorio/BI_2025/Bases_Teleurgencias_2026
```

Medico y No Medico:

```text
/mnt/BD_CControl/ENFE. INFEC Y TROP/TELEDENGUE NUEVO/TELEMONITOREO MEDICO
/mnt/BD_CControl/ENFE. INFEC Y TROP/TELEDENGUE NUEVO/TELEMONITOREO ENFERMERIA
```

El montaje `BD_CControl` quedo activo en produccion usando la cuenta `cenate.db01` configurada en el servidor.

## Historicos

Los scripts no hacen limpieza general de carpeta. La limpieza previa solo borra archivos que coinciden con:

```text
centro_YYYYMMDD_YYYYMMDD_*.txt
```

y con el sufijo esperado del RPA. Por eso, archivos de periodos antiguos con otro rango de fechas no deben verse afectados.

## Configuracion privada

Usuarios maestros:

```text
/home/cenate/shared/config/.env_usuarios
```

Cada RPA tiene su `.env` privado en su carpeta productiva y apunta a ese archivo mediante `RPA_USERS_ENV_FILE`.

## Validaciones realizadas

- Se valido que el venv compartido de Diario tenga dependencias requeridas.
- Se compilaron los scripts Python de los tres RPAs en produccion.
- Se verifico existencia de `.env`, JSON de Google y archivo de usuarios maestros.
- Se activaron timers de Tele Triaje y Tele Urgencia.
- Se activo el timer de Medico y No Medico despues de validar acceso a `BD_CControl`.
- Se agrego soporte de correo y se copio la configuracion `MAIL_*`/`SMTP_*` desde el RPA Diario.

Durante la preparacion inicial no se ejecuto smoke Selenium porque `rpa-cext-diario.service` estaba activo. Al terminar Diario, se ejecuto smoke productivo controlado con `MAX_CENTERS=1`.

Resultado smoke productivo:

| RPA | Resultado |
| --- | --- |
| Tele Triaje | `exit_code=0`, macro `SUR`, centro `127` OK |
| Tele Urgencia | `exit_code=0`, macro `SUR`, centro `127` OK |
| Medico y No Medico | `exit_code=0`, macro `CENTRO`, centro `739` OK para `MEDICO` y `NO_MEDICO` |

Archivos confirmados:

```text
/mnt/comp_observatorio/BI_2025/Bases_Teletriaje_2026/127_20260701_20260731_PacAtenTriaje.txt
/mnt/comp_observatorio/BI_2025/Bases_Teleurgencias_2026/127_20260701_20260731_PacAtendxTopico.txt
/mnt/BD_CControl/ENFE. INFEC Y TROP/TELEDENGUE NUEVO/TELEMONITOREO MEDICO/739_20260701_20260731_DxMedSer.txt
/mnt/BD_CControl/ENFE. INFEC Y TROP/TELEDENGUE NUEVO/TELEMONITOREO ENFERMERIA/739_20260701_20260731_DxNoMedSer.txt
```

## Comandos de verificacion

```bash
systemctl list-timers --all 'rpa-tele-*' 'rpa-medico-*' --no-pager
systemctl status rpa-tele-triaje.timer rpa-tele-urgencia.timer --no-pager
systemctl status rpa-medico-no-medico.timer --no-pager
```

Despues de la primera madrugada:

```bash
tail -100 /home/cenate/rpa_medico_no_medico/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
tail -100 /home/cenate/rpa_tele_triaje/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
tail -100 /home/cenate/rpa_tele_urgencia/orchestrator_logs/orchestrator_$(date +%Y%m%d).log
```

Criterios:

- `ORCH_END | exit_code=0`
- `MACRO_START` y `MACRO_END`
- Sin `SIN_MACRO`
- Sin fallas finales
- `MAIL_OK`

## Orquestador madrugada

El 2026-07-04 se desplego `/home/cenate/rpa_orquestador_madrugada` y se activo `rpa-orquestador-madrugada.timer` para ejecutar a la `01:00`.

Orden configurado:

```text
MENSUAL,TELE_TRIAJE,TELE_URGENCIA,MEDICO_NO_MEDICO
```

El orquestador ejecuta los RPAs con `MAIL_ENABLED=false` para evitar correos individuales y luego envia un unico correo consolidado con:

- mensaje sugerido para WhatsApp;
- resumen por RPA;
- IPRESS fallidas;
- tipo de descarga, cuando aplique;
- usuario logico;
- login enmascarado;
- motivo y fase de falla;
- adjuntos `reporte_madrugada.csv` y `reporte_madrugada.json`.

Una falla en un RPA no detiene los siguientes.

## Validacion de correo

El 2026-07-04 se ejecutaron manualmente los tres RPAs en produccion usando `.env` productivo y `RUN_NAME` de prueba de correo.

| RPA | Run dir | Resultado |
| --- | --- | --- |
| Medico y No Medico | `/home/cenate/rpa_medico_no_medico/logs/RUN_MEDICO_NO_MEDICO_MAIL_TEST_20260704_200137` | `exit_code=0`, centro `739` OK para `MEDICO` y `NO_MEDICO`, `MAIL_OK` |
| Tele Triaje | `/home/cenate/rpa_tele_triaje/logs/RUN_TELE_TRIAJE_MAIL_TEST_20260704_200306` | `exit_code=0`, 5/5 centros OK, `summary.csv`, `MAIL_OK` |
| Tele Urgencia | `/home/cenate/rpa_tele_urgencia/logs/RUN_TELE_URGENCIA_MAIL_TEST_20260704_200537` | `exit_code=0`, 4/4 centros OK, `summary.csv`, `MAIL_OK` |

## Pendientes

- Validar la primera ejecucion automatica del orquestador el 2026-07-05.
- Reactivar el timer de Diario cuando se decida cerrar la ventana operativa:

```bash
sudo systemctl start rpa-cext-diario.timer
```

- Agregar control DB para panel.

## Diagnostico BD_CControl

Desde el servidor productivo `10.0.89.241`, la cuenta configurada en `/etc/samba/cred_cenate_db01` puede intentar montar el recurso:

```text
//10.0.89.147/BD_CControl
```

pero el servidor remoto responde:

```text
NT_STATUS_ACCESS_DENIED listing \*
```

El montaje CIFS podia quedar creado, pero `ls /mnt/BD_CControl` devolvia `Permission denied` tanto para `root` como para `cenate`. Esto indicaba permiso SMB/NTFS insuficiente para la cuenta usada por el servidor, no un problema de Python ni del RPA.

La PC local puede ver la ruta con la identidad `ESSALUD\cenate.proyectosti`, pero el servidor productivo usa otra identidad: `cenate.db01@essalud.gob.pe`.

El acceso fue habilitado para `cenate.db01` y luego se valido:

- listado del share con `smbclient`;
- montaje CIFS en `/mnt/BD_CControl`;
- lectura de carpetas destino;
- escritura temporal y borrado en ambas carpetas;
- smoke productivo del RPA Medico y No Medico.

Permisos requeridos que deben conservarse: `Modify` para `ESSALUD\cenate.db01` sobre el share `BD_CControl` y sobre estas carpetas:

```text
BD_CControl\ENFE. INFEC Y TROP\TELEDENGUE NUEVO\TELEMONITOREO MEDICO
BD_CControl\ENFE. INFEC Y TROP\TELEDENGUE NUEVO\TELEMONITOREO ENFERMERIA
```

El permiso `Modify` es necesario porque el RPA reemplaza archivos del mismo periodo cuando reprocesa; no borra historicos de otros periodos.
