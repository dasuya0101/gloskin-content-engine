"""Render one opt-in design preview; leaves the production renderer untouched."""
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1350
OUT = ROOT / 'output' / 'design_review_2026-09-21' / 'C1'
BACKGROUND = '#F5F3F6'
INK = '#201C27'
ACCENT = '#773CED'

def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf', size)

def wrap(text, face, width):
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).strip()
            if line and measure.textlength(candidate, font=face) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return lines

def text_block(image, text, size, cy, color=INK, width=900, bold=True):
    draw = ImageDraw.Draw(image)
    face = font(size, bold)
    lines = wrap(text, face, width)
    step = round(size * 1.20)
    top = cy - (len(lines)-1)*step/2
    for idx, line in enumerate(lines):
        draw.text((W/2, top+idx*step), line, font=face, fill=color, anchor='mm')
    return len(lines)*step

def chrome(image, idx, dark=False):
    draw = ImageDraw.Draw(image)
    color = '#FFFFFF' if dark else ACCENT
    draw.text((54, 50), 'GloSkin', font=font(30, True), fill=color,
              stroke_width=1 if dark else 0, stroke_fill='#504952')
    for n in range(5):
        x=924+n*22
        draw.ellipse((x-4,65-4,x+4,65+4),fill=color if n==idx else ('#D6D0D7' if dark else '#CEC7D4'))

def footer(image, text, dark=False):
    ImageDraw.Draw(image).text((W/2,H-27),text,font=font(24),
                              fill='#BEB9C5' if dark else '#756F7C',anchor='mm')

def portrait(slide, idx):
    photo=Image.open(slide['image']).convert('RGB')
    # Use the whole canvas for the face, instead of a 58% photo panel.
    base=ImageOps.fit(photo,(W,H),method=Image.Resampling.LANCZOS,centering=(.5,.34))
    # A continuous fade into a compact dark text area; no separate pink block.
    mask=Image.new('L',(1,H))
    values=[]
    for y in range(H):
        t=max(0,min(1,(y-855)/405))
        eased=t*t*(3-2*t)
        values.append(round(255*eased))
    mask.putdata(values)
    base=Image.composite(Image.new('RGB',(W,H),'#1B1822'),base,mask.resize((W,H)))
    chrome(base,idx,dark=True)
    text_block(base,slide['text'],58,1175,color='#FFFFFF',width=900)
    if slide.get('subtext'):
        text_block(base,slide['subtext'],27,1257,color='#DDD8E3',bold=False)
    footer(base,slide['disclosure'],dark=True)
    return base

def iphone_frame(screen):
    # Keep the capture's actual iPhone aspect ratio and existing Dynamic Island.
    # Thin graphite rim, one black bezel, no repeated thick concentric borders.
    screen=screen.convert('RGB')
    screen.thumbnail((500,990),Image.Resampling.LANCZOS)
    sw,sh=screen.size
    bezel=10
    width,height=sw+2*bezel,sh+2*bezel
    device=Image.new('RGBA',(width+6,height),(0,0,0,0))
    draw=ImageDraw.Draw(device)
    radius=round(width*.135)
    draw.rounded_rectangle((3,0,width+2,height-1),radius=radius,
                           fill='#111113',outline='#626267',width=2)
    draw.rounded_rectangle((0,155,4,183),radius=2,fill='#343438')
    draw.rounded_rectangle((0,211,4,261),radius=2,fill='#343438')
    draw.rounded_rectangle((0,278,4,328),radius=2,fill='#343438')
    draw.rounded_rectangle((width+1,224,width+5,316),radius=2,fill='#343438')
    mask=Image.new('L',(sw,sh),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,sw-1,sh-1),radius=radius-bezel,fill=255)
    device.paste(screen,(3+bezel,bezel),mask)
    return device

def screenshot(slide,idx):
    base=Image.new('RGBA',(W,H),BACKGROUND)
    chrome(base,idx)
    text_block(base,slide['caption'],48,157,width=850)
    device=iphone_frame(Image.open(slide['image']))
    x,y=(W-device.width)//2,250
    shadow=Image.new('RGBA',(W,H),(0,0,0,0))
    ImageDraw.Draw(shadow).rounded_rectangle((x+8,y+19,x+device.width-8,y+device.height+17),
                                             radius=60,fill=(18,16,22,56))
    base=Image.alpha_composite(base,shadow.filter(ImageFilter.GaussianBlur(22)))
    base.alpha_composite(device,(x,y))
    footer(base,slide['disclosure'])
    return base.convert('RGB')

def cta(slide,idx):
    base=Image.new('RGB',(W,H),BACKGROUND)
    chrome(base,idx)
    text_block(base,slide['text'],72,590,width=850)
    draw=ImageDraw.Draw(base)
    draw.rounded_rectangle((320,755,760,847),radius=46,fill=ACCENT)
    draw.text((540,800),slide['button'],font=font(37,True),fill='white',anchor='mm')
    text_block(base,slide['subtext'],29,900,bold=False,color='#756F7C')
    footer(base,slide['disclosure'])
    return base

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    brief=json.loads((ROOT/'output/gloskin_september_11_revisions/C1_revised/brief.json').read_text(encoding='utf-8'))
    brief['slug']='C1_design_preview_2026_09_21'
    brief['design_status']='one_carousel_awaiting_user_approval'
    for idx,slide in enumerate(brief['slides']):
        slide.pop('disclosure_chip',None)
        im=portrait(slide,idx) if slide.get('layout')=='image_top' else screenshot(slide,idx) if slide['kind']=='screenshot' else cta(slide,idx)
        im.save(OUT/f'slide_{idx+1:02d}.png')
    (OUT/'brief.json').write_text(json.dumps(brief,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'output/gloskin_september_11_revisions/C1_revised/caption.txt',OUT/'caption.txt')
    # Review sheet is a viewing aid; the five originals remain full resolution.
    sheet=Image.new('RGB',(1800,480),'white')
    for idx in range(5):
        im=Image.open(OUT/f'slide_{idx+1:02d}.png')
        im.thumbnail((360,450),Image.Resampling.LANCZOS)
        sheet.paste(im,(360*idx,30))
        ImageDraw.Draw(sheet).text((360*idx+12,7),f'{idx+1:02d}',font=font(18),fill=INK)
    sheet.save(OUT/'contact_sheet.jpg',quality=94)
    pair=Image.new('RGB',(1096,675),'#FFFFFF')
    for idx in range(2):
        im=Image.open(OUT/f'slide_{idx+1:02d}.png')
        im=im.resize((540,675),Image.Resampling.LANCZOS)
        pair.paste(im,(556*idx,0))
    pair.save(OUT/'cover_and_phone.jpg',quality=95)
    subprocess.run(['ffmpeg','-v','error','-y','-framerate','1/3.5','-i',str(OUT/'slide_%02d.png'),
                    '-vf','fps=30','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',
                    str(OUT/'preview.mp4')],check=True)
    print(OUT)

if __name__=='__main__':main()
