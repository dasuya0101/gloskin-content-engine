"""Render the approved casual selfie carousel direction without changing old assets."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/selfie_batch_2026-09-22'
SOURCE_INDEX = ROOT / 'output/approved_design_2026-09-21/index.json'
W, H = 1080, 1350
FONT = 'C:/Windows/Fonts/arialbd.ttf'
COPY = {
    'C1': ['wait you can check your skin with a selfie?',
           'this is what a scan looks like in gloskin',
           'you can save it and check back another day',
           'your saved scans stay in the app',
           'try a selfie in gloskin and see yours'],
    'C2': ['ever zoom into a selfie to check your skin?',
           'gloskin gives you a score from your scan',
           'you can keep a record as you go',
           'then look back at your other scans',
           'the app is called gloskin if you want to try'],
    'C3': ['wait your selfie can have a skin score?',
           'this is where your glo score shows up',
           'you can come back for another scan',
           'and keep your earlier scans too',
           'you can check yours in gloskin'],
    'C4': ['does anyone else just guess with skincare?',
           'you can start with a skin scan in gloskin',
           'save a scan so you can look back later',
           'your previous scans are there when you need them',
           'try gloskin next time you check your skin'],
    'C5': ['a full skincare shelf and still not sure?',
           'gloskin starts with a selfie of your skin',
           'keep a scan alongside your routine',
           'come back to see your saved scans',
           'you can give it a try in gloskin'],
    'C6': ['when did you last check in on your skin?',
           'a selfie in gloskin gives you a glo score',
           'save your scan for another day',
           'then open it whenever you want to look back',
           'gloskin keeps those check ins in one place'],
    'C7': ['about to buy another serum?',
           'you could start with a skin scan in gloskin',
           'keep a record of your skin along the way',
           'your old scans are easy to look back at',
           'try a selfie in gloskin first'],
    'C8': ['so many skincare products and still guessing?',
           'gloskin lets you start with a selfie',
           'save a scan while you figure out your routine',
           'you can look back at your other check ins',
           'find gloskin if you want to try it'],
    'C9': ['all your skin check ins in one place',
           'gloskin turns your scan into a glo score',
           'you can save your scans as you go',
           'then revisit them in the same app',
           'try your next skin check in gloskin'],
    'C10': ['curious what your skin scan would show?',
            'this is how your glo score appears',
            'come back for a scan whenever you like',
            'you can compare it with your saved scans',
            'open gloskin and try a selfie'],
}
CAPTIONS = {
    'C1': 'Ever wondered what a skin scan looks like? Take a selfie in GloSkin to see your Glo Score and save your scan for later.',
    'C2': 'If you already zoom into your selfies to check your skin, you can try a scan in GloSkin. Save it and come back whenever you want to look at it again.',
    'C3': 'Your Glo Score starts with a selfie in GloSkin. You can save your scans and look back at them over time.',
    'C4': 'Skincare can involve a lot of guessing. GloSkin lets you scan your skin and keep your check ins in one place.',
    'C5': 'A shelf full of products is only part of your routine. You can use GloSkin to save skin scans along the way.',
    'C6': 'A quick check in for your skin. Take a selfie in GloSkin and save your scan so you can come back to it later.',
    'C7': 'Thinking about another serum? You can also take a moment to check in on your skin. GloSkin lets you save a scan and look back at it later.',
    'C8': "It's easy to collect skincare products. Keeping track of your skin can be useful too. Try a selfie in GloSkin to start a record of your scans.",
    'C9': 'Keep your skin scans together in GloSkin. Take a selfie to see your Glo Score, then save it for your next check in.',
    'C10': 'Curious about your Glo Score? Take a selfie in GloSkin and save your scan. You can revisit your earlier scans whenever you like.',
}


def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def lines_for(text, font, width):
    result, line = [], ''
    for word in text.split():
        candidate = f'{line} {word}'.strip()
        if font.getlength(candidate) > width and line:
            result.append(line)
            line = word
        else:
            line = candidate
    return result + [line]


def overlay(base, text, portrait):
    image = base.copy()
    font = ImageFont.truetype(FONT, 47 if portrait else 38)
    lines = lines_for(text, font, 800 if portrait else 940)
    if text == COPY['C1'][0]:
        lines = ['wait you can check your', 'skin with a selfie?']
    elif text == COPY['C3'][0]:
        lines = ['wait your selfie can', 'have a skin score?']
    assert len(lines) <= 3, text
    spacing = 11
    draw = ImageDraw.Draw(image)
    label = '\n'.join(lines)
    center_y = 1100 if portrait else 96
    bounds = draw.multiline_textbbox((0, 0), label, font=font, spacing=spacing, align='center', stroke_width=2 if portrait else 0)
    x = (W - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = center_y - (bounds[3] - bounds[1]) / 2 - bounds[1]
    actual = draw.multiline_textbbox((x, y), label, font=font, spacing=spacing, align='center', stroke_width=2 if portrait else 0)
    assert 36 <= actual[0] and actual[2] <= W-36 and 30 <= actual[1] and actual[3] < H-90, actual
    draw.multiline_text((x, y), label, font=font, spacing=spacing, align='center', fill='white' if portrait else '#252525', stroke_width=2 if portrait else 0, stroke_fill='#252525')
    return image, {'text': text, 'font_px': font.size, 'lines': lines, 'bounds': list(actual)}


def portrait_base(path, position):
    with Image.open(path) as source:
        image = ImageOps.fit(source.convert('RGB'), (W, H), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    if position == 2:
        image = ImageOps.fit(image, (W, H), Image.Resampling.LANCZOS, bleed=0.018, centering=(0.46, 0.42))
    elif position == 4:
        image = ImageOps.fit(image, (W, H), Image.Resampling.LANCZOS, bleed=0.01, centering=(0.52, 0.5))
    return image


def screenshot_base(path):
    image = Image.new('RGB', (W, H), '#F4F4F4')
    with Image.open(path) as source:
        shot = source.convert('RGB')
        shot.thumbnail((950, 1140), Image.Resampling.LANCZOS)
    image.paste(shot, ((W-shot.width)//2, 175 + (1140-shot.height)//2))
    return image


def sheet(paths, out, labels):
    canvas = Image.new('RGB', (360 * len(paths), 484), 'white')
    draw = ImageDraw.Draw(canvas)
    for i, (path, label) in enumerate(zip(paths, labels)):
        with Image.open(path) as image:
            canvas.paste(image.resize((360,450), Image.Resampling.LANCZOS), (360*i,34))
        draw.text((360*i+10,7), label, fill='#252525', font=ImageFont.truetype(FONT,18))
    canvas.save(out, quality=94)


def render(entry):
    code = entry['code']
    number = int(code[1:])
    portrait = OUT / 'assets' / f'person_{(number+1)//2}.png'
    if not portrait.exists():
        raise FileNotFoundError(f'Waiting for portrait: {portrait}')
    old_brief = json.loads((Path(entry['folder'])/'brief.json').read_text(encoding='utf-8'))
    old_asset_folder = Path(next(s['image'] for s in old_brief['slides'] if 'image' in s)).parent
    sources = [portrait, old_asset_folder/'shot_after.png', portrait, old_asset_folder/'shot_before.png', portrait]
    folder = OUT/code
    for child in ['slides','clean']:
        (folder/child).mkdir(parents=True, exist_ok=True)
    slides, clean, fit_records, slide_records = [], [], [], []
    for i, (source, text) in enumerate(zip(sources, COPY[code])):
        is_portrait = i % 2 == 0
        base = portrait_base(source, i) if is_portrait else screenshot_base(source)
        image, fit = overlay(base, text, is_portrait)
        path, clean_path = folder/'slides'/f'{i+1:02d}.png', folder/'clean'/f'{i+1:02d}.png'
        image.save(path)
        base.save(clean_path)
        for p in (path, clean_path):
            with Image.open(p) as check:
                assert check.size == (W,H)
                check.verify()
        slides.append(str(path))
        clean.append(str(clean_path))
        fit_records.append(fit)
        slide_records.append({'kind':'selfie' if is_portrait else 'screenshot', 'image':str(source), 'text':text, 'disclosure':None})
    caption = CAPTIONS[code] + '\n\nFind GloSkin at gloskin.app\n\nAI generated photos and sample app scores. These are separate illustrative examples, not customer results or a real before and after.\n\nResults vary. Not medical advice.\n'
    for name in ['caption.txt','caption_instagram.txt']:
        (folder/name).write_text(caption, encoding='utf-8')
    (folder/'native_text.txt').write_text('\n\n'.join(f'Slide {i+1}\n{text}' for i,text in enumerate(COPY[code]))+'\n', encoding='utf-8')
    write_json(folder/'brief.json', {'slug':f'{code}_selfie_2026_09_22', 'brand':'gloskin', 'slides':slide_records, 'formats':['slideshow'], 'design_status':'approved_selfie_direction_2026_09_22', 'is_aigc':True, 'generation_status':'synthetic_portrait_generated', 'image_disclosure':None, 'disclosure_location':'caption and platform controls', 'sample_scores':True, 'customer_testimonial':False, 'source_post_id':entry['source_post_id'], 'source_brief':str(Path(entry['folder'])/'brief.json')})
    write_json(folder/'text_fit.json',fit_records)
    sheet(slides,folder/'contact_sheet.jpg',[f'{code} / {i}' for i in range(1,6)])
    return {'code':code, 'source_post_id':entry['source_post_id'], 'is_aigc':True, 'generation_status':'synthetic_portrait_generated', 'own_brand_promotional_content':True, 'published':False, 'status':'rendered_pending_visual_review', 'slides':slides, 'clean_slides':clean, 'native_text':str(folder/'native_text.txt'), 'folder':str(folder), 'preview':str(folder/'contact_sheet.jpg'), 'video':str(folder/'video.mp4'), 'validation':{'slide_count':5,'clean_slide_count':5,'dimensions':[W,H], 'text_bounds':'pass','image_decode':'pass','publishing_queue_updated':False}}


def video(entry):
    subprocess.run(['ffmpeg','-v','error','-y','-framerate','1/3.5','-i',str(Path(entry['folder'])/'slides/%02d.png'),'-vf','fps=30','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',entry['video']], check=True)
    subprocess.run(['ffmpeg','-v','error','-i',entry['video'],'-f','null','-'],check=True)
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',entry['video']]))
    assert len(probe['streams']) == 1
    assert probe['streams'][0]['width'] == W and probe['streams'][0]['height'] == H
    assert 17.4 <= float(probe['format']['duration']) <= 17.6
    entry['validation'].update(video_full_decode='pass',video_duration_seconds=float(probe['format']['duration']))
    print(f'{entry["code"]}: slides, text bounds and MP4 verified',flush=True)
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codes',nargs='*', help='Optional subset for a preview; full index only written for the full batch.')
    args = parser.parse_args()
    entries = [x for x in json.loads(SOURCE_INDEX.read_text()) if x['code'] in COPY and (not args.codes or x['code'] in args.codes)]
    rendered = [render(entry) for entry in entries]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rendered = list(pool.map(video,rendered))
    if not args.codes:
        write_json(OUT/'index.json',rendered)
        grid = Image.new('RGB',(1800, 970),'white')
        draw = ImageDraw.Draw(grid)
        for i, entry in enumerate(rendered):
            x,y=(i%5)*360,(i//5)*485
            with Image.open(entry['slides'][0]) as im:
                grid.paste(im.resize((360,450),Image.Resampling.LANCZOS),(x,y+35))
            draw.text((x+12,y+8),entry['code'],font=ImageFont.truetype(FONT,18),fill='#252525')
        grid.save(OUT/'all_covers.jpg',quality=94)
        write_json(OUT/'validation_carousels.json', {'posts':len(rendered),'slides':sum(len(e['slides']) for e in rendered),'clean_slides':sum(len(e['clean_slides']) for e in rendered),'results':[{ 'code':e['code'], **e['validation']} for e in rendered]})
    print(OUT,flush=True)


if __name__ == '__main__':
    main()
