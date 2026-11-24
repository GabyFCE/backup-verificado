# Runbook — backup-verificado

Qué hacer según el código de salida y el síntoma. Ordenado por lo que aparece en
la práctica.

## Salida 0 y silencio

Es lo normal. No hay nada que hacer. El resumen está con `-v`.

## Salida 2 — no se pudo crear el backup

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `no hay archivos para respaldar` | Ruta mal escrita, o el filtro excluyó todo | Revisar `--source`; correr con `-v` |
| `ninguna ruta de origen existe` | Disco no montado, carpeta movida | Montar/verificar la ruta y volver a correr |
| `no se pudo escribir el backup` | Disco lleno, permisos | `df -h` sobre el destino; revisar dueño y modo |
| `el zip salió corrupto` | Fallo de disco o de memoria | Revisar `dmesg`; si se repite, cambiar el destino |

El backup anterior **no se toca** en ninguno de estos casos: se escribe a un
`.part` y se publica con `os.replace` recién al final.

## Salida 3 — se creó pero no restaura

Es la más importante y la que casi nunca se ve.

1. Correr `python3 backup.py --check <archivo> -v` para ver la lista completa.
2. `hash distinto` en varios archivos: el artefacto se corrompió después de
   crearse (copia a otro disco, sincronización, antivirus). Rehacer el backup y
   verificar el `.sha256` en destino.
3. `falta en el backup` con el zip recién creado: algún archivo se movió o se
   borró durante la corrida. Rehacer con la fuente quieta.
4. `archivo no declarado`: alguien agregó contenido al zip fuera del script. No
   confiar en ese archivo.
5. Si falla siempre en el mismo archivo: revisar permisos de lectura y que no sea
   un archivo que cambia constantemente (log, base en caliente).

## Restaurar a mano

```bash
sha256sum -c backup-AAAAMMDD-HHMMSS.zip.sha256     # integridad del zip
unzip -l backup-AAAAMMDD-HHMMSS.zip                 # contenido y MANIFEST
mkdir /tmp/restore && unzip backup-AAAAMMDD-HHMMSS.zip -d /tmp/restore
cd /tmp/restore && awk '!/^#/ {h=$1; $1=""; $2=""; sub(/^ +/,""); print h"  "$0}' MANIFEST.txt | sha256sum -c -
```

La última línea compara todo el contenido restaurado contra el manifiesto sin
pasar por el script: sirve para auditar el script mismo.

## Rotación

`--keep N` conserva las N copias más nuevas por fecha de modificación. `--keep 0`
no borra nada. Si el disco se llena, bajar `--keep` antes que tocar los archivos a
mano.

## Cuando el backup pasa a otro disco

1. Copiar el `.zip` **y** el `.sha256`.
2. En destino: `sha256sum -c archivo.zip.sha256`.
3. Correr `--check` sobre el archivo copiado: verifica contenido, no solo el hash
   del contenedor.
