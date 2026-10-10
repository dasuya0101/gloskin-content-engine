"""Export a fresh, portable Instagram content handoff; never publish or sync.

Each run must target a new directory so Muse's receipts cannot be overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r'C:\Users\Amols\Downloads\gloskin_content_engine')

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def export(out, instagram_handle=None, index_path=None, make_zip=False):
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Choose a new empty output directory; existing handoffs are never overwritten.')
    out.mkdir(parents=True, exist_ok=True)
    approved_index = ROOT/'output/approved_design_2026-09-21/index.json'
    selfie_index = ROOT/'output/selfie_batch_2026-09-22/index.json'
    if selfie_index.exists():
        approved_index = selfie_index
    default_index = approved_index if approved_index.exists() else ROOT/'output/gloskin_september_11_revisions/index.json'
    exports = json.loads((index_path or default_index).read_text())
    old_root = SOURCE/'posts/gloskin/gloskin_main/2026-08-30'
    # The two unchanged packages complete the current batch of ten concepts.
    for code, post_id in [('C3', '4241bf1d0228'), ('C4', '59f195a8fe59')]:
        if any(entry['code'] == code for entry in exports):
            continue
        folder = old_root/post_id
        exports.append({'code': code, 'source_post_id': post_id,
                        'folder': str(folder), 'is_aigc': True,
                        'slides': [str(p) for p in sorted((folder/'slides').glob('*.png'))]})
    posts = []
    for entry in exports:
        code = entry['code']
        folder = Path(entry['folder'])
        brief = json.loads((folder/'brief.json').read_text(encoding='utf-8'))
        post_id = entry.get('source_post_id')
        if (folder/'caption_instagram.txt').is_file():
            caption = (folder/'caption_instagram.txt').read_text(encoding='utf-8')
        elif post_id:
            original = old_root/post_id
            payload = json.loads((original/'platform_payloads.json').read_text())
            old_hook = json.loads((original/'brief.json').read_text())['slides'][0]['text']
            caption = payload['instagram']['caption'].replace(old_hook, brief['slides'][0]['text'])
        else:
            caption = (folder/'caption.txt').read_text(encoding='utf-8')
        # Keep operational tracking in the manifest rather than the visible caption.
        caption = '\n'.join(line for line in caption.splitlines() if not line.startswith('Tracking:'))
        while '\n\n\n' in caption:
            caption = caption.replace('\n\n\n', '\n\n')
        target = out/'CONTENT'/code
        (target/'media').mkdir(parents=True)
        media = []
        assert len(entry['slides']) == 5, code
        for idx, source in enumerate(entry['slides'], start=1):
            dest = target/'media'/f'{idx:02d}.png'
            shutil.copy2(source, dest)
            media.append({'path': dest.relative_to(out).as_posix(),
                          'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()})
        caption_path = target/'caption_instagram.txt'
        caption_path.write_text(caption.strip()+'\n', encoding='utf-8')
        # Optional editing bases live outside media so they cannot double the post.
        editing_assets = []
        if (folder/'clean').is_dir():
            clean_target = out/'EDITING_BASES'/code
            clean_target.mkdir(parents=True)
            for source in sorted((folder/'clean').glob('*.png')):
                dest = clean_target/source.name
                shutil.copy2(source, dest)
                editing_assets.append(dest.relative_to(out).as_posix())
            if (folder/'native_text.txt').is_file():
                shutil.copy2(folder/'native_text.txt', clean_target/'native_text.txt')
        fingerprint = hashlib.sha256((''.join(x['sha256'] for x in media)+caption).encode()).hexdigest()
        record = {'content_id': 'gloskin_'+code, 'source_post_id': post_id,
                  'revision': fingerprint[:12], 'platform': 'instagram',
                  'account_handle': instagram_handle, 'format': 'carousel',
                  'headline': brief['slides'][0]['text'], 'asset_state': 'prepared',
                  'design_revision': brief.get('design_status', 'legacy'),
                  'delivery_state': 'unscheduled', 'scheduled_at': None,
                  'timezone': 'America/New_York', 'publication_history': 'not_reconciled',
                  'caption_file': caption_path.relative_to(out).as_posix(),
                  'media': media, 'synthetic_people_or_results': entry['is_aigc'],
                  'optional_editing_bases': editing_assets,
                  'own_brand_promotional_content': True, 'posting_receipt': None}
        write_json(target/'post.json', record)
        posts.append(record)
    draft_specs = [
        ('routine_order', 'dreamina_routine_hook_retry', 'gloskin_routine_hook_retry_seedance_2_5_720p.mp4'),
        ('personal_routine', 'dreamina_routine_variant_1', 'gloskin_routine_variant_1_seedance_2_5_720p.mp4'),
        ('morning_evening', 'dreamina_routine_variant_2', 'gloskin_routine_variant_2_seedance_2_5_720p.mp4'),
    ]
    drafts=[]
    for code, directory, filename in draft_specs:
        source=SOURCE/'output/gloskin/gloskin_main'/directory/filename
        if not source.is_file():
            raise FileNotFoundError(source)
        dest=out/'DRAFTS'/code/'video.mp4'
        dest.parent.mkdir(parents=True)
        shutil.copy2(source,dest)
        record={'content_id':'gloskin_'+code,'asset_state':'draft',
                'delivery_state':'hold','reason':'Final caption, full playback review and disclosure preparation remain.',
                'video':dest.relative_to(out).as_posix(),
                'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
        write_json(dest.parent/'post.json',record)
        drafts.append(record)
    (out/'PLANNING').mkdir()
    for filename in ['gloskin_screen_video_scripts_2026-09.md','gloskin_product_match_carousel_draft.md']:
        shutil.copy2(ROOT/'docs'/filename,out/'PLANNING'/filename)
    (out/'RECEIPTS').mkdir()
    write_json(out/'manifest.json', {'schema_version':1,'brand':'GloSkin','platform':'instagram',
               'account_handle':instagram_handle,'timezone':'America/New_York',
               'batch_state':'awaiting_account_and_schedule' if not instagram_handle else 'awaiting_schedule',
               'posts':posts,'drafts':drafts})
    write_json(out/'RECEIPTS/template.json', {'content_id':None,'revision':None,'platform':'instagram',
               'account_handle':None,'status':'template_only','started_at':None,'published_at':None,
               'post_url':None,'error':None})
    shutil.copy2(ROOT/'docs/muse_drive_handoff_instructions.md',out/'START_HERE.md')
    for post in posts:
        assert (out/post['caption_file']).is_file()
        for asset in post['media']:
            assert not Path(asset['path']).is_absolute()
            assert hashlib.sha256((out/asset['path']).read_bytes()).hexdigest()==asset['sha256']
    archive=None
    if make_zip:
        archive=out.parent/(out.name+'.zip')
        if archive.exists():
            raise SystemExit('Archive already exists; handoff directory is complete but was not archived.')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for path in out.rglob('*'):
                if path.is_file():z.write(path,path.relative_to(out))
    print(json.dumps({'prepared_carousels':len(posts),'draft_videos':len(drafts),
                      'folder':str(out),'zip':str(archive) if archive else None,'uploaded':False},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--instagram-handle')
    parser.add_argument('--index', type=Path, help='Explicit rendered batch index; keeps original content IDs.')
    parser.add_argument('--zip', action='store_true', help='Optionally create an archive; folder export is the default.')
    args=parser.parse_args()
    export(args.out.resolve(),args.instagram_handle,args.index,args.zip)
