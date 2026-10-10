"""Render the approved September 21 design for C1-C10 into a separate batch.

Original source assets, briefs, posting manifests and handoffs are read-only.
"""
import concurrent.futures
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

import carousel_design_preview as design

ROOT = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/Amols/Downloads/gloskin_content_engine')
OLD = SOURCE / 'posts/gloskin/gloskin_main/2026-08-30'
OUT = ROOT / 'output/approved_design_2026-09-21'
IDS = ['ec5cfa7516bd', '587a75f6746a', '4241bf1d0228', '59f195a8fe59',
       '051fb505147f', '78297f5f88ce', '1cb2359b772b', '50d5f8d99bae',
       '623a548db7b0', '35e27c98315a']
BASE_TEXT_BLOCK = design.text_block
TEXT_FITS = []


def fitted_text_block(image, text, size, cy, color=design.INK, width=900, bold=True):
    """Fit copy in the approved heading zones without changing the words."""
    requested = size
    max_lines = 2 if cy in (1175, 157) else 3 if cy == 590 else 1
    min_size = 38 if cy in (1175, 157) else 24
    while len(design.wrap(text, design.font(size, bold), width)) > max_lines:
        size -= 1
        if size < min_size:
            raise ValueError(f'Copy cannot fit approved area: {text!r}')
    TEXT_FITS.append({'text': text, 'requested_px': requested, 'font_px': size,
                      'lines': len(design.wrap(text, design.font(size, bold), width))})
    return BASE_TEXT_BLOCK(image, text, size, cy, color=color, width=width, bold=bold)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def render_one(number, post_id):
    code = f'C{number}'
    original = OLD / post_id
    revised = ROOT / f'output/gloskin_september_11_revisions/{code}_revised/brief.json'
    brief = json.loads((revised if revised.exists() else original / 'brief.json').read_text(encoding='utf-8'))
    brief['slug'] = f'{code}_approved_design_2026_09_21'
    brief['design_status'] = 'approved_direction_2026_09_21'
    for idx, slide in enumerate(brief['slides']):
        slide.pop('disclosure_chip', None)
        if 'image' in slide:
            name = ['opening.png', 'shot_before.png', 'shot_after.png', 'after.png'][idx]
            slide['image'] = str(original / 'source_assets' / name)
            if not Path(slide['image']).is_file():
                raise FileNotFoundError(slide['image'])
    folder = OUT / code
    slides_dir = folder / 'slides'
    slides_dir.mkdir(parents=True, exist_ok=True)
    slides = []
    first_fit = len(TEXT_FITS)
    for idx, slide in enumerate(brief['slides']):
        image = (design.portrait(slide, idx) if slide.get('layout') == 'image_top'
                 else design.screenshot(slide, idx) if slide['kind'] == 'screenshot'
                 else design.cta(slide, idx))
        dest = slides_dir / f'{idx+1:02d}.png'
        image.save(dest)
        slides.append(str(dest))
    write_json(folder / 'brief.json', brief)
    write_json(folder / 'text_fit.json', TEXT_FITS[first_fit:])
    old_brief = json.loads((original / 'brief.json').read_text(encoding='utf-8'))
    payload = json.loads((original / 'platform_payloads.json').read_text(encoding='utf-8'))
    caption = payload['instagram']['caption'].replace(old_brief['slides'][0]['text'], brief['slides'][0]['text'])
    caption = '\n'.join(line for line in caption.splitlines() if not line.startswith('Tracking:'))
    while '\n\n\n' in caption:
        caption = caption.replace('\n\n\n', '\n\n')
    for filename in ['caption.txt', 'caption_instagram.txt']:
        (folder / filename).write_text(caption.strip() + '\n', encoding='utf-8')
    sheet = Image.new('RGB', (1800, 480), 'white')
    for idx, path in enumerate(slides):
        with Image.open(path) as im:
            im.thumbnail((360, 450), Image.Resampling.LANCZOS)
            sheet.paste(im, (360*idx, 30))
        ImageDraw.Draw(sheet).text((360*idx+12, 7), f'{code} / {idx+1:02d}', font=design.font(18), fill=design.INK)
    sheet.save(folder / 'contact_sheet.jpg', quality=94)
    return {'code': code, 'source_post_id': post_id, 'is_aigc': True,
            'own_brand_promotional_content': True, 'published': False,
            'status': 'rendered_pending_visual_review', 'slides': slides,
            'video': str(folder / 'video.mp4'), 'folder': str(folder),
            'preview': str(folder / 'contact_sheet.jpg'),
            'validation': {'slide_count': 5, 'dimensions': [1080, 1350],
                           'publishing_queue_updated': False}}


def encode_and_validate(entry):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '1/3.5',
                    '-i', str(Path(entry['folder']) / 'slides/%02d.png'),
                    '-vf', 'fps=30', '-c:v', 'libx264', '-threads', '2', '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart', entry['video']], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', entry['video'], '-f', 'null', '-'], check=True)
    for path in entry['slides']:
        with Image.open(path) as image:
            assert image.size == (1080, 1350)
            image.verify()
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                               '-show_format', '-of', 'json', entry['video']]))
    assert len(probe['streams']) == 1
    assert probe['streams'][0]['width'] == 1080 and probe['streams'][0]['height'] == 1350
    assert 17.4 <= float(probe['format']['duration']) <= 17.6
    entry['validation']['video_full_decode'] = 'pass'
    entry['validation']['video_duration_seconds'] = float(probe['format']['duration'])
    print(f"{entry['code']}: 5 slides and silent MP4 verified", flush=True)
    return entry


def main():
    design.text_block = fitted_text_block
    OUT.mkdir(parents=True, exist_ok=True)
    entries = [render_one(number, post_id) for number, post_id in enumerate(IDS, 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        entries = list(pool.map(encode_and_validate, entries))
    write_json(OUT / 'index.json', entries)
    print(OUT)


if __name__ == '__main__':
    main()
