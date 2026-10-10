"""Render one casual cover preview and a clean base for native posting text."""
from pathlib import Path
import json
import shutil
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output/design_review_selfie_native/C1'
SOURCE = Path(r'C:\Users\Amols\.codex\generated_images\01a08cc1-cf7a-7252-b5e1-220e5e074277\exec-0daecde1-0d4e-40d3-b4fb-c7f5fb1f4473.png')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, OUT / 'selfie_original.png')
    photo = ImageOps.fit(Image.open(SOURCE).convert('RGB'), (1080, 1350))
    photo.save(OUT / 'cover_clean.png')
    font = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', 47)
    draw = ImageDraw.Draw(photo)
    lines = ['wait you can check your', 'skin with a selfie?']
    for i, line in enumerate(lines):
        draw.text((540, 1065 + i * 58), line, font=font, anchor='mm',
                  fill='white', stroke_width=2, stroke_fill='#262626')
    photo.save(OUT / 'cover_with_text.png')
    (OUT / 'native_text.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (OUT / 'caption_instagram.txt').write_text(
        'You can take a selfie in GloSkin to see your Glo Score and save your scans to check back on later.\n\n'
        'AI generated photo used to show the app.\n\n'
        'gloskin.app\n', encoding='utf-8')
    (OUT / 'brief.json').write_text(json.dumps({
        'design_status': 'selfie_cover_preview_pending_review',
        'scope': 'One cover preview. Completed batch and posting handoff are unchanged.',
        'is_aigc': True,
        'image_disclosure': None,
        'disclosure_location': 'caption and platform posting controls',
        'copy': ' '.join(lines),
        'source': str(SOURCE),
        'image_generation': 'built-in imagegen',
        'followup_slides': 'Use a plain app capture after the selfie, without a decorative phone frame. Product Match screen is still needed for that separate concept.'
    }, indent=2), encoding='utf-8')
    print(OUT)

if __name__ == '__main__':
    main()
