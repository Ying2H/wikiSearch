import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'posix' and shutil.which('bash') and shutil.which('git'), 'Linux publisher integration test')
class PublisherTests(unittest.TestCase):
    def test_repeat_publish_and_remote_failure_preserve_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'project'
            (root / 'scripts').mkdir(parents=True)
            script = root / 'scripts/publish_github_pages.sh'
            shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/publish_github_pages.sh', script)
            remote = Path(temp) / 'remote.git'
            def git(*args):
                return subprocess.run(['git', *map(str, args)], check=True, capture_output=True, text=True).stdout.strip()
            git('init', '--bare', remote)
            git('init', root)
            git('-C', root, 'remote', 'add', 'origin', remote)
            site = root / 'data/publish/site'
            site.mkdir(parents=True)
            (site / 'index.html').write_text('search', encoding='utf-8')
            def publish():
                return subprocess.run(['bash', str(script)], cwd=root, capture_output=True, text=True)
            first = publish()
            self.assertEqual(first.returncode, 0, first.stderr)
            head = git('--git-dir', remote, 'rev-parse', 'gh-pages')
            second = publish()
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn('no push needed', second.stdout)
            self.assertEqual(git('--git-dir', remote, 'rev-parse', 'gh-pages'), head)
            (site / 'index.html').write_text('updated search', encoding='utf-8')
            third = publish()
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertNotEqual(git('--git-dir', remote, 'rev-parse', 'gh-pages'), head)
            git('-C', root, 'remote', 'set-url', 'origin', Path(temp) / 'missing.git')
            failed = publish()
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual((root / 'data/github-pages/index.html').read_text(), 'updated search')
