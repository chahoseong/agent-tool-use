"""Render official success rates from the saved chart aggregate."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
rows = json.loads((ROOT / "artifacts/published/chart-data.json").read_text("utf-8"))[
    "rows"
]
im = Image.new("RGB", (1600, 770), "white")
draw = ImageDraw.Draw(im)
INK = "#182638"
MUTED = "#586678"
COLORS = ["#8496a8", "#166a9c"]


def text(x, y, value, size=24, color=INK, bold=False, anchor=None):
    font = ImageFont.truetype(
        "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf", size
    )
    draw.text((x, y), value, font=font, fill=color, anchor=anchor)


text(800, 38, "공식 채점 · Task 성공률", 38, bold=True, anchor="mt")
for x, label, color in [
    (590, "Baseline", COLORS[0]),
    (820, "프롬프트 개선", COLORS[1]),
]:
    draw.rectangle((x, 110, x + 26, 136), fill=color)
    text(x + 40, 104, label, 23)

left, right, top, bottom = 170, 1450, 235, 670
for count in range(4):
    y = bottom - (bottom - top) * count / 3
    draw.line((left, y, right, y), fill="#e3e8ee", width=2)
    label = f"{count * 100 / 3:.1f}%" if count in (1, 2) else f"{count * 100 // 3}%"
    text(left - 24, y, label, 24, MUTED, anchor="rm")
draw.line((left, top, left, bottom), fill="#8b97a5", width=2)
draw.line((left, bottom, right, bottom), fill="#8b97a5", width=2)

tasks = list(dict.fromkeys(row["task"] for row in rows))
for index, task in enumerate(tasks):
    center = left + (index + 0.5) * (right - left) / len(tasks)
    pair = [row for row in rows if row["task"] == task]
    assert [row["variant"] for row in pair] == ["Baseline", "프롬프트 개선"]
    for j, row in enumerate(pair):
        assert row["count"] == 3 and 0 <= row["official_pass"] <= row["count"]
        source = json.loads((ROOT / row["source"] / "results.json").read_text("utf-8"))
        assert len(source["simulations"]) == row["count"]
        assert (
            sum(s["reward_info"]["reward"] == 1 for s in source["simulations"])
            == row["official_pass"]
        )
        x = center + (-48 if j == 0 else 48)
        y = bottom - (bottom - top) * row["official_pass"] / row["count"]
        if row["official_pass"]:
            draw.rectangle((x - 40, y, x + 40, bottom - 1), fill=COLORS[j])
        else:
            draw.line((x - 40, bottom, x + 40, bottom), fill=COLORS[j], width=3)
        text(
            x,
            y - 17,
            f"{row['official_pass']}/{row['count']}",
            28,
            bold=True,
            anchor="mb",
        )
    text(center, bottom + 28, task, 27, bold=True, anchor="mt")

output = ROOT / "docs/assets/charts/official-results.png"
output.parent.mkdir(parents=True, exist_ok=True)
im.save(output)
print(output)
