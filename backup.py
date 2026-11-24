#!/usr/bin/env python3
"""backup-verificado — backup con verificación de integridad y prueba de restauración.

Un backup que nunca se restauró es una hipótesis, no un backup.

Uso típico (cron semanal, silencioso):

    python3 backup.py --source ~/kb --source ~/datos --dest ~/backups --keep 8 --restore-test

Códigos de salida:
    0  backup creado, verificado y restaurado OK
    2  no se pudo crear el backup (o el zip salió corrupto)
    3  el backup se creó pero la prueba de restauración falló

Solo stdlib (Python 3.8+). Corre en Linux, macOS y Windows.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_RESTORE = 3

EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
                "cache", ".mypy_cache", ".pytest_cache", ".idea"}
EXCLUDE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}

MANIFEST = "MANIFEST.txt"
CHUNK = 1 << 20  # 1 MiB


# --------------------------------------------------------------------------
# utilidades
# --------------------------------------------------------------------------

def sha256_file(path):
    """SHA-256 de un archivo, leído por bloques (no carga todo en memoria)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def iter_files(sources):
    """Devuelve [(ruta_real, nombre_dentro_del_zip)] filtrando basura."""
    used = {}

    for src in sources:
        src = Path(src).expanduser()
        if src.is_file():
            pairs = [(src, src.name)]
        elif src.is_dir():
            pairs = []
            for p in sorted(src.rglob("*")):
                if not p.is_file():
                    continue
                rel_parts = p.relative_to(src).parts
                if any(part in EXCLUDE_DIRS for part in rel_parts[:-1]):
                    continue
                if p.name in EXCLUDE_NAMES or p.suffix.lower() in EXCLUDE_SUFFIXES:
                    continue
                pairs.append((p, "/".join((src.name,) + rel_parts)))
        else:
            continue

        for real, name in pairs:
            name = name.replace(os.sep, "/")
            if name in used:
                stem, dot, ext = name.rpartition(".")
                n = 2
                while f"{stem}-{n}{dot}{ext}" in used:
                    n += 1
                name = f"{stem}-{n}{dot}{ext}"
            used[name] = real
            yield real, name


def parse_manifest(text):
    """MANIFEST: 'sha256  tamaño  nombre' por línea (el nombre puede tener espacios)."""
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        digest, size, name = parts
        if len(digest) != 64:
            continue
        try:
            entries[name] = (digest.lower(), int(size))
        except ValueError:
            continue
    return entries


