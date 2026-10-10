"""Refresh the two existing Product Match explainers without fabricating UI."""
import json
from PIL import Image, ImageDraw, ImageFont
import render_selfie_batch as base

POSTS = {
    'W2_popular_vs_fit': (2, [
        'everyone loves it but does it suit your skin?',
        'reviews can help but everyone has different skin',
        'gloskin has a product match score based on your skin profile',
        'you can read why a product got that score too',
        'try checking a product you already own'
    ], 'Before you add another product to your shelf, check its match score in GloSkin. It uses your skin profile, and you can read the explanation behind the score.'),
    'W2_match_score_faq': (5, [
        'what does that product match score actually mean?',
        'it shows how a product fits your skin profile',
        'the explanation gives you more context than the number alone',
        "a high score doesn't guarantee it will work for you",
        'look up one of your products in gloskin'
    ], "GloSkin's product match score is a guide to how a product fits your skin profile. Read the explanation alongside the number. A match score isn't a guarantee of results.")
}

def main():
    entries = []
    for code, (person, copy, caption) in POSTS.items():
        folder = base.OUT/code
        for sub in ('slides', 'clean'):
            (folder/sub).mkdir(parents=True, exist_ok=True)
        slides, clean, records = [], [], []
        for idx, text in enumerate(copy):
            if idx in (0,4):
                plain = base.portrait_base(base.OUT/'assets'/f'person_{person}.png', idx)
                image, record = base.overlay(plain, text, True)
            else:
                plain = Image.new('RGB', (1080,1350), '#F4F4F4')
                image = plain.copy()
                font = ImageFont.truetype(base.FONT, 48)
                label = '\n'.join(base.lines_for(text, font, 800))
                draw = ImageDraw.Draw(image)
                box = draw.multiline_textbbox((0,0), label, font=font, spacing=15, align='center')
                x, y = (1080-box[2])/2, (1350-(box[3]-box[1]))/2-box[1]
                draw.multiline_text((x,y), label, font=font, spacing=15, align='center', fill='#252525')
                assert box[2] <= 800
                record = {'text':text, 'font_px':48}
            p, c = folder/'slides'/f'{idx+1:02d}.png', folder/'clean'/f'{idx+1:02d}.png'
            image.save(p)
            plain.save(c)
            slides.append(str(p)); clean.append(str(c)); records.append(record)
        caption += '\n\nFind GloSkin at gloskin.app\n\nAI generated portraits. Product match is guidance. Results vary.\n'
        for name in ['caption.txt','caption_instagram.txt']:
            (folder/name).write_text(caption, encoding='utf-8')
        (folder/'native_text.txt').write_text('\n\n'.join(f'Slide {i+1}\n{t}' for i,t in enumerate(copy)), encoding='utf-8')
        base.write_json(folder/'brief.json', {'slug':code, 'brand':'gloskin', 'slides':[{'kind':'hook' if i==0 else 'body','text':t} for i,t in enumerate(copy)], 'is_aigc':True, 'design_status':'approved_selfie_direction_2026_09_22', 'image_disclosure':None, 'ui_screenshot_status':'No Product Match screenshot supplied; this remains an explainer.'})
        base.write_json(folder/'text_fit.json', records)
        base.sheet(slides, folder/'contact_sheet.jpg', [str(i) for i in range(1,6)])
        entry = {'code':code,'source_post_id':None,'is_aigc':True,'folder':str(folder),'slides':slides,'clean_slides':clean,'video':str(folder/'video.mp4'),'preview':str(folder/'contact_sheet.jpg'),'validation':{'slide_count':5,'dimensions':[1080,1350],'text_bounds':'pass'}}
        entries.append(base.video(entry))
    base.write_json(base.OUT/'match_posts_index.json',entries)

if __name__ == '__main__':
    main()
