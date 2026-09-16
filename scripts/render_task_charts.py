"""Render all task charts, or one with --task 'airline 42'."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/published/chart-data.json"
OUTPUT = ROOT / "docs/assets/charts"
INK = "#182638"
MUTED = "#586678"
COLORS = {"pass": "#177b91", "fail": "#c76032", "unknown": "#8063ae", "-": "#d9dfe7"}
KEYS = ["retrieval", "proposals", "consent", "side_effects", "guidance"]
LABELS = ["조회 근거", "제안 적절성", "사용자 동의", "요청·정책 준수", "안내 정확성"]


def render(task, rows, output):
    pair = [row for row in rows if row["task"] == task]
    assert [row["variant"] for row in pair] == ["Baseline", "프롬프트 개선"]
    im = Image.new("RGB", (1600, 770), "white")
    draw = ImageDraw.Draw(im)

    def text(x, y, value, size=24, color=INK, bold=False, anchor=None):
        font = ImageFont.truetype(
            "C:/Windows/Fonts/malgunbd.ttf" if bold else "C:/Windows/Fonts/malgun.ttf",
            size,
        )
        draw.text((x, y), value, font=font, fill=color, anchor=anchor)

    def bar_segment(bounds, color, hatched=False):
        x0, y0, x1, y1 = map(round, bounds)
        segment = Image.new("RGB", (x1 - x0 + 1, y1 - y0 + 1), color)
        if hatched:
            lines = ImageDraw.Draw(segment)
            rgb = ImageColor.getrgb(color)
            target = 95 if color == COLORS["-"] else 255
            stripe = tuple(round(channel * 0.65 + target * 0.35) for channel in rgb)
            width, height = segment.size
            for offset in range(-height, width, 16):
                lines.line((offset, height, offset + height, 0), fill=stripe, width=2)
        im.paste(segment, (x0, y0))

    text(800, 38, f"{task} · 추가 채점 판정 분포", 38, bold=True, anchor="mt")
    legend = [
        (key, label)
        for key, label in [
            ("pass", "통과"),
            ("fail", "실패"),
            ("unknown", "판단 불가"),
            ("-", "해당 없음(N/A)"),
        ]
        if any(
            row["metrics"][metric].get(key, 0) > 0 for row in pair for metric in KEYS
        )
    ]
    left, right, top, bottom = 115, 1320, 190, 670
    legend_top = (top + bottom) / 2 - (len(legend) - 1) * 28
    for index, (key, label) in enumerate(legend):
        y = legend_top + index * 56
        draw.rectangle((1360, y - 11, 1382, y + 11), fill=COLORS[key])
        text(1394, y, label, 23, anchor="lm")

    bar_segment((507, 110, 543, 133), COLORS["-"], hatched=True)
    text(555, 104, "Baseline", 23)
    bar_segment((737, 110, 773, 133), COLORS["-"])
    text(785, 104, "프롬프트 개선", 23)

    text(left, 144, "실행 수", 23, MUTED)
    for count in range(4):
        y = bottom - count * 160
        draw.line((left, y, right, y), fill="#e3e8ee", width=2)
        text(left - 20, y, str(count), 24, MUTED, anchor="rm")
    draw.line((left, top, left, bottom), fill="#8b97a5", width=2)
    draw.line((left, bottom, right, bottom), fill="#8b97a5", width=2)

    for k, (key, label) in enumerate(zip(KEYS, LABELS)):
        center = left + (k + 0.5) * (right - left) / len(KEYS)
        for j, row in enumerate(pair):
            counts = row["metrics"][key]
            assert row["count"] == 3 and sum(counts.values()) == 3
            assert set(counts) <= set(COLORS)
            assert all(isinstance(n, int) and n >= 0 for n in counts.values())
            x = center + (-46 if j == 0 else 46)
            y = bottom
            for verdict, color in COLORS.items():
                n = counts.get(verdict, 0)
                if n:
                    end = y - n * 160
                    bar_segment((x - 40, end, x + 40, y - 1), color, hatched=j == 0)
                    if j == 0:
                        middle = (y + end) / 2
                        draw.rectangle(
                            (x - 15, middle - 21, x + 15, middle + 21), fill=color
                        )
                    text(
                        x,
                        (y + end) / 2,
                        str(n),
                        30,
                        INK if verdict == "-" else "white",
                        True,
                        anchor="mm",
                    )
                    y = end
        text(center, bottom + 28, label, 27, bold=True, anchor="mt")

    output.mkdir(parents=True, exist_ok=True)
    path = output / f"judge-stacked-{task.replace(' ', '-')}.png"
    im.save(path)
    print(path)


def main():
    rows = json.loads(SOURCE.read_text("utf-8"))["rows"]
    tasks = list(dict.fromkeys(row["task"] for row in rows))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=tasks, help="Generate only this task")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    for task in [args.task] if args.task else tasks:
        render(task, rows, args.output_dir)


if __name__ == "__main__":
    main()
