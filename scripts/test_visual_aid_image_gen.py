#!/usr/bin/env python3
"""
配图生成冒烟测试脚本。

用途：
1) 验证 .env 中的配图模型配置是否可用
2) 直接调用 multi_agent_teaching.image_gen.generate_image_for_node()
3) 将图片保存到 static/uploads/visual_aids/_smoke_test/

示例：
  python scripts/test_visual_aid_image_gen.py
  python scripts/test_visual_aid_image_gen.py --prompt "一张显示勾股定理的几何示意图"
  python scripts/test_visual_aid_image_gen.py --model gpt-image-1 --mode openai
  python scripts/test_visual_aid_image_gen.py --model doubao-seedream-5.0-lite --mode predictions --size 2K
  python scripts/test_visual_aid_image_gen.py --model gemini-3.1-flash-image-preview --mode gemini --aspect-ratio 4:3
"""

from __future__ import annotations

import argparse
import os
import sys
import time

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def _set_env_if_given(key: str, value: str | None) -> None:
    if value is not None and str(value).strip():
        os.environ[key] = str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="测试教学地图配图生成功能")
    parser.add_argument(
        "--prompt",
        default="一张清晰的初中数学教学配图：直角三角形ABC，标注三边a,b,c，并在图旁用中文说明 a²+b²=c²。",
        help="用于生成图片的描述词",
    )
    parser.add_argument("--subject", default="数学", help="学科（用于拼接系统提示）")
    parser.add_argument("--grade", default="初二", help="年级（用于拼接系统提示）")
    parser.add_argument(
        "--task-id",
        default="_smoke_test",
        help="保存目录任务ID（默认 _smoke_test）",
    )
    parser.add_argument(
        "--node-id",
        default="SMOKE-M1",
        help="节点ID（会参与文件名生成）",
    )

    parser.add_argument("--model", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_MODEL")
    parser.add_argument("--mode", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_API_MODE")
    parser.add_argument("--size", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_SIZE")
    parser.add_argument("--quality", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_QUALITY")
    parser.add_argument("--base-url", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_BASE_URL")
    parser.add_argument("--api-key", default=None, help="覆盖 TEACHING_MAP_IMAGE_GEN_API_KEY")
    parser.add_argument(
        "--aspect-ratio",
        default=None,
        help="覆盖 TEACHING_MAP_IMAGE_GEN_ASPECT_RATIO（Gemini 图像模型）",
    )
    args = parser.parse_args()

    if load_dotenv:
        load_dotenv(os.path.join(ROOT_DIR, ".env"))

    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_MODEL", args.model)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_API_MODE", args.mode)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_SIZE", args.size)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_QUALITY", args.quality)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_BASE_URL", args.base_url)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_API_KEY", args.api_key)
    _set_env_if_given("TEACHING_MAP_IMAGE_GEN_ASPECT_RATIO", args.aspect_ratio)

    # 动态导入，确保读取的是最新环境变量
    import importlib
    import config as app_config
    import multi_agent_teaching.image_gen as image_gen

    importlib.reload(app_config)
    importlib.reload(image_gen)

    node_id = "%s-%d" % (args.node_id, int(time.time()))

    print("=== 配图生成测试开始 ===")
    print("MODEL     :", app_config.IMAGE_GEN_MODEL)
    print("MODE      :", app_config.IMAGE_GEN_API_MODE)
    print("SIZE      :", app_config.IMAGE_GEN_SIZE)
    print("QUALITY   :", app_config.IMAGE_GEN_QUALITY)
    print("ASPECT    :", getattr(app_config, "IMAGE_GEN_ASPECT_RATIO", "4:3"))
    print("BASE_URL  :", app_config.IMAGE_GEN_BASE_URL)
    print("TASK_ID   :", args.task_id)
    print("NODE_ID   :", node_id)
    print("PROMPT    :", args.prompt)
    print("----------------------------------------")

    url = image_gen.generate_image_for_node(
        task_id=args.task_id,
        node_id=node_id,
        visual_aid_prompt=args.prompt,
        subject=args.subject,
        grade=args.grade,
    )

    if not url:
        print("❌ 失败：未返回图片 URL。请查看 Flask 日志中的具体报错。")
        return 1

    abs_path = os.path.join(ROOT_DIR, url.lstrip("/"))
    print("✅ 成功：", url)
    print("文件路径：", abs_path)
    print("存在校验：", "OK" if os.path.exists(abs_path) else "MISSING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

