# backup-verificado

Backup con verificación de integridad y **prueba de restauración automática**.
Un backup que nunca se restauró es una hipótesis, no un backup.

Python 3.8+, solo biblioteca estándar. Linux, macOS y Windows.

## El problema

Tenía un backup semanal que se generaba solo y nunca se probaba. El día que hace
falta es el peor día para descubrir que el zip está truncado, que faltó una
carpeta o que el archivo adentro no es el que era.

El chequeo habitual —abrir el zip y ver que no esté corrupto— no alcanza: valida
el CRC del contenedor, no que el contenido coincida con el original. Un zip puede
abrir perfecto y tener adentro datos que no son los que se respaldaron.

## Qué hace

1. Comprime las rutas indicadas en `destino/backup-AAAAMMDD-HHMMSS.zip`.
2. Calcula el SHA-256 de **cada archivo** y lo guarda en un `MANIFEST.txt` dentro
   del zip.
3. Verifica el contenedor con `testzip()` antes de publicarlo.
4. Publica de forma atómica (`os.replace`): nunca queda un zip a medio escribir
   con nombre definitivo.
5. Guarda el `sha256` del zip en un archivo `.sha256` al lado.
6. **Restaura a un directorio temporal y compara hash y tamaño de cada archivo**
   (`--restore-test`).
7. Rota: conserva las últimas N copias y borra las viejas con su `.sha256`.
8. Es silencioso si todo sale bien (patrón watchdog para cron).

## Uso

```bash
# backup semanal, verificado
python3 backup.py --source ~/kb --source ~/datos --dest ~/backups --keep 8 --restore-test

# verificar un backup viejo sin crear nada
python3 backup.py --check ~/backups/backup-20261123-211517.zip

# salida para monitoreo
python3 backup.py --source ~/kb --dest ~/backups --restore-test --json
```

Cron (domingo 15:10, avisa solo si falla):

```cron
10 15 * * 0 python3 /home/usuario/bin/backup.py --source /home/usuario/kb \
  --dest /home/usuario/backups --keep 8 --restore-test >/tmp/backup.log 2>&1 || \
  cat /tmp/backup.log
```

## Tres niveles de verificación

| Nivel | Qué comprueba | Cómo |
|---|---|---|
| Contenedor | El zip no está corrupto | `testzip()` antes de publicar |
| Contenido | Cada archivo coincide con su hash | SHA-256 por archivo en `MANIFEST.txt` |
| Restauración | Lo guardado se puede recuperar igual | `--restore-test`: extrae y recompara hash y tamaño |

El tercero es el que importa. Los dos primeros los tiene cualquier script; el
tercero es el que convierte "tengo backups" en "sé que mis backups restauran".

## Códigos de salida

| Código | Significado | Qué hace el cron |
|---|---|---|
| 0 | Backup creado, verificado y restaurado | Nada |
| 2 | No se pudo crear, o el zip salió corrupto | Avisa |
| 3 | Se creó, pero no restaura fielmente | Avisa con prioridad |

Distinguir 2 de 3 no es capricho: "no copió" y "copió mal" se investigan distinto.

## Prueba de fuego

Un zip que abre bien y no restaura fielmente, detectado por el script:

```
$ python3 backup.py --check manipulado.zip
FALLA: manipulado.zip
  - hash distinto: kb/README.md
  - hash distinto: CONTEXTO.md
  - hash distinto: NOTAS.md
  ...
exit 3
```

El zip se reescribió cambiando un byte por archivo, sin tocar tamaños ni el
manifiesto. `testzip()` lo da por bueno; el restore test no.

## Resultado medido

- 23 archivos, 297 KB sin comprimir → 101 KB de zip, **0,10 s**.
- Restore test: 23 archivos extraídos, 0 diferencias de hash.
- Prueba de manipulación: 19 archivos alterados detectados, salida 3.

## Decisiones de diseño

- **Extraer y comparar, no solo `testzip()`**: el CRC no dice nada sobre la
  fidelidad del contenido.
- **Manifiesto adentro del zip**: el backup se explica a sí mismo; no depende de
  un archivo externo que se puede perder.
- **Escritura atómica**: un corte de luz a mitad de la copia no destruye la
  última copia buena.
- **Restore test sobre el backup recién creado, no sobre el origen**: prueba el
  artefacto que realmente se va a guardar.
- **Silencio en éxito**: un cron que manda mail todas las semanas se ignora en dos
  meses. Solo habla cuando hay algo que hacer.
- **Cero dependencias**: un archivo, stdlib, corre en cualquier lado. Un backup
  que necesita `pip install` es un backup que un día no corre.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Diez tests contra el CLI real: creación, manifiesto, filtros de basura, restore OK,
manipulación de contenido, archivo faltante, zip corrupto, rotación, fuente
inexistente, silencio en éxito.

## Límites (honestos)

- No es incremental ni deduplica: cada corrida es un zip completo. Sirve para
  decenas o cientos de MB, no para 100 GB.
- No cifra ni sube a la nube: es la pata local. Para offsite, copiar el `.zip` y
  el `.sha256` a otro disco o bucket, y verificar el hash allá.
- No reemplaza un backup del sistema operativo ni de la base en caliente: para
  SQLite u otras bases, conviene un dump consistente antes.

## Qué mejoraría

- Envío a almacenamiento externo (S3/Backblaze) reutilizando el mismo `.sha256`.
- Cifrado con `age` o `gpg` antes de publicar.
- Backup incremental por bloques para volúmenes grandes.

## Licencia

MIT.
