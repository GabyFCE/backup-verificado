# backup-verificado

Copia archivos y carpetas a un zip, guarda el hash SHA-256 de cada archivo y
verifica el resultado restaurándolo.

Python 3.8 o superior. Solo biblioteca estándar. Linux, macOS y Windows.

## Uso

```bash
# crear backup y verificar la restauración
python3 backup.py --source ~/kb --source ~/datos --dest ~/backups --keep 8 --restore-test

# verificar un backup existente sin crear nada
python3 backup.py --check ~/backups/backup-20261123-211517.zip

# salida JSON para monitoreo
python3 backup.py --source ~/kb --dest ~/backups --restore-test --json
```

| Opción | Descripción |
|---|---|
| `--source RUTA` | Archivo o carpeta a respaldar. Se puede repetir. |
| `--dest DIR` | Carpeta donde se escriben los backups. |
| `--keep N` | Copias a conservar. Por defecto 8. `0` no borra nada. |
| `--restore-test` | Después de crear el backup, lo extrae a un directorio temporal y compara hash y tamaño de cada archivo. |
| `--check ARCHIVO` | Verifica un backup existente. No crea nada. |
| `--json` | Escribe el resultado como JSON en una línea. |
| `-v`, `--verbose` | Imprime el resumen de la corrida. |

## Qué hace

1. Recorre las rutas de `--source` y descarta `__pycache__`, `.git`, `.venv`,
   `node_modules`, `cache`, archivos `.pyc`, `.tmp` y metadatos del sistema.
2. Escribe el zip en un archivo `.part` dentro del destino.
3. Calcula el SHA-256 de cada archivo y lo agrega a `MANIFEST.txt` dentro del zip.
4. Verifica el zip cerrado con `testzip()`.
5. Renombra el `.part` al nombre definitivo con `os.replace`.
6. Escribe el SHA-256 del zip en un archivo `.sha256`.
7. Borra las copias más viejas que `--keep`.
8. No imprime nada si la corrida sale bien, salvo con `-v` o `--json`.

## Formato

```
backup-AAAAMMDD-HHMMSS.zip
├── MANIFEST.txt          # sha256, tamaño y ruta de cada archivo
└── <origen>/...          # archivos respaldados
backup-AAAAMMDD-HHMMSS.zip.sha256
```

Cada línea del manifiesto tiene el formato `sha256  tamaño  ruta`. La ruta puede
contener espacios.

## Verificación

| Nivel | Qué comprueba | Cuándo |
|---|---|---|
| Contenedor | Que el zip no esté corrupto | `testzip()` antes de publicar el archivo |
| Contenido | Que el hash de cada archivo coincida con el manifiesto | `--restore-test` o `--check` |
| Restauración | Que los archivos se extraigan con el tamaño y el hash originales | `--restore-test` o `--check` |

`testzip()` valida la estructura del zip, no el contenido. Un zip puede abrir sin
errores y tener adentro datos distintos de los respaldados; la comparación de
hashes cubre ese caso.

## Códigos de salida

| Código | Significado |
|---|---|
| 0 | Backup creado y verificado. |
| 2 | No se pudo crear el backup, o el zip salió corrupto. La copia anterior no se modifica. |
| 3 | El backup se creó, pero falló la verificación de contenido o de restauración. |

## Cron

```cron
10 15 * * 0 python3 /home/usuario/bin/backup.py --source /home/usuario/kb \
  --dest /home/usuario/backups --keep 8 --restore-test >/tmp/backup.log 2>&1 || \
  cat /tmp/backup.log
```

## Ejemplo: contenido alterado

Se reescribió un backup cambiando un byte por archivo, sin modificar tamaños ni
manifiesto. `testzip()` lo acepta y `--check` no:

```
$ python3 backup.py --check manipulado.zip
FALLA: manipulado.zip
  - hash distinto: kb/README.md
  - hash distinto: CONTEXTO.md
  - hash distinto: NOTAS.md
  ...
exit 3
```

## Medición

Corrida sobre 23 archivos: 297 KB sin comprimir, 101 KB de zip, 0,10 s. La
verificación restauró los 23 archivos sin diferencias. La prueba de manipulación
detectó 19 archivos alterados y devolvió 3.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Diez tests que ejecutan el CLI: creación del zip, manifiesto, filtros de
exclusión, restauración correcta, contenido alterado, archivo faltante, zip
corrupto, rotación, ruta de origen inexistente y salida silenciosa.

## Estructura

```
backup.py              # CLI
tests/test_backup.py   # tests
docs/RUNBOOK.md        # diagnóstico por código de salida y restauración manual
.github/workflows/tests.yml
```

## Límites

- Cada corrida genera un zip completo: no es incremental ni deduplica.
- No cifra ni copia a otro equipo. Para una copia externa hay que mover el `.zip`
  y su `.sha256`, y verificar el hash en destino.
- No hace dumps de bases de datos en caliente. Para SQLite u otras bases conviene
  un dump consistente antes de la corrida.
- Pensado para volúmenes de hasta cientos de MB.

## Licencia

MIT.
