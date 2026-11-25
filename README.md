# backup-verificado

Herramienta de línea de comandos para administradores de sistemas y desarrolladores que genera copias de seguridad en formato ZIP y verifica su integridad mediante hashes SHA-256 y pruebas de restauración.

## Qué es y para qué sirve

Un respaldo es útil solo cuando se garantiza que el archivo existe y que su contenido coincide exactamente con el original. La verificación estructural estándar de un archivo ZIP comprueba que el contenedor pueda abrirse, pero no detecta si los datos internos sufrieron alteraciones silenciosas respecto a la fuente.

`backup-verificado` empaqueta directorios y archivos excluyendo artefactos temporales (`__pycache__`, `.git`, `.venv`, `node_modules`, `cache`, `.pyc`, `.tmp` y metadatos del sistema). Durante el proceso, calcula el hash SHA-256 y el tamaño de cada archivo para registrarlos en un manifiesto interno (`MANIFEST.txt`), y genera un archivo `.sha256` externo para el contenedor. Permite extraer el respaldo en un directorio temporal para recalcular y comparar los hashes contra el manifiesto, devolviendo códigos de salida específicos para sistemas de monitoreo.

## Qué incluye

### Opciones de línea de comandos

| Opción | Descripción |
|---|---|
| `--source RUTA` | Archivo o carpeta a respaldar. Se puede repetir para múltiples orígenes. |
| `--dest DIR` | Carpeta donde se escriben los archivos de respaldo y sus hashes. |
| `--keep N` | Cantidad de copias a conservar en la rotación (por defecto `8`, `0` no borra nada). |
| `--restore-test` | Extrae el respaldo creado a un directorio temporal y verifica hash y tamaño de cada archivo. |
| `--check ARCHIVO` | Verifica la estructura y el contenido de un archivo ZIP existente sin crear uno nuevo. |
| `--json` | Imprime el resultado de la operación en una línea con formato JSON. |
| `-v`, `--verbose` | Imprime el resumen de la ejecución por salida estándar. |

### Niveles de verificación

| Nivel | Qué comprueba | Mecanismo |
|---|---|---|
| Contenedor | Ausencia de corrupción en la estructura del ZIP | `testzip()` antes de renombrar el archivo temporal |
| Contenido | Coincidencia del hash de cada archivo con `MANIFEST.txt` | `--restore-test` al crear o `--check` sobre un ZIP |
| Restauración | Extracción real con tamaño y hash idénticos al origen | `--restore-test` al crear o `--check` sobre un ZIP |

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | Respaldo creado y verificado sin errores. |
| `2` | Error al crear el respaldo o contenedor ZIP corrupto. Las copias anteriores no se modifican. |
| `3` | Respaldo creado, pero con fallos en la verificación de contenido o durante la restauración. |

## Decisiones técnicas

- **Solo biblioteca estándar de Python (3.8+):** Se descartó el uso de paquetes externos de compresión o CLI para evitar la gestión de entornos virtuales y dependencias en servidores de destino, permitiendo la ejecución directa en Linux, macOS y Windows.
- **Verificación por manifiesto SHA-256 en lugar de solo `testzip()`:** Se descartó confiar únicamente en la validación CRC del contenedor ZIP porque no detecta discrepancias lógicas entre el dato original y el almacenado si el contenedor es estructuralmente válido.
- **Escritura atómica mediante archivo `.part` y `os.replace`:** Se descartó escribir directamente sobre el nombre final del archivo ZIP para evitar que interrupciones o fallos de disco dejen respaldos incompletos que entren en la rotación y reemplacen copias válidas anteriores.
- **Respaldos completos por corrida en lugar de incrementales:** Se descartaron la deduplicación y las cadenas incrementales para eliminar la dependencia entre archivos; cada archivo `.zip` junto a su `.sha256` es autónomo y restaurable por sí mismo en volúmenes de hasta cientos de megabytes.
- **Salida silenciosa por defecto:** Se descartó imprimir progreso en ejecuciones exitosas sin banderas para evitar el envío de notificaciones innecesarias cuando la herramienta se ejecuta de forma desatendida, emitiendo salida solo ante errores o cuando se solicitan `-v` o `--json`.

## Estructura

```text
LICENSE                # Licencia MIT del proyecto
backup.py              # Script principal de respaldo, rotación y verificación
docs/RUNBOOK.md        # Guía de diagnóstico por código de salida y restauración manual
tests/test_backup.py   # Batería de 10 pruebas automatizadas sobre la interfaz de comandos
```

## Cómo se usa

El proyecto requiere Python 3.8 o superior y no necesita instalación de dependencias externas.

Crear un respaldo de múltiples orígenes, conservar las últimas 8 copias y verificar la restauración:

```bash
python3 backup.py --source ./datos/documentos --source ./datos/proyectos --dest ./respaldos --keep 8 --restore-test
```

Crear un respaldo emitiendo salida en formato JSON para sistemas de monitoreo:

```bash
python3 backup.py --source ./datos/documentos --dest ./respaldos --restore-test --json
```

Verificar la integridad de un respaldo existente sin generar archivos nuevos:

```bash
python3 backup.py --check ./respaldos/backup-20261123-211517.zip
```

Ejecutar la suite de pruebas automatizadas (verifica creación, manifiesto, exclusiones, restauración, detección de contenido alterado, archivos faltantes, corrupción de ZIP, rotación, rutas inexistentes y modo silencioso):

```bash
python3 -m unittest discover -s tests -v
```

## Licencia

Distribuido bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.
