# Contexto para IA - RPA Prog Prof

Leer este archivo antes de modificar `rpa-prog-prof`.

## Objetivo

Descargar la programacion de profesionales desde ExplotaDatos para los centros/IPRESS marcados en la pestaña `CENACRON`.

## Formulario

URL:

```text
http://appsgasistexpl.essalud.gob.pe/explotaDatos/servlet/CtrlControl?opt=adm19
```

Selecciones:

- `area=00`
- `servicio=00`
- fecha inicio = primer dia del mes
- fecha fin = ultimo dia del mes
- `formatoArchivo=xls`

## Publicacion

Ruta final:

```text
//10.0.88.100/bbdd_rpa/Bases_Prog_Prof
```

Archivos esperados:

```text
COD_YYYYMMDD_YYYYMMDD_ConsProgPro.txt
```

## Reglas

- No pertenece al orquestador de madrugada.
- Se ejecuta antes de `rpa-mensual-cronicos` dentro de `orquestador-cronicos`.
- Usa usuarios maestros por macroregion desde `shared/config/.env_usuarios`.
- Mantiene staging temporal, limpieza de perfiles Chrome y publicacion atomica.
