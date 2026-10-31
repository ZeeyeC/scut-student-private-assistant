import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('app_build_mode',Path(__file__).resolve().parents[1]/'app_build_mode.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def test_release_removes_developer_path_even_when_reusing_a_bundle(tmp_path):
    module.configure_source_marker(tmp_path,Path('/private/developer/source'),False)
    assert (tmp_path/'source-project.txt').exists()
    module.configure_source_marker(tmp_path,Path('/private/developer/source'),True)
    assert not (tmp_path/'source-project.txt').exists()
