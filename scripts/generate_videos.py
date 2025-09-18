import os
import json
import openai
from gtts import gTTS
from moviepy.editor import (
    ColorClip, ImageClip, AudioFileClip,
    CompositeVideoClip, TextClip, concatenate_videoclips
)
from dotenv import load_dotenv
from pathlib import Path
import textwrap
import uuid
import time

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("Set OPENAI_API_KEY in env or GitHub Secrets")

openai.api_key = OPENAI_API_KEY

OUT_DIR = Path("outputs")
ASSETS_DIR = Path("assets")  # optional: put any stock short clips here, named clip1.mp4 etc.
OUT_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# ---- 1) Generate tech tips ----
def generate_tech_tips(num_tips=5):
    prompt = f"Generate {num_tips} short, punchy tech tips suitable for a 15-30 second Instagram Reel. Each tip should be 1-2 short sentences. Number them."
    resp = openai.ChatCompletion.create(
        model="gpt-4",  # or "gpt-4o" / "gpt-4o-mini" depending on your access
        messages=[{"role":"user", "content":prompt}],
        temperature=0.7,
        max_tokens=400
    )
    text = resp["choices"][0]["message"]["content"]
    # parse by lines containing "1." etc
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # if line starts with number or dash, remove numbering
        if line[0].isdigit() and (line[1] == '.' or line[1] == ')'):
            line = line.split('.',1)[1].strip() if '.' in line else line
        lines.append(line)
    # fallback: if single paragraph, split by sentences
    if len(lines) < num_tips:
        import re
        sentences = re.split(r'(?<=[.!?]) +', text)
        lines = [s.strip() for s in sentences if len(s.strip())>10][:num_tips]
    return lines[:num_tips]

# ---- 2) Create voice with gTTS ----
def create_voice(text, out_path):
    tts = gTTS(text=text, lang='en', slow=False)
    tts.save(str(out_path))

# ---- 3) Build a vertical clip (1080x1920) ----
def build_video(tip_text, output_path, duration=None, bg_color=(18,18,18), use_stock_clip=None):
    # create audio
    audio_file = output_path.with_suffix(".mp3")
    create_voice(tip_text, audio_file)
    audio = AudioFileClip(str(audio_file))
    aud_duration = audio.duration
    clip_duration = duration if duration else max(8, min(25, aud_duration + 0.5))

    W, H = 1080, 1920

    # background: if you have a matching stock clip, use it and resize/crop
    if use_stock_clip and Path(use_stock_clip).exists():
        from moviepy.editor import VideoFileClip
        bg = VideoFileClip(str(use_stock_clip)).resize(height=H).crop(x_center=0.5, width=W)
        bg = bg.subclip(0, min(clip_duration, bg.duration)).set_duration(clip_duration)
    else:
        # animate a simple color background (solid with slow zoom)
        bg = ColorClip(size=(W, H), color=bg_color, duration=clip_duration)
        bg = bg.set_fps(24)

    # create text overlay as multiple lines with wrapping
    wrapped = textwrap.fill(tip_text, width=25)
    # TextClip uses ImageMagick; if missing, fallback to ImageClip (PIL)
    txt_clip = (TextClip(wrapped, fontsize=70, font='Arial-Bold', color='white', method='caption', size=(int(W*0.9), None), align='center')
                .set_duration(clip_duration)
                .set_position(("center", H*0.25)))
    
    # small subtitle or CTA at bottom
    cta = TextClip("Follow for daily tech tips ➜ @yourhandle", fontsize=38, font='Arial', color='white', method='label')
    cta = cta.set_duration(clip_duration).set_position(("center", H*0.88)).margin(top=10, opacity=0)

    # optionally add a translucent rectangle behind text for readability (ImageClip)
    # Composite everything
    final = CompositeVideoClip([bg, txt_clip, cta], size=(W, H)).set_duration(clip_duration)
    final = final.set_audio(audio)
    # write
    final.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", threads=2, preset="medium", verbose=False, logger=None)

    # cleanup audio file (optional)
    try:
        audio.close()
    except:
        pass

# ---- main ----
if __name__ == "__main__":
    tips = generate_tech_tips(num_tips=5)
    results = []
    stock_candidates = sorted(ASSETS_DIR.glob("*.mp4"))
    for i, tip in enumerate(tips):
        name = f"tech_tip_{int(time.time())}_{i+1}.mp4"
        out_path = OUT_DIR / name
        stock = str(stock_candidates[i % len(stock_candidates)]) if stock_candidates else None
        print("Generating:", tip)
        build_video(tip, out_path, use_stock_clip=stock)
        results.append({"tip": tip, "file": str(out_path)})
        time.sleep(1)

    # save log
    with open(OUT_DIR / "videos_log.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Done. Videos in outputs/")
