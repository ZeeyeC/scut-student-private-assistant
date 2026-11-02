"""Cloud cleanup cannot remove unverified, changed, linked or latest releases."""
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('cloud_archive',Path(__file__).resolve().parents[1]/'archive-releases.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)

class ArchiveSafetyTests(unittest.TestCase):
    def test_nested_private_file_is_rejected(self):
        nested=io.BytesIO()
        with zipfile.ZipFile(nested,'w') as z:z.writestr('source/model.env','KEY=not-for-upload')
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:z.writestr('source.zip',nested.getvalue())
        outer.seek(0)
        with self.assertRaisesRegex(RuntimeError,'Private'):a.audit_zip(outer,set())

    def test_invalid_zip_fixture_is_scanned_but_not_treated_as_release_zip(self):
        outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:z.writestr('tests/broken.zip',b'intentionally not zip')
        outer.seek(0);a.audit_zip(outer,set())

    def test_cleanup_preserves_everything_until_all_preflight_checks_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);history=base/'history';history.mkdir()
            old=history/'Demo2.7';old.mkdir();(old/'note.md').write_text('original')
            latest=base/'Demo2.8.1';latest.mkdir();(latest/'课间桌宠.app').mkdir()
            (latest/'验证结果.json').write_text('{"passed":true}')
            row={'local_root':str(old),'remote_verified':False,'tree':a.tree_inventory(old,set()),'release':'Demo2.7'}
            plan=base/'plan.json';a.save(plan,{'records':[row]})
            with patch.object(a,'DEFAULT_HISTORY',history):
                with self.assertRaises(RuntimeError):a.cleanup(plan,latest,set())
                self.assertTrue(old.exists())
                row['remote_verified']=True;a.save(plan,{'records':[row]})
                (old/'note.md').write_text('changed')
                with self.assertRaisesRegex(RuntimeError,'changed'):a.cleanup(plan,latest,set())
                self.assertTrue(old.exists())
                (old/'note.md').write_text('original')
                a.cleanup(plan,latest,set());self.assertFalse(old.exists())
                self.assertTrue(latest.exists())

    def test_tree_rejects_external_links_and_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'old';root.mkdir();(root/'link').symlink_to('/tmp')
            with self.assertRaises(RuntimeError):a.tree_inventory(root,set())
            (root/'link').unlink();(root/'model.env').write_text('secret')
            with self.assertRaises(RuntimeError):a.tree_inventory(root,set())

if __name__=='__main__':unittest.main()
