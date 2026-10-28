"""Installer filesystem behavior; no network, real keys or paid requests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).parents[1] / "installer.py"


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="portable 中文 空格 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "package"
        self.skill = self.package / "skill"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text("new skill", encoding="utf-8")
        (self.skill / "scripts").mkdir()
        (self.skill / "scripts/apinebula_image.py").write_text("# script", encoding="utf-8")
        runtime = self.package / "runtime/macos-arm64/bin"
        runtime.mkdir(parents=True)
        (runtime / "python3").write_text("runtime", encoding="utf-8")
        (runtime.parent / "included-license.txt").write_text("license", encoding="utf-8")
        self.target = self.root / "user/.agents/skills/apinebula-imagegen"
        spec = importlib.util.spec_from_file_location("portable_installer", SOURCE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def install(self):
        return self.m.install_package(self.package, self.target, "Darwin", "arm64")

    def test_native_runtime_selection_and_unsupported_platform(self):
        self.assertEqual(self.m.runtime_name("Darwin", "arm64"), "macos-arm64")
        self.assertEqual(self.m.runtime_name("Darwin", "x86_64"), "macos-x64")
        self.assertEqual(self.m.runtime_name("Windows", "AMD64"), "windows-x64")
        with self.assertRaises(self.m.InstallError):
            self.m.runtime_name("Windows", "ARM64")

    def test_fresh_install_copies_selected_runtime_and_works_in_unicode_path(self):
        with patch.object(self.m, "validate_runtime"):
            result = self.install()
        self.assertEqual(result["target"], str(self.target))
        self.assertEqual((self.target / "SKILL.md").read_text(), "new skill")
        self.assertTrue((self.target / "runtime/bin/python3").exists())
        self.assertTrue((self.target / "runtime/included-license.txt").exists())
        if self.m.os.name != "nt":
            self.assertTrue((self.target / "run.command").stat().st_mode & 0o111)
        self.assertTrue((self.target / "portable-install.json").exists())

    def test_upgrade_backs_up_previous_skill_and_keeps_external_key(self):
        self.target.mkdir(parents=True)
        (self.target / "custom.txt").write_text("old customization")
        key = self.root / "user/.config/codex-imagegen/apinebula-api-key"
        key.parent.mkdir(parents=True)
        key.write_text("user-secret-never-copy")
        with patch.object(self.m, "validate_runtime"):
            result = self.install()
        backup = Path(result["backup"])
        self.assertEqual((backup / "custom.txt").read_text(), "old customization")
        self.assertNotEqual(backup.parent, self.target.parent)
        self.assertNotIn(self.target.parent, backup.parents)
        self.assertFalse((self.target / "custom.txt").exists())
        self.assertEqual(key.read_text(), "user-secret-never-copy")
        self.assertNotIn("user-secret-never-copy", json.dumps(result))

    def test_failed_validation_leaves_existing_install_untouched(self):
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("original")
        with patch.object(self.m, "validate_runtime", side_effect=self.m.InstallError("unusable runtime")):
            with self.assertRaises(self.m.InstallError):
                self.install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "original")
        self.assertEqual(list(self.target.parent.glob("*.backup-*")), [])

    def test_repeated_install_creates_distinct_recoverable_backups(self):
        with patch.object(self.m, "validate_runtime"):
            self.install()
            a = self.install()
            b = self.install()
        self.assertNotEqual(a["backup"], b["backup"])
        self.assertTrue(Path(a["backup"]).exists())
        self.assertTrue(Path(b["backup"]).exists())

    def test_commit_failure_restores_previous_install(self):
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("original")
        original_rename = Path.rename
        def rename(path, destination):
            if path.name.startswith(".apinebula-install-"):
                raise OSError("simulated commit failure")
            return original_rename(path, destination)
        with patch.object(self.m, "validate_runtime"), patch.object(Path, "rename", rename):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual((self.target / "SKILL.md").read_text(), "original")
        self.assertEqual(list(self.target.parent.glob(".apinebula-install-*")), [])

    def test_missing_platform_runtime_does_not_touch_existing_install(self):
        self.target.mkdir(parents=True)
        (self.target / "SKILL.md").write_text("original")
        with self.assertRaises(self.m.InstallError):
            self.m.install_package(self.package, self.target, "Windows", "AMD64")
        self.assertEqual((self.target / "SKILL.md").read_text(), "original")

    def test_destination_symlink_is_not_replaced(self):
        other = self.root / "unrelated"
        other.mkdir()
        self.target.parent.mkdir(parents=True)
        try:
            self.target.symlink_to(other, target_is_directory=True)
        except OSError as exc:
            if __import__("os").name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("This Windows account cannot create symlinks without Developer Mode")
            raise
        with self.assertRaises(self.m.InstallError):
            self.install()
        self.assertTrue(self.target.is_symlink())


if __name__ == "__main__":
    unittest.main()
