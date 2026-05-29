#!/usr/bin/env python3
"""Render conversion-focused App Store screenshots from raw app captures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DISPLAY_SIZES = {
    "APP_IPHONE_67": (1320, 2868),
    "APP_IPHONE_65": (1284, 2778),
    "APP_IPHONE_61": (1206, 2622),
    "APP_IPAD_PRO_3GEN_129": (2048, 2732),
    "APP_IPAD_PRO_3GEN_11": (1668, 2388),
    "APP_DESKTOP": (2880, 1800),
}


def load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:  # pragma: no cover - exercised only without Pillow
        raise SystemExit(
            "Pillow is required for rendering screenshots. Install it with: "
            "python3 -m pip install pillow"
        ) from exc
    return Image, ImageDraw, ImageFont


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as file:
        return json.load(file)


def hex_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB color, got {value}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def font(size: int, bold: bool = False):
    _, _, ImageFont = load_pillow()
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def wrap_text(draw: Any, text: str, font_obj: Any, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font_obj)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def rounded_rectangle(draw: Any, box: tuple[int, int, int, int], radius: int, fill: Any, outline: Any = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_pill(
    draw: Any,
    x: int,
    y: int,
    text: str,
    font_obj: Any,
    fill: tuple[int, int, int],
    text_color: tuple[int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font_obj)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    box = (x, y, x + text_width + width * 2, y + text_height + height * 2)
    rounded_rectangle(draw, box, radius=max(22, (box[3] - box[1]) // 2), fill=fill)
    draw.text((box[0] + width, box[1] + height - 2), text, font=font_obj, fill=text_color)
    return box


def render_one(config: dict[str, Any], screen: dict[str, Any], output_dir: Path) -> Path:
    Image, ImageDraw, _ = load_pillow()
    display_type = screen.get("displayType") or config.get("displayType", "APP_IPHONE_67")
    width, height = DISPLAY_SIZES.get(display_type, DISPLAY_SIZES["APP_IPHONE_67"])
    background = hex_color(screen.get("background") or config.get("background", "#F5F7FA"))
    accent = hex_color(screen.get("accent") or config.get("accent", "#0A84FF"))
    text_color = hex_color(screen.get("textColor") or config.get("textColor", "#111827"))
    muted_color = hex_color(screen.get("mutedColor") or config.get("mutedColor", "#4B5563"))
    cta_text_color = hex_color(screen.get("ctaTextColor") or config.get("ctaTextColor", "#FFFFFF"))

    canvas = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(canvas)

    margin = int(width * 0.08)
    top = int(height * 0.07)
    max_text_width = width - margin * 2

    headline_font = font(max(54, int(width * 0.075)), bold=True)
    sub_font = font(max(34, int(width * 0.036)))
    badge_font = font(max(26, int(width * 0.032)), bold=True)
    cta_font = font(max(28, int(width * 0.034)), bold=True)

    y = top
    for line in wrap_text(draw, screen["headline"], headline_font, max_text_width):
        draw.text((margin, y), line, font=headline_font, fill=text_color)
        y += int(headline_font.size * 1.12)
    y += int(height * 0.012)
    for line in wrap_text(draw, screen.get("subheadline", ""), sub_font, max_text_width):
        draw.text((margin, y), line, font=sub_font, fill=muted_color)
        y += int(sub_font.size * 1.35)

    if screen.get("cta"):
        y += int(height * 0.018)
        cta_box = draw_pill(
            draw,
            margin,
            y,
            screen["cta"],
            cta_font,
            accent,
            cta_text_color,
            int(width * 0.028),
            int(height * 0.009),
        )
        y = cta_box[3]

    if screen.get("paid"):
        badge = screen.get("paidBadge") or config.get("paidBadge", "Pro")
        badge_text = f"{badge} feature"
        y += int(height * 0.014)
        draw_pill(
            draw,
            margin,
            y,
            badge_text,
            badge_font,
            accent,
            cta_text_color,
            int(width * 0.025),
            int(height * 0.008),
        )

    source = Path(screen["source"]).expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    capture = Image.open(source).convert("RGB")

    phone_top = int(height * float(screen.get("phoneTopRatio") or config.get("phoneTopRatio", 0.34)))
    phone_width = int(width * float(screen.get("phoneWidthRatio") or config.get("phoneWidthRatio", 0.72)))
    phone_height = min(int(height * 0.60), int(phone_width * capture.height / capture.width) + 80)
    phone_left = (width - phone_width) // 2
    phone_box = (phone_left, phone_top, phone_left + phone_width, phone_top + phone_height)
    shadow = (0, 0, 0)
    rounded_rectangle(
        draw,
        (phone_box[0] + 18, phone_box[1] + 22, phone_box[2] + 18, phone_box[3] + 22),
        radius=58,
        fill=tuple(max(0, channel - 20) for channel in background),
    )
    rounded_rectangle(draw, phone_box, radius=58, fill=(20, 24, 31), outline=shadow, width=3)
    inset = 30
    screen_box = (phone_box[0] + inset, phone_box[1] + inset, phone_box[2] - inset, phone_box[3] - inset)
    available_w = screen_box[2] - screen_box[0]
    available_h = screen_box[3] - screen_box[1]
    capture.thumbnail((available_w, available_h))
    paste_x = screen_box[0] + (available_w - capture.width) // 2
    paste_y = screen_box[1] + (available_h - capture.height) // 2
    canvas.paste(capture, (paste_x, paste_y))

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / screen.get("output", source.name)
    canvas.save(out)
    return out


def render(config_path: str | Path) -> dict[str, Any]:
    config_path = Path(config_path).expanduser()
    config = load_json(config_path)
    output_dir = Path(config.get("outputDir", "generated-screenshots")).expanduser()
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    outputs = [str(render_one(config, screen, output_dir)) for screen in config.get("screens", [])]
    return {"outputDir": str(output_dir), "files": outputs}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to screenshot-template JSON.")
    args = parser.parse_args(argv)
    result = render(args.config)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
