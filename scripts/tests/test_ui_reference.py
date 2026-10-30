"""A missing/empty geometry report cannot stand in for actual UI measurements."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image

spec=importlib.util.spec_from_file_location('ui_reference',Path(__file__).resolve().parents[1]/'verify-ui-reference.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('geometry',[None,{}, {'today':{'x':214,'y':31,'width':1028,'height':43}}])
def test_incomplete_geometry_is_rejected(tmp_path,geometry):
    reference=tmp_path/'docs/design/reference';screens=reference/'screens';screens.mkdir(parents=True)
    actual=tmp_path/'actual';actual.mkdir()
    (reference/'reference-manifest.json').write_text(json.dumps({'status':'accepted','knownIssues':[],'files':[]}))
    image=Image.new('RGB',(1280,782),'white')
    for page in ('today','calendar','tasks','assistant','settings','task-detail','import-default'):
        name=page+('.png' if page in ('task-detail','import-default') else '-desktop.png')
        image.save(screens/name);image.save(actual/name)
    if geometry is not None:(actual/'geometry.json').write_text(json.dumps(geometry))
    with patch.object(sys,'argv',['verify-ui-reference.py','--reference',str(reference),'--actual',str(actual)]):
        with pytest.raises(SystemExit) as result:module.main()
    assert result.value.code==1
