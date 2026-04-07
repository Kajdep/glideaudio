from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
STORE_DIR = ROOT / "assets" / "store"

COLORS = {
    "bg": "#050505",
    "surface": "#151515",
    "surface_alt": "#202020",
    "border": "#2D2118",
    "primary": "#D86B21",
    "primary_soft": "#FFB36B",
    "text": "#F5EFE6",
    "text_secondary": "#B59C84",
    "track": "#24170F",
}


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Users/kajal/AppData/Local/Microsoft/Windows/Fonts/SpaceGrotesk-VariableFont_wght.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_wave(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], *, color: str) -> None:
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    mid = top + height // 2
    step = max(8, width // 18)
    bars = [0.16, 0.32, 0.56, 0.82, 0.46, 0.92, 0.64, 0.36, 0.72, 0.28, 0.66, 0.18]
    for index, strength in enumerate(bars):
        x = left + index * step
        bar_height = int(height * strength)
        draw.rounded_rectangle(
            (x, mid - bar_height // 2, x + step // 2, mid + bar_height // 2),
            radius=max(3, step // 6),
            fill=color,
        )


def build_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), COLORS["bg"])
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    margin = int(size * 0.12)
    glow_draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=int(size * 0.18),
        outline=COLORS["primary"],
        width=max(10, size // 24),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=max(6, size // 38)))
    image.alpha_composite(glow)

    draw = ImageDraw.Draw(image)
    panel = (margin, margin, size - margin, size - margin)
    draw.rounded_rectangle(panel, radius=int(size * 0.18), fill=COLORS["surface"], outline=COLORS["primary"], width=max(6, size // 42))

    inner = int(size * 0.18)
    draw_wave(draw, (inner, inner + size // 10, size - inner, size - inner // 2), color=COLORS["primary_soft"])

    label_font = load_font(max(36, size // 8), bold=True)
    label = "GA"
    text_bbox = draw.textbbox((0, 0), label, font=label_font)
    text_width = text_bbox[2] - text_bbox[0]
    draw.text(
        ((size - text_width) / 2, size * 0.70),
        label,
        font=label_font,
        fill=COLORS["text"],
    )
    return image


def build_store_hero(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, COLORS["bg"])
    draw = ImageDraw.Draw(image)

    for offset in range(0, height, 80):
        alpha = int(20 + (offset / max(1, height)) * 55)
        draw.rectangle((0, offset, width, min(height, offset + 60)), fill=(36, 23, 15, alpha))

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((width * 0.52, height * 0.18, width * 0.98, height * 0.82), fill=(216, 107, 33, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=72))
    image.alpha_composite(glow)

    panel = (70, 80, width - 70, height - 80)
    draw.rounded_rectangle(panel, radius=42, fill=COLORS["surface"], outline=COLORS["border"], width=3)

    draw_wave(draw, (120, 210, width - 130, 430), color=COLORS["primary"])

    title_font = load_font(84, bold=True)
    subtitle_font = load_font(34, bold=False)
    body_font = load_font(24, bold=False)

    draw.text((120, 480), "GlideAudio", font=title_font, fill=COLORS["text"])
    draw.text((120, 575), "Repair spoken audio fast.", font=subtitle_font, fill=COLORS["primary_soft"])
    draw.text(
        (120, 630),
        "Analyze, audition, batch render, and export locally without a full DAW workflow.",
        font=body_font,
        fill=COLORS["text_secondary"],
    )

    chip_font = load_font(22, bold=True)
    chip_y = 720
    chips = ["A/B Preview", "Batch Queue", "Repaired Video", "Local-First"]
    chip_x = 120
    for chip in chips:
        bbox = draw.textbbox((0, 0), chip, font=chip_font)
        chip_width = bbox[2] - bbox[0] + 28
        draw.rounded_rectangle((chip_x, chip_y, chip_x + chip_width, chip_y + 44), radius=18, fill=COLORS["track"])
        draw.text((chip_x + 14, chip_y + 9), chip, font=chip_font, fill=COLORS["text"])
        chip_x += chip_width + 14

    return image


def build_wordmark(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, COLORS["bg"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 30, size[0] - 30, size[1] - 30), radius=42, fill=COLORS["surface"], outline=COLORS["border"], width=3)
    draw_wave(draw, (90, 90, size[0] - 90, 250), color=COLORS["primary"])
    title_font = load_font(72, bold=True)
    subtitle_font = load_font(26, bold=False)
    draw.text((90, 280), "GlideAudio", font=title_font, fill=COLORS["text"])
    draw.text((90, 370), "Clean spoken audio without the DAW drag.", font=subtitle_font, fill=COLORS["text_secondary"])
    return image


def save_ico(image: Image.Image, target: Path) -> None:
    image.save(target, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


def main() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    icon = build_icon(1024)
    save_ico(icon, ROOT / "glideaudio.ico")
    icon.save(ROOT / "glideaudio-logo.png")

    build_wordmark((1200, 675)).save(STORE_DIR / "glideaudio-cover.png")
    build_store_hero((1600, 900)).save(STORE_DIR / "glideaudio-store-hero.png")
    build_icon(768).save(STORE_DIR / "glideaudio-store-square.png")

    print("Wrote branding assets:")
    print(ROOT / "glideaudio.ico")
    print(ROOT / "glideaudio-logo.png")
    print(STORE_DIR / "glideaudio-cover.png")
    print(STORE_DIR / "glideaudio-store-hero.png")
    print(STORE_DIR / "glideaudio-store-square.png")


if __name__ == "__main__":
    main()
