import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from writer import _create_file, _relative, ArtifactWriter


class WriterTests(unittest.TestCase):
    def test_rejects_ambiguous_and_escaping_paths(self):
        for path in ["", "/tmp/out", "../out", "a/../out", "a//out", "./out", "a\\out", "a/", "a\0b"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                _relative(path)

    def test_exclusive_utf8_write_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            args = {"workspace": directory, "path": "note.txt", "content": "Fictional café\n"}
            result = _create_file(args)
            self.assertEqual(result["bytes"], len(args["content"].encode()))
            with self.assertRaises(FileExistsError):
                _create_file({**args, "content": "replacement"})
            self.assertEqual((Path(directory) / "note.txt").read_text(), args["content"])
            self.assertEqual((Path(directory) / "note.txt").stat().st_mode & 0o777, 0o600)

    def test_refuses_symlink_parent_and_destination(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / "link").symlink_to(outside, target_is_directory=True)
            (root / "file").symlink_to(Path(outside) / "target")
            for path in ["link/out.txt", "file"]:
                with self.subTest(path=path), self.assertRaises(OSError):
                    _create_file({"workspace": directory, "path": path, "content": "fiction"})
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_invalid_settings_and_arguments_never_write(self):
        writer = ArtifactWriter(lambda key, default=None: default)
        self.assertFalse(json.loads(writer.prepare({"path": "x", "content": "fiction"}))["prepared"])
        self.assertFalse(json.loads(writer.commit({"request_id": "../bad"}))["admitted"])
        self.assertFalse(json.loads(writer.prepare({"path": "x", "content": "fiction", "run_id": "chosen"}))["prepared"])


if __name__ == "__main__":
    unittest.main()
