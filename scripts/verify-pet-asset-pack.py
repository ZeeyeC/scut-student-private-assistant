"""Validate a complete pinned NaiWa pack, and optionally its frozen App resources."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import runpy

_HELPERS = runpy.run_path(str(Path(__file__).with_name('import-naiwa-assets.py')))
PIN = _HELPERS['PIN']


def verify_pack(root, *, release=False):
    root = Path(root).resolve()
    document, _ = _HELPERS['read_json'](root, 'asset-pack.json')
    if document.get('schema_version') != 1 or document.get('upstream_ref') != PIN or document.get('repository') != 'https://github.com/SbongeBobybl/NaiWaChatPet':
        raise ValueError('Unrecognized asset source/schema')
    if release and document.get('qa_fixture'):
        raise ValueError('QA fixture cannot enter a release')
    rights = document.get('rights', {})
    if rights.get('status') != 'verified' or not str(rights.get('basis', '')).strip():
        raise ValueError('Missing asset permission evidence')
    if document.get('canvas') != {'width': 420, 'height': 560} or not 0 <= document['ground_y'] <= 560:
        raise ValueError('Expected original canvas/ground')
    allowed = {'asset-pack.json', 'SOURCES.md'}
    clips = document['clips']
    if not 1 <= len(clips) <= 64:
        raise ValueError('Invalid clips')
    count = 0
    for name, clip in clips.items():
        frames = clip['frames']
        if not 1 <= len(frames) <= 240 or not isinstance(clip['loop'], bool):
            raise ValueError('Invalid frame count/loop')
        expected = clip.get('source_duration_ns')
        if 'source_fps' in clip:
            fps = clip['source_fps']
            if not 0 < fps <= 60: raise ValueError('Invalid FPS')
            expected = round(1_000_000_000 / fps)
        if not isinstance(expected, int) or not 0 < expected <= 10_000_000_000:
            raise ValueError('Source timing missing')
        for frame in frames:
            if frame['duration_ns'] != expected:
                raise ValueError('Timing differs from source metadata')
            if not frame.get('source_path') or '..' in PurePosixPath(frame['source_path']).parts:
                raise ValueError('Frame provenance missing')
            _HELPERS['verified_png'](root, frame['file'], frame['sha256'], (420, 560))
            allowed.add(frame['file']); count += 1
        for key in ['transition_in', 'transition_out']:
            if clip.get(key) and clip[key] not in clips: raise ValueError('Missing transition')
        if clip.get('pose_hold_ms') is not None and (clip['pose_hold_ms'] != 800 or len(frames) != 1):
            raise ValueError('Invalid static pose')
    states = document['states']
    if set(states) != _HELPERS['STATES'] or any(name not in clips for name in states.values()):
        raise ValueError('Incomplete states')
    if document['default_frame'] != clips[states['idle']]['frames'][0]['file']:
        raise ValueError('Missing same-character default')
    ids = set()
    for action in document['actions']:
        if action['id'] in ids or not action['title'] or not action['clips'] or any(name not in clips for name in action['clips']):
            raise ValueError('Invalid manual action')
        ids.add(action['id'])
        if action.get('hold_ms') is not None and (action['hold_ms'] != 800 or len(action['clips']) != 1 or len(clips[action['clips'][0]]['frames']) != 1):
            raise ValueError('Invalid manual hold')
    icon = document['icon']
    _HELPERS['verified_png'](root, icon['file'], icon['sha256'], (256, 256)); allowed.add(icon['file'])
    declarations = document.get('declarations', [])
    if not declarations or not _HELPERS['source_file'](root, 'SOURCES.md').read_text().strip():
        raise ValueError('Missing declarations')
    for item in declarations:
        path = _HELPERS['source_file'](root, item['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Declaration hash mismatch')
        allowed.add(item['file'])
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file() or path.is_symlink()}
    if actual != allowed:
        raise ValueError('Unlisted or legacy resources in asset pack')
    return {'upstream_ref': PIN, 'clips': len(clips), 'frames': count, 'canvas': document['canvas'], 'actions': [action['id'] for action in document['actions']]}


def verify_app(app, *, release=False):
    resources = Path(app) / 'Contents/Resources'
    if any((resources / name).exists() for name in ['Animations', 'naiwa.png']):
        raise ValueError('Legacy character fallback found in App')
    result = verify_pack(resources / 'NaiWa', release=release)
    if not (resources / 'AppIcon.icns').is_file():
        raise ValueError('Missing App icon')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--pack', type=Path)
    group.add_argument('--app', type=Path)
    parser.add_argument('--release', action='store_true', help='Reject synthetic QA packs')
    args = parser.parse_args()
    print(json.dumps(verify_app(args.app, release=args.release) if args.app else verify_pack(args.pack, release=args.release), ensure_ascii=False))


if __name__ == '__main__': main()
