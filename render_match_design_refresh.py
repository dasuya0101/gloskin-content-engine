"""Apply the approved neutral palette and smaller type to the two text carousels."""
import json
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw
import carousel_design_preview as design

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/approved_design_2026-09-21'

def main():
    entries=[]
    for code in ['W2_popular_vs_fit','W2_match_score_faq']:
        old=ROOT/'output/gloskin_september_11_revisions'/code
        folder=OUT/code
        folder.mkdir(parents=True,exist_ok=True)
        brief=json.loads((old/'brief.json').read_text(encoding='utf-8'))
        brief['design_status']='approved_direction_2026_09_21'
        slides=[]
        for idx,slide in enumerate(brief['slides']):
            slide['disclosure']='Product-fit guidance. Results vary.'
            if slide['kind']=='cta':
                # A single footer carries this caveat rather than repeating it above.
                adjusted=dict(slide,subtext='')
                image=design.cta(adjusted,idx)
            else:
                image=Image.new('RGB',(design.W,design.H),design.BACKGROUND)
                design.chrome(image,idx)
                draw=ImageDraw.Draw(image)
                draw.text((540,460),'PRODUCT MATCH',font=design.font(26,True),fill=design.ACCENT,anchor='mm')
                design.text_block(image,slide['text'],64 if idx==0 else 58,650,width=870)
                design.footer(image,slide['disclosure'])
            path=folder/f'slide_{idx+1:02d}.png'
            image.save(path)
            slides.append(str(path))
        (folder/'brief.json').write_text(json.dumps(brief,indent=2),encoding='utf-8')
        shutil.copy2(old/'caption.txt',folder/'caption.txt')
        preview=Image.new('RGB',(1800,480),'white')
        for idx,path in enumerate(slides):
            im=Image.open(path); im.thumbnail((360,450),Image.Resampling.LANCZOS)
            preview.paste(im,(360*idx,30))
            ImageDraw.Draw(preview).text((360*idx+12,7),f'{idx+1:02d}',font=design.font(18),fill=design.INK)
        preview.save(folder/'contact_sheet.jpg',quality=94)
        video=folder/'slideshow.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-framerate','1/4.2','-i',str(folder/'slide_%02d.png'),
                        '-vf','fps=30','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
        entries.append({'code':code,'source_post_id':None,'folder':str(folder),'slides':slides,
                        'video':str(video),'preview':str(folder/'contact_sheet.jpg'),'is_aigc':False})
    (OUT/'text_posts_index.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
    print('Rendered two matching text carousels.')

if __name__=='__main__':main()
