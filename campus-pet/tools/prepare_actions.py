"""Cut user-selected video actions into transparent, silent PNG frames.

Input frames come from extract_video.swift at 20 fps and max-size 720.
Color-key the blue stage, keep the largest character component, fill enclosed
features (green eyes/dark mouth), then normalize each clip on a fixed canvas.
"""
from pathlib import Path
import json
import hashlib
import numpy as np
from PIL import Image, ImageFilter, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FRAMES = ROOT / 'build/video-frames'
OUTPUT = ROOT / 'Resources/Animations'
FPS = 20
CLIPS = [('flash-step', '闪身步', 2.1, 5.25),
         ('arm-swing', '大抡臂', 11.05, 15.35),
         ('bear-shake', '狗熊哆嗦毛', 25.6, 28.9)]


def largest_component(mask):
    """Row-run union find; avoids a third-party CV runtime in the Mac app."""
    parent, runs, previous = [], [], []
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for y, row in enumerate(mask):
        edges = np.diff(np.pad(row.astype(np.int8), (1, 1)))
        current = []
        old_index = 0
        for left, right in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            i = len(parent); parent.append(i); runs.append((y, int(left), int(right)))
            while old_index < len(previous) and previous[old_index][1] < left:
                old_index += 1
            j = old_index
            while j < len(previous) and previous[j][0] <= right:
                parent[find(i)] = find(previous[j][2]); j += 1
            current.append((left, right, i))
        previous = current
    areas = {}
    for i, (_, left, right) in enumerate(runs):
        root = find(i); areas[root] = areas.get(root, 0) + right - left
    result = np.zeros_like(mask)
    if not areas: return result
    largest = max(areas, key=areas.get)
    for i, (y, left, right) in enumerate(runs):
        if find(i) == largest: result[y, left:right] = True
    return result


def cutout(index):
    source = Image.open(FRAMES / f'{index:06}.png').convert('RGB')
    rgb = np.asarray(source).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    warm = ((r - b > 14) & (g - b > 7)) | ((g - b > 14) & (r - b > -60))
    # The room reflection starts below the feet; the caption is left of the pet.
    warm[500:, :] = False
    warm[420:, :250] = False
    warm[:20, :] = False
    closed = Image.fromarray(warm.astype('uint8') * 255).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    body = largest_component(np.asarray(closed) > 0)
    # Keep enclosed non-yellow details (eyes/mouth), while leaving gaps outside.
    exterior = largest_component(~body)
    alpha = Image.fromarray((~exterior).astype('uint8') * 255).filter(ImageFilter.GaussianBlur(.45))
    image = source.convert('RGBA'); image.putalpha(alpha)
    return image


def normalize(image, geometry):
    x, baseline, scale = geometry
    box = image.getbbox()
    crop = image.crop(box)
    crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (320, 320))
    canvas.alpha_composite(crop, (round(160 + (box[0] - x) * scale), round(313 + (box[1] - baseline) * scale)))
    return canvas


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {'version': 1, 'fps': FPS, 'canvas': [320, 320], 'source': 'https://www.bilibili.com/video/BV1uSe16KEfi/', 'clips': []}
    preview = Image.new('RGB', (320 * 3, 350 * 3), '#e9e6dc')
    draw = ImageDraw.Draw(preview)
    idle_geometry = None
    for col, (key, title, start, end) in enumerate(CLIPS):
        images = [cutout(i) for i in range(round(start * FPS), round(end * FPS))]
        boxes = [im.getbbox() for im in images]
        union = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        first = boxes[0]
        scale = min(240 / (first[3] - first[1]), 304 / (union[2] - union[0]), 304 / (union[3] - union[1]))
        geometry = ((union[0] + union[2]) / 2, union[3], scale)
        if key == 'arm-swing': idle_geometry = geometry
        directory = OUTPUT / key; directory.mkdir(exist_ok=True)
        for old in directory.glob('*.png'): old.unlink()
        normalized = [normalize(im, geometry) for im in images]
        for i, image in enumerate(normalized): image.save(directory / f'{i:04}.png', optimize=True)
        for row, n in enumerate([0, len(images)//3, 2*len(images)//3]):
            preview.paste(normalized[n], (col*320, row*350+25), normalized[n])
            draw.text((col*320+10, row*350+8), f'{key} frame {n}', fill='#223322')
        # Human-review animation, kept outside the application bundle.
        gif_frames=[]
        for im in normalized:
            bg=Image.new('RGB', im.size, '#e9e6dc'); bg.paste(im, mask=im.getchannel('A')); gif_frames.append(bg)
        gif_frames[0].save(ROOT/'build'/f'{key}-preview.gif', save_all=True, append_images=gif_frames[1:], duration=50, loop=0)
        manifest['clips'].append({'id': key, 'title': title, 'start': start, 'end': end, 'frameCount': len(images)})
        print(f'{title}: {len(images)} frames, {len(images)/FPS:.2f}s, bounds {union}', flush=True)
    normalize(cutout(220), idle_geometry).save(OUTPUT / 'idle.png')
    manifest['sourceSHA256'] = hashlib.sha256((ROOT/'art/video/source.mp4').read_bytes()).hexdigest()
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    preview.save(ROOT / 'build/actions-contact.png')

if __name__ == '__main__': main()
