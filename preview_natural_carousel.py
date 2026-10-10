"""One follow-up design sample: clearer portrait first and conversational copy."""
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw
import carousel_design_preview as design

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/design_review_natural_copy/C1'

def right_note(image,text,dark=False):
    # On portraits use the pale upper-right backdrop, away from the headline.
    # On neutral slides use the lower-right margin. No badge or opaque box.
    draw=ImageDraw.Draw(image)
    y=113 if dark else 1286
    for i,line in enumerate(['AI generated example','Not a customer result']):
        draw.text((1026,y+i*27),line,font=design.font(22),fill='#5D5B62',anchor='ra')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    brief=json.loads((ROOT/'output/approved_design_2026-09-21/C1/brief.json').read_text(encoding='utf-8'))
    brief['slug']='C1_natural_copy_preview'
    brief['design_status']='followup_preview_pending_user_review'
    brief['slides'][0]['image']=brief['slides'][3]['image']
    new_copy=[
        'Curious what your skin scan would show?',
        'Take a selfie to see your Glo Score.',
        'You can compare your scans over time.',
        'Come back whenever you want to check in.',
        'Want to see yours?'
    ]
    design.footer=right_note
    for idx,slide in enumerate(brief['slides']):
        slide['caption' if slide['kind']=='screenshot' else 'text']=new_copy[idx]
        slide['disclosure']='AI generated example. Not a customer result.'
        slide['disclosure_footer']=slide['disclosure']
        slide.pop('disclosure_chip',None)
        if idx==3:slide.pop('subtext',None)
        render=design.portrait if slide.get('layout')=='image_top' else design.screenshot if slide['kind']=='screenshot' else design.cta
        im=render(slide,idx)
        im.save(OUT/f'slide_{idx+1:02d}.png')
    brief['factual_claims']=[new_copy[0]]
    (OUT/'brief.json').write_text(json.dumps(brief,indent=2),encoding='utf-8')
    caption=("Curious what your skin scan would show?\n\n"
             "Take a selfie in GloSkin to see your Glo Score. You can come back and compare your scans over time.\n\n"
             "AI generated images and sample scores. These are illustrative examples, not actual customer results.\n\n"
             "Results vary. Not medical advice.\n\n"
             "Find GloSkin at gloskin.app\n")
    (OUT/'caption_instagram.txt').write_text(caption,encoding='utf-8')
    sheet=Image.new('RGB',(1800,480),'white')
    pair=Image.new('RGB',(1096,675),'white')
    for idx in range(5):
        im=Image.open(OUT/f'slide_{idx+1:02d}.png')
        if idx<2:pair.paste(im.resize((540,675),Image.Resampling.LANCZOS),(556*idx,0))
        im.thumbnail((360,450),Image.Resampling.LANCZOS)
        sheet.paste(im,(idx*360,30))
        ImageDraw.Draw(sheet).text((idx*360+10,7),f'{idx+1:02d}',font=design.font(18),fill=design.INK)
    sheet.save(OUT/'contact_sheet.jpg',quality=94)
    pair.save(OUT/'cover_and_phone.jpg',quality=95)
    subprocess.run(['ffmpeg','-v','error','-y','-framerate','1/3.5','-i',str(OUT/'slide_%02d.png'),
                    '-vf','fps=30','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'preview.mp4')],check=True)
    print(OUT)

if __name__=='__main__':main()
