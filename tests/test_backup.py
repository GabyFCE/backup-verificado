#!/usr/bin/env python3
"""Tests de backup.py — se ejecutan contra el CLI real, no contra funciones internas.

    python3 -m unittest discover -s tests -v
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "backup.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True)


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bv-test-"))
        self.src = self.tmp / "origen"
        self.dest = self.tmp / "backups"
        (self.src / "sub").mkdir(parents=True)
        (self.src / "a.txt").write_text("contenido A\n", encoding="utf-8")
        (self.src / "sub" / "b.bin").write_bytes(bytes(range(200)))
        (self.src / "con espacios.txt").write_text("x\n", encoding="utf-8")
        (self.src / "__pycache__").mkdir()
        (self.src / "__pycache__" / "basura.pyc").write_bytes(b"\x00\x01")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def backup(self, *extra):
        return run("--source", str(self.src), "--dest", str(self.dest), *extra)

    # ------------------------------------------------------------------

    def test_crea_zip_manifiesto_y_sha256(self):
        r = self.backup()
        self.assertEqual(r.returncode, 0, r.stderr)

        zips = list(self.dest.glob("backup-*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertTrue(Path(str(zips[0]) + ".sha256").is_file())

        with zipfile.ZipFile(zips[0]) as zf:
            names = zf.namelist()
            manifest = zf.read("MANIFEST.txt").decode()

        self.assertIn("origen/a.txt", names)
        self.assertIn("origen/sub/b.bin", names)
        self.assertIn("origen/con espacios.txt", names)
        self.assertNotIn("origen/__pycache__/basura.pyc", names)
        self.assertEqual(manifest.count("  origen/"), 3)

    def test_restore_test_ok(self):
        r = self.backup("--restore-test", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertTrue(data["ok"])
        self.assertTrue(data["restore_test"]["ok"])
        self.assertEqual(data["restore_test"]["checked"], 3)
        self.assertEqual(data["restore_test"]["problems"], [])

    def test_check_detecta_manipulacion_de_contenido(self):
        self.assertEqual(self.backup().returncode, 0)
        archive = next(self.dest.glob("backup-*.zip"))

        # Reescribo el zip cambiando un byte, sin tocar el tamaño ni el manifiesto.
        with zipfile.ZipFile(archive) as zf:
            items = [(i, zf.read(i.filename)) for i in zf.infolist()]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for info, data in items:
                if info.filename.endswith("a.txt"):
                    data = b"contenido B\n"          # mismo largo, distinto hash
                zf.writestr(info.filename, data)

        r = run("--check", str(archive), "--json")
        self.assertEqual(r.returncode, 3, r.stderr)
        data = json.loads(r.stdout)
        self.assertFalse(data["ok"])
        self.assertTrue(any("hash distinto" in p for p in data["problems"]))

    def test_check_detecta_falta_de_archivo(self):
        self.assertEqual(self.backup().returncode, 0)
        archive = next(self.dest.glob("backup-*.zip"))

        with zipfile.ZipFile(archive) as zf:
            items = [(i, zf.read(i.filename)) for i in zf.infolist()]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for info, data in items:
                if info.filename.endswith("b.bin"):
                    continue
                zf.writestr(info.filename, data)

        r = run("--check", str(archive))
        self.assertEqual(r.returncode, 3)
        self.assertIn("falta en el backup", r.stderr)

    def test_zip_corrupto(self):
        self.assertEqual(self.backup().returncode, 0)
        archive = next(self.dest.glob("backup-*.zip"))
        raw = bytearray(archive.read_bytes())
        raw[100:140] = b"\xff" * 40            # rompo la estructura interna
        archive.write_bytes(bytes(raw))

        r = run("--check", str(archive))
        self.assertEqual(r.returncode, 3)
        self.assertIn("FALLA", r.stderr)

    def test_rotacion_conserva_las_ultimas(self):
        for _ in range(5):
            self.assertEqual(self.backup("--keep", "2").returncode, 0)
        zips = list(self.dest.glob("backup-*.zip"))
        self.assertEqual(len(zips), 2)
        for z in zips:
            self.assertTrue(Path(str(z) + ".sha256").is_file())

    def test_fuente_inexistente(self):
        r = run("--source", str(self.tmp / "no-existe"), "--dest", str(self.dest))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ninguna ruta de origen existe", r.stderr)

    def test_sin_argumentos(self):
        r = run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("--source y --dest son obligatorios", r.stderr)

    def test_silencio_en_exito(self):
        r = self.backup()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(r.stderr.strip(), "")

    def test_verbose_muestra_resumen(self):
        r = self.backup("-v")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("restore", r.stdout, "sin --restore-test no debe hablar de restore")
        self.assertIn("ok:", r.stdout)


if __name__ == "__main__":
    unittest.main()
