#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kgent V3 — 本地文件变更监控 + AI 日报生成

运行模式：
  python main.py                        # 交互式菜单（默认）
  python main.py -c my.json             # 指定配置文件进入交互模式
  python main.py snapshot               # 打一次快照后退出（供计划任务调用）
  python main.py snapshot --label TEXT  # 打快照并指定标签
  python main.py --web                  # 启动 Web 管理界面（自动打开浏览器）
  python main.py --web --port 8080      # 指定端口
  python main.py --web --no-browser     # 不自动打开浏览器
"""

import argparse
import sys
from pathlib import Path


def _resolve_config(path_str: str) -> Path:
    p = Path(path_str).resolve()
    if not p.exists():
        print(f"[错误] 配置文件不存在: {p}")
        print("请先复制配置模板: copy config.example.json config.json")
        sys.exit(1)
    return p


def cmd_interactive(args: argparse.Namespace) -> None:
    """进入交互式终端菜单。"""
    config_path = _resolve_config(args.config)
    try:
        from daily_reporter.ui import run_interactive
        run_interactive(config_path)
    except KeyboardInterrupt:
        print("\n已退出。")


def cmd_web(args: argparse.Namespace) -> None:
    """启动 Web 管理后台服务。"""
    config_path = _resolve_config(args.config)
    try:
        from daily_reporter.web import run_server
        run_server(
            config_path=config_path,
            host="127.0.0.1",
            port=args.port,
            open_browser=not args.no_browser,
        )
    except KeyboardInterrupt:
        print("\n[Web] 已退出。")


def cmd_snapshot(args: argparse.Namespace) -> None:
    """打一次快照后退出，无需交互界面。供 Windows 计划任务调用。"""
    config_path = _resolve_config(args.config)
    from daily_reporter.config import load_config
    from daily_reporter.snapshot import take_snapshot

    cfg = load_config(config_path)
    label = args.label or "auto"
    try:
        snap = take_snapshot(cfg, label=label, trigger="scheduled")
        print(f"[快照] {snap['id']}  文件数: {snap['file_count']}  标签: {label}")
    except Exception as e:
        print(f"[错误] 打快照失败: {e}")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="本地文件变更监控 + 快照日报生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python main.py                        # 交互式菜单
  python main.py -c D:\\work\\config.json # 指定配置文件
  python main.py snapshot               # 打一次快照后退出
  python main.py snapshot --label noon  # 打快照并指定标签
  python main.py --web                  # 启动 Web 管理界面
  python main.py --web --port 8080      # 指定端口
        """,
    )
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="配置文件路径（默认: config.json）",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web 管理界面（默认端口 7421，自动打开浏览器）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7421,
        help="Web 服务端口（默认 7421，仅 --web 模式有效）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="不自动打开浏览器（仅 --web 模式有效，适合服务器部署）",
    )

    subparsers = parser.add_subparsers(dest="command")

    # snapshot 子命令
    sp = subparsers.add_parser(
        "snapshot",
        help="打一次快照后退出（供 Windows 计划任务调用，无需交互界面）",
    )
    sp.add_argument(
        "--label", "-l",
        default="",
        help="快照标签（如 morning / noon / evening），留空则自动推断",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "snapshot":
        cmd_snapshot(args)
    elif getattr(args, 'web', False):
        cmd_web(args)
    else:
        cmd_interactive(args)


if __name__ == "__main__":
    main()
