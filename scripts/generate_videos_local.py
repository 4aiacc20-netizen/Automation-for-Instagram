#!/usr/bin/env python3
import os
import json
import textwrap
import uuid
import time
from pathlib import Path
from dotenv import load_dotenv
from gtts import gTTS
from moviepy.editor import (
    ColorClip, ImageClip, AudioFileClip,
    CompositeVideoClip, VideoFileClip
)
from PIL import Image, ImageDraw, ImageFont

# --- NEW: modern OpenAI client ---
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("Set OPENAI_API_KEY in env or GitHub Secrets")

# instantiate the new client
client = OpenAI(api_key=OPENAI_API_KEY)

OUT_DIR = Path("outputs")
ASSETS_DIR = Path("assets")  # optional
OUT_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)

# ---- 1) Generate tech tips (uses new client.chat.completions.create) ----
def generate_tech_tips(num_tips=5):
    prompt = f"Generate {num_tips} short, punchy tech tips suitable for a 15-30 second Instagram Reel. Each tip should be 1-2 short sentences. Number them."
    # Use the new client API
    resp = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    # parse response text (choice -> message -> content)
    # this matches the new client response shape: resp.choices[0].message.content
    try:
        text = resp.choices[0].message.content
    except Exception:
        # fallback: try dictionary-style access if packaging returns dicts
        text = resp["choices"][0]["message"]["content"]

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # remove leading numbering like "1." or "1)"
        if len(line) > 1 and line[0].isdigit() and (line[1] in ['.', ')']):
            # strip the numbering (first occurrence of '.' or ')')
            idx = 1
            while idx < len(line) and line[idx] not in ['.', ')']:
                idx += 1
            line = line[idx+1:].strip() if idx < len(line) else line
        lines.append(line)
    # fallback: if response is a paragraph, split into sentences
    if len(lines) < num_tips:
        import re
        sentences = re.split(r'(?<=[.!?]) +', text)
        lines = [s.strip() for s in sentences if len(s.strip()) > 10][:num_tips]
    return lines[:num_tips]

# ---- 2) Create voice with gTTS ----
def create_voice(text, out_path):
    tts = gTTS(text=text, lang='en', slow=False)
    tts.save(str(out_path))

# ---- 3) Create text image with PIL and return ImageClip ----
def create_text_image_clip(text, w=1080, h=1920, fontsize=72, duration=8):
    wrapped = textwrap.fill(text, width=24)
    img = Image.new("RGBA", (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", fontsize)
    except Exception:
        font = ImageFont.load_default()
    lines = wrapped.split("\n")
    # approximate line height
    line_h = font.getsize("Ay")[1] + 10
    y_text = int(h * 0.20)
    for line in lines:
        w_text, _ = draw.textsize(line, font=font)
        x_text = (w - w_text) // 2
        draw.text((x_text, y_text), line, font=font, fill=(255,255,255,255))
        y_text += line_h
    cta = "Follow for daily tech tips ➜ @yourhandle"
    w_cta, _ = draw.textsize(cta, font=font)
    draw.text(((w - w_cta)//2, int(h*0.88)), cta, font=font, fill=(230,230,230,255))
    tmp = OUT_DIR / f"text_{uuid.uuid4().hex}.png"
    img.save(tmp)
    clip = ImageClip(str(tmp)).set_duration(duration)
    return clip, tmp

# ---- 4) Build vertical video (1080x1920) ----
def build_video(tip_text, output_path, duration=None, bg_color=(18,18,18), use_stock_clip=None):
    audio_file = output_path.with_suffix(".mp3")
    create_voice(tip_text, audio_file)
    audio = AudioFileClip(str(audio_file))
    aud_duration = audio.duration
    clip_duration = duration if duration else max(8, min(25, aud_duration + 0.5))
    W, H = 1080, 1920

    # background: stock clip or solid color
    if use_stock_clip and Path(use_stock_clip).exists():
        try:
            bg = VideoFileClip(str(use_stock_clip)).resize(height=H)
            if bg.w > W:
                bg = bg.crop(width=W, height=H, x_center=bg.w/2, y_center=bg.h/2)
            bg = bg.subclip(0, min(clip_duration, bg.duration)).set_duration(clip_duration)
        except Exception:
            bg = ColorClip(size=(W, H), color=bg_color, duration=clip_duration)
    else:
        bg = ColorClip(size=(W, H), color=bg_color, duration=clip_duration)

    txt_clip, tmp_img = create_text_image_clip(tip_text, w=W, h=H, fontsize=72, duration=clip_duration)
    txt_clip = txt_clip.set_position(("center","center"))

    final = CompositeVideoClip([bg, txt_clip], size=(W, H)).set_duration(clip_duration)
    final = final.set_audio(audio)

    final.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", threads=2, preset="medium", verbose=False, logger=None)

    try:
        audio.close()
    except:
        pass
    try:
        tmp_img.unlink()
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

    with open(OUT_DIR / "videos_log.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Done. Videos in outputs/")
