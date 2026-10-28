import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('build_packages', Path(__file__).parents[1] / 'build_packages.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PortableBuildTests(unittest.TestCase):
    def test_paths_are_repository_relative(self):
        self.assertEqual(m.SKILL_SOURCE, Path(__file__).resolve().parents[2] / 'apinebula-imagegen')
        self.assertEqual(m.ROOT, Path(__file__).resolve().parents[2])

    def test_platform_guard_does_not_build_windows_on_mac(self):
        with self.assertRaises(ValueError):
            m.check_build_host('windows', 'Darwin')
        m.check_build_host('windows', 'Windows')
        m.check_build_host('macos', 'Darwin')

    def test_packaged_skill_has_runtime_entrypoints_and_all_references(self):
        with tempfile.TemporaryDirectory(prefix='打包 测试 ') as tmp:
            target = Path(tmp) / 'skill'
            m.packaged_skill(target)
            text = (target / 'SKILL.md').read_text(encoding='utf-8')
            self.assertIn('run.command', text)
            self.assertIn('run.cmd', text)
            self.assertTrue((target / 'references/setup.md').exists())
            self.assertTrue((target / 'requirements.lock').exists())

    def test_archive_rejects_local_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'package';root.mkdir()
            (root / 'apinebula-api-key').write_text('dummy-secret')
            with self.assertRaises(ValueError):
                m.validate_distribution(root)

    def test_public_runtime_ca_bundle_is_allowed_but_private_key_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / 'runtime/macos-arm64/lib/python3.13/site-packages/certifi/cacert.pem'
            bundle.parent.mkdir(parents=True)
            bundle.write_text('public CA certificate fixture')
            m.validate_distribution(root)
            sdk_bundle = root / 'runtime/macos-arm64/lib/python3.13/site-packages/botocore/cacert.pem'
            sdk_bundle.parent.mkdir(parents=True)
            sdk_bundle.write_text('public S3 SDK CA certificate fixture')
            m.validate_distribution(root)
            (root / 'personal.pem').write_text('private fixture')
            with self.assertRaises(ValueError):
                m.validate_distribution(root)

    def test_platform_hash_locks_match_source_dependency_versions(self):
        def normalized(path):
            return {line.split()[0].lower().replace('_', '-') for line in path.read_text().splitlines()
                    if line.strip() and not line.startswith('#')}
        source_versions = normalized(m.SKILL_SOURCE / 'requirements.lock')
        for target in ('macos-arm64', 'macos-x64', 'windows-x64'):
            path = m.ROOT / 'packaging/locks' / (target + '.txt')
            self.assertEqual(normalized(path), source_versions)
            for line in path.read_text().splitlines():
                if line.strip() and not line.startswith('#'):
                    self.assertRegex(line, r'--hash=sha256:[a-f0-9]{64}$')

    def test_windows_guide_describes_windows_and_never_claims_mac_only(self):
        guide = m.guide('Windows')
        self.assertIn('Windows 10/11 x64', guide)
        self.assertIn('Install.cmd', guide)
        self.assertNotIn('当前电脑没有 Rosetta', guide)


if __name__ == '__main__':
    unittest.main()
