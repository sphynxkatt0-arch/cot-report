"""Ensure a shell rebuild cannot restore the obsolete bootstrap alias."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shell_installer', ROOT / 'install_cot_intelligence_shell.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeShellTest(unittest.TestCase):
    def test_rebuild_replaces_stale_bootstrap_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / 'dashboard.html'
            source = (ROOT / 'worldclass_dashboard.html').read_text(encoding='utf-8')
            source = source.replace('worldclass/bootstrap.js', 'worldclass/bootstrap.78b7dd7edb1c.js')
            html.write_text(source, encoding='utf-8')
            with patch.object(installer, 'HTML', html), contextlib.redirect_stdout(io.StringIO()):
                installer.main()
                result = html.read_text(encoding='utf-8')
                installer.main()
            self.assertIn('versioned("worldclass/bootstrap.js", runtimeVersion)', result)
            self.assertNotIn('bootstrap.78b7dd7edb1c.js', result)
            self.assertIn(f'const shellAssetRevision = "bootstrap-{installer.digest(installer.BOOTSTRAP)}";', result)
            self.assertEqual(result, html.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