def safe_extract(zf, dest):
    """Extrae sin permitir rutas que se escapen del directorio destino (zip slip)."""
    base = Path(dest).resolve()
    for info in zf.infolist():
        target = (base / info.filename).resolve()
        if target != base and base not in target.parents:
            raise ValueError(f"ruta insegura dentro del zip: {info.filename}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, CHUNK)


# --------------------------------------------------------------------------
# verificación
# --------------------------------------------------------------------------

def restore_test(archive):
    """Extrae el backup a un temporal y compara hash y tamaño de cada archivo.

    Devuelve (ok, archivos_verificados, [problemas]).
    """
    archive = Path(archive)
    problems = []

    if not archive.is_file():
        return False, 0, [f"no existe el archivo: {archive}"]

    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            if MANIFEST not in names:
                return False, 0, ["el zip no tiene MANIFEST.txt"]
            expected = parse_manifest(zf.read(MANIFEST).decode("utf-8", "replace"))
            if not expected:
                return False, 0, ["el MANIFEST está vacío o ilegible"]

            with tempfile.TemporaryDirectory(prefix="restore-test-") as tmp:
                safe_extract(zf, tmp)
                root = Path(tmp)
                extraidos = set()

                for rel in root.rglob("*"):
                    if rel.is_file():
                        extraidos.add("/".join(rel.relative_to(root).parts))

                checked = 0
                for name, (digest, size) in expected.items():
                    target = root / name
                    if not target.is_file():
                        problems.append(f"falta en el backup: {name}")
                        continue
                    if target.stat().st_size != size:
                        problems.append(f"tamaño distinto: {name}")
                        continue
                    if sha256_file(target) != digest:
                        problems.append(f"hash distinto: {name}")
                        continue
                    checked += 1

                for sobrante in sorted(extraidos - set(expected) - {MANIFEST}):
                    problems.append(f"archivo no declarado: {sobrante}")
    except zipfile.BadZipFile:
        return False, 0, ["el zip está corrupto y no se puede abrir"]
    except Exception as exc:  # noqa: BLE001 — el restore test no debe romper el job
        return False, 0, [f"error al restaurar: {exc}"]

    return (not problems), checked, problems


# --------------------------------------------------------------------------
# backup
# --------------------------------------------------------------------------

def unique_path(dest_dir, stamp):
    candidate = dest_dir / f"backup-{stamp}.zip"
    n = 2
    while candidate.exists():
        candidate = dest_dir / f"backup-{stamp}-{n}.zip"
        n += 1
    return candidate


def create_backup(sources, dest_dir, keep, log):
    dest_dir = Path(dest_dir).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)

    archivos = list(iter_files(sources))
    if not archivos:
        print("error: no hay archivos para respaldar", file=sys.stderr)
        return EXIT_FAIL, None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = unique_path(dest_dir, stamp)
    tmp = dest.with_name(dest.name + ".part")

    manifest = [
        f"# backup-verificado",
        f"# creado: {datetime.now().isoformat(timespec='seconds')}",
        f"# origen: {', '.join(str(Path(s).expanduser()) for s in sources)}",
        f"# archivos: {len(archivos)}",
    ]

    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for real, name in archivos:
                digest = sha256_file(real)
                zf.write(real, name)
                manifest.append(f"{digest}  {real.stat().st_size:>10}  {name}")
            zf.writestr(MANIFEST, "\n".join(manifest) + "\n")
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        print(f"error: no se pudo escribir el backup: {exc}", file=sys.stderr)
        return EXIT_FAIL, None

    # Integridad del contenedor antes de pisar nada.
    try:
        with zipfile.ZipFile(tmp) as zf:
            roto = zf.testzip()
    except zipfile.BadZipFile:
        roto = "no abre"
    if roto is not None:
        tmp.unlink(missing_ok=True)
        print(f"error: el zip salió corrupto ({roto}); no se reemplazó nada", file=sys.stderr)
        return EXIT_FAIL, None

    os.replace(tmp, dest)  # atómico

    digest_zip = sha256_file(dest)
    sidecar = dest.with_name(dest.name + ".sha256")
    sidecar.write_text(f"{digest_zip}  {dest.name}\n", encoding="utf-8")

    # Retención por fecha de modificación, conservando las 'keep' más nuevas.
    copias = sorted(dest_dir.glob("backup-*.zip"), key=lambda p: (p.stat().st_mtime, p.name))
    borradas = []
    for viejo in copias[:-keep] if keep > 0 else []:
        viejo.unlink(missing_ok=True)
        viejo.with_name(viejo.name + ".sha256").unlink(missing_ok=True)
        borradas.append(viejo.name)

    size_raw = sum(real.stat().st_size for real, _ in archivos)
    log.update({
        "archive": str(dest),
        "files": len(archivos),
        "bytes_raw": size_raw,
        "bytes_zip": dest.stat().st_size,
        "sha256": digest_zip,
        "pruned": borradas,
    })
    return EXIT_OK, dest


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="backup.py",
        description="Backup con verificación de integridad y prueba de restauración.",
    )
    p.add_argument("--source", action="append", metavar="RUTA",
                   help="archivo o carpeta a respaldar (repetible)")
    p.add_argument("--dest", metavar="DIR", help="carpeta destino de los backups")
    p.add_argument("--keep", type=int, default=8, metavar="N",
                   help="cuántas copias conservar (default 8; 0 = no borrar nada)")
    p.add_argument("--restore-test", action="store_true",
                   help="después de crear, restaurar a un temporal y comparar hashes")
    p.add_argument("--check", metavar="ARCHIVO",
                   help="solo verificar un backup existente (no crea nada)")
    p.add_argument("--json", action="store_true", help="salida JSON (una línea)")
    p.add_argument("-v", "--verbose", action="store_true", help="resumen por stdout")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    started = time.time()
    log = {"ok": False, "started": datetime.now().isoformat(timespec="seconds")}

    # Modo verificación de un backup existente.
    if args.check:
        ok, checked, problems = restore_test(args.check)
        log.update({"ok": ok, "mode": "check", "archive": args.check,
                    "checked": checked, "problems": problems})
        log["duration_s"] = round(time.time() - started, 3)
        if args.json:
            print(json.dumps(log, ensure_ascii=False))
        elif ok:
            print(f"ok: {args.check} restaura correctamente ({checked} archivos)")
        else:
            print(f"FALLA: {args.check}", file=sys.stderr)
            for p in problems[:20]:
                print("  - " + p, file=sys.stderr)
        return EXIT_OK if ok else EXIT_RESTORE

    if not args.source or not args.dest:
        print("error: --source y --dest son obligatorios (o usá --check ARCHIVO)",
              file=sys.stderr)
        return EXIT_FAIL

    faltantes = [s for s in args.source if not Path(s).expanduser().exists()]
    if faltantes:
        for f in faltantes:
            print(f"aviso: no existe la ruta de origen: {f}", file=sys.stderr)
        if len(faltantes) == len(args.source):
            print("error: ninguna ruta de origen existe", file=sys.stderr)
            return EXIT_FAIL

    code, archive = create_backup(args.source, args.dest, args.keep, log)
    if code != EXIT_OK:
        log["duration_s"] = round(time.time() - started, 3)
        if args.json:
            print(json.dumps(log, ensure_ascii=False))
        return code

    if args.restore_test:
        ok, checked, problems = restore_test(archive)
        log["restore_test"] = {"ok": ok, "checked": checked, "problems": problems}
        if not ok:
            log["duration_s"] = round(time.time() - started, 3)
            if args.json:
                print(json.dumps(log, ensure_ascii=False))
            else:
                print(f"FALLA la restauración de {archive}", file=sys.stderr)
                for p in problems[:20]:
                    print("  - " + p, file=sys.stderr)
            return EXIT_RESTORE
        code = EXIT_OK

    log["ok"] = True
    log["duration_s"] = round(time.time() - started, 3)

    if args.json:
        print(json.dumps(log, ensure_ascii=False))
    elif args.verbose:
        print(f"ok: {archive}")
        print(f"  archivos: {log['files']} | origen {log['bytes_raw']/1024:.0f} KB "
              f"-> zip {log['bytes_zip']/1024:.0f} KB | {log['duration_s']} s")
        if "restore_test" in log:
            print(f"  restore test: {log['restore_test']['checked']} archivos, 0 diferencias")
        if log["pruned"]:
            print(f"  rotación: {len(log['pruned'])} copia(s) vieja(s) borrada(s)")

    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # el cron avisa solo si algo falla
        print(f"error inesperado: {exc}", file=sys.stderr)
        sys.exit(EXIT_FAIL)
