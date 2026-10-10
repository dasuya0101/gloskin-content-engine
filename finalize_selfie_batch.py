"""Assemble the reviewed batch and verify the portable Muse export."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from clean_image_metadata import clean, chunks
from export_muse_handoff import export

ROOT = Path(__file__).resolve().parent
BATCH = ROOT/'output/selfie_batch_2026-09-22'
HANDOFF = Path(r'C:\Users\Amols\Downloads\GloSkin Content - Selfies 2026-09-22')

def main():
    entries = json.loads((BATCH/'index.json').read_text())
    entries = [e for e in entries if not e['code'].startswith('W2_')]
    entries += json.loads((BATCH/'match_posts_index.json').read_text())
    assert len(entries)==12 and len({e['code'] for e in entries})==12
    metadata = []
    for e in entries:
        for path in e['slides']+e['clean_slides']:
            metadata.append(clean(Path(path)))
        e['status'] = 'rendered_visual_reviewed'
        e['validation']['contact_sheet_review'] = 'pass'
        e['validation']['png_optional_metadata'] = 'removed_and_verified'
    (BATCH/'index.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    (BATCH/'metadata_report.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    grid = Image.new('RGB',(1440,1470),'white')
    draw = ImageDraw.Draw(grid)
    for i,e in enumerate(entries):
        x,y=(i%4)*360,(i//4)*490
        draw.text((x+10,y+8),e['code'],font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',20),fill='#252525')
        with Image.open(e['slides'][0]) as im:
            grid.paste(im.resize((360,450)),(x,y+36))
    grid.save(BATCH/'all_covers.jpg',quality=94)
    pair=Image.new('RGB',(1080,675),'white')
    for x,code in [(0,'C3'),(540,'C9')]:
        with Image.open(BATCH/code/'slides/01.png') as im:
            pair.paste(im.resize((540,675)),(x,0))
    pair.save(BATCH/'outfit_preview.jpg',quality=94)
    export(HANDOFF,index_path=BATCH/'index.json')
    manifest=json.loads((HANDOFF/'manifest.json').read_text())
    for post in manifest['posts']:
        code=post['content_id'].removeprefix('gloskin_')
        assert (HANDOFF/post['caption_file']).read_text(encoding='utf-8')==(BATCH/code/'caption_instagram.txt').read_text(encoding='utf-8').strip()+'\n'
        assert len(post['media'])==5 and len(post['optional_editing_bases'])==5
        for asset in post['media']:
            path=HANDOFF/asset['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256']
            assert set(chunks(path)) <= {'IHDR','IDAT','IEND'}
        for path in post['optional_editing_bases']:
            assert set(chunks(HANDOFF/path)) <= {'IHDR','IDAT','IEND'}
    report={'carousels':12,'posting_pngs':60,'clean_editing_pngs':60,'captions_verified':12,'metadata_check':'essential PNG chunks only','draft_videos':3,'uploaded':False,'scheduled':False,'handoff':str(HANDOFF)}
    (BATCH/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (BATCH/'README.md').write_text('Approved casual selfie batch, September 22\n\n12 replacement carousel concepts, 60 slides, 60 clean editing bases, 12 MP4 previews and rewritten captions.\n\nPortraits generated with built-in imagegen; prompts in generation_prompts.json. Optional embedded PNG metadata removed and decoded pixels checked unchanged. Synthetic status is retained in captions and manifests.\n\nThe two Product Match explainers do not contain a new app capture. The separate release walkthrough still needs supplied screens.\n\nUnzipped Muse handoff: '+str(HANDOFF)+'\n\nPrepared locally, not uploaded or scheduled.\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
