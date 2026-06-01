#!/usr/bin/env python3
"""把图像生成产出的「4 帧像素小人」长条统一裁切并拼成对齐的 sprite sheet。

输入：static/images/mat_pixel/src/<name>_strip.png
    每张图横向排布约 4 帧同一角色的工作循环动作，帧间用透明间隔分开，
    但帧的位置/大小并不严格对齐（扩散模型输出的固有问题）。

输出：static/images/mat_pixel/<name>_sheet.png
    固定网格：CELL x CELL 的方格，横向 FRAMES 帧。每帧裁出角色的不透明
    包围盒，底部对齐（脚踩在同一水平线），按「脚部中心」水平居中，
    从而让动作变化（抬锤/挥手/浇水）来自角色本身，而不是整体抖动。

用法：
    .venv/bin/python scripts/gen_mat_pixel_sprites.py
"""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "images" / "mat_pixel"
SRC_DIR = OUT_DIR / "src"

NAMES = [
    "idle",
    "scout",
    "drafter",
    "builder",
    "gardener",
    "inspector",
    "packer",
    "celebrate",
]

FRAMES = 4
CELL = 240          # 每帧方格边长（像素）
MARGIN = 14         # 角色与方格边缘的安全边距
ALPHA_CUTOFF = 40   # 低于此 alpha 视为透明（去掉淡边/噪点）


def dechecker(img: Image.Image) -> Image.Image:
    """去掉「假透明」棋盘格背景。

    图像生成器经常把透明背景画成真实的灰/白棋盘格像素（alpha=255），
    在深色场景上就成了马赛克。这里从四条边界做洪泛填充：把与边界连通、
    且「接近灰阶且偏亮」的像素（棋盘格的白格 + 浅灰格）抹成全透明。
    角色和脚下的灰色积木都被自身的深色描边包住，洪泛到不了，因此被保护。
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    def is_bg(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        if a < 8:
            return True  # 已透明（帧间空隙），可继续蔓延
        mx = max(r, g, b)
        mn = min(r, g, b)
        return mx > 170 and (mx - mn) < 32  # 近灰阶且偏亮 = 棋盘格

    visited = bytearray(w * h)
    dq: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        i = y * w + x
        if not visited[i] and is_bg(x, y):
            visited[i] = 1
            dq.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while dq:
        x, y = dq.popleft()
        r, g, b, a = px[x, y]
        if a != 0:
            px[x, y] = (r, g, b, 0)
        if x + 1 < w: seed(x + 1, y)
        if x - 1 >= 0: seed(x - 1, y)
        if y + 1 < h: seed(x, y + 1)
        if y - 1 >= 0: seed(x, y - 1)

    return img


def cleaned_alpha(img: Image.Image) -> Image.Image:
    """返回经阈值处理的 alpha 通道（L 模式），用于稳健地求包围盒。"""
    alpha = img.split()[-1]
    return alpha.point(lambda a: 255 if a >= ALPHA_CUTOFF else 0)


def feet_center_x(crop: Image.Image) -> int:
    """估计「脚部/身体」水平中心。

    用底部 45% 区域的 alpha 质心（而非包围盒边界）：腿部像素质量大，
    侧面的小道具（积木、放大镜）只贡献少量质量，因此质心在各帧间更稳定，
    可避免角色在循环里左右滑动。
    """
    w, h = crop.size
    mask = cleaned_alpha(crop).load()
    band_top = int(h * 0.55)
    total = 0
    weighted = 0
    for y in range(band_top, h):
        for x in range(w):
            if mask[x, y]:
                total += 1
                weighted += x
    if total == 0:
        return w // 2
    return weighted // total


def build_sheet(name: str) -> None:
    src_path = SRC_DIR / f"{name}_strip.png"
    if not src_path.exists():
        print(f"  [skip] 缺少源文件 {src_path}")
        return

    src = dechecker(Image.open(src_path))
    w, h = src.size
    quarter = w // FRAMES
    inner = CELL - 2 * MARGIN

    # 1) 先把每一格裁紧，得到 4 个角色裁剪图
    crops: list[Image.Image | None] = []
    for i in range(FRAMES):
        cell = src.crop((i * quarter, 0, (i + 1) * quarter, h))
        bbox = cleaned_alpha(cell).getbbox()
        crops.append(cell.crop(bbox) if bbox else None)

    valid = [c for c in crops if c is not None]
    if not valid:
        print(f"  [skip] {name}: 未检测到角色内容")
        return

    # 2) 统一缩放系数：以最大帧为准，保证整段动画里角色体型一致（避免忽大忽小）
    max_w = max(c.width for c in valid)
    max_h = max(c.height for c in valid)
    scale = min(inner / max_w, inner / max_h)

    sheet = Image.new("RGBA", (CELL * FRAMES, CELL), (0, 0, 0, 0))
    for i, crop in enumerate(crops):
        if crop is None:
            continue
        nw = max(1, int(round(crop.width * scale)))
        nh = max(1, int(round(crop.height * scale)))
        scaled = crop.resize((nw, nh), Image.LANCZOS)

        # 3) 底部对齐 + 以脚部中心水平居中
        fx = feet_center_x(scaled)
        x = i * CELL + (CELL // 2) - fx
        x = max(i * CELL, min(x, i * CELL + CELL - nw))
        y = CELL - MARGIN - nh
        sheet.alpha_composite(scaled, (x, y))

    out_path = OUT_DIR / f"{name}_sheet.png"
    sheet.save(out_path)
    print(f"  [ok] {name}: {src.size} -> {sheet.size}  ({out_path.relative_to(ROOT)})")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {OUT_DIR.relative_to(ROOT)}  (CELL={CELL}, FRAMES={FRAMES})")
    for name in NAMES:
        build_sheet(name)
    print("完成。")


if __name__ == "__main__":
    main()
