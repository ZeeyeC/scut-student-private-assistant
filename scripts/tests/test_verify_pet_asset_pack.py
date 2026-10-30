import hashlib
import json
import runpy
from pathlib import Path

import pytest
from test_import_naiwa_assets import fixture, import_pack

MODULE = Path(__file__).resolve().parents[1] / 'verify-pet-asset-pack.py'


def verify(path):
    return runpy.run_path(str(MODULE))['verify_pack'](path)


def make_pack(tmp_path):
    source, selection = fixture(tmp_path)
    (source / 'NOTICE.md').write_text('Synthetic fixture declaration, no upstream art')
    selection['declarations'] = [{'source': 'NOTICE.md', 'sha256': hashlib.sha256((source / 'NOTICE.md').read_bytes()).hexdigest()}]
    pack = tmp_path / 'pack'
    import_pack(source, selection, pack)
    return pack


def test_verify_all_frames_provenance_and_icon(tmp_path):
    result = verify(make_pack(tmp_path))
    assert result['clips'] == 2 and result['frames'] == 3
    assert result['canvas'] == {'width': 420, 'height': 560}


@pytest.mark.parametrize('fault', ['missing', 'hash', 'timing', 'canvas', 'rights', 'declaration', 'legacy', 'escape', 'source'])
def test_freeze_rejects_incomplete_mixed_or_unattributed_pack(tmp_path, fault):
    pack = make_pack(tmp_path)
    manifest = pack / 'asset-pack.json'
    body = json.loads(manifest.read_text())
    frame = body['clips']['idle']['frames'][0]
    if fault == 'missing': (pack / frame['file']).unlink()
    elif fault == 'hash': (pack / frame['file']).write_bytes(b'not a frame')
    elif fault == 'timing': frame['duration_ns'] = 50_000_000
    elif fault == 'canvas': body['canvas']['width'] = 320
    elif fault == 'rights': body['rights']['status'] = 'pending'
    elif fault == 'declaration': (pack / body['declarations'][0]['file']).unlink()
    elif fault == 'legacy': (pack / 'flash-step.mp4').write_bytes(b'old video')
    elif fault == 'escape': frame['file'] = '../outside.png'
    elif fault == 'source': body['upstream_ref'] = '0' * 40
    manifest.write_text(json.dumps(body))
    # Load outside raises so a missing checker cannot count as a valid rejection.
    module = runpy.run_path(str(MODULE))
    with pytest.raises((ValueError, FileNotFoundError)):
        module['verify_pack'](pack)

def test_release_validation_rejects_synthetic_qa_material(tmp_path):
    pack = make_pack(tmp_path)
    path = pack / 'asset-pack.json'
    body = json.loads(path.read_text()); body['qa_fixture'] = True
    path.write_text(json.dumps(body))
    module = runpy.run_path(str(MODULE))
    with pytest.raises(ValueError, match='QA'):
        module['verify_pack'](pack, release=True)
