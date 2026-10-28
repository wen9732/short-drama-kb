#!/usr/bin/env python3
"""把一张工位卡导出成"自成一体"的系统提示词，给 GPT、豆包等其他 AI 直接粘贴使用。

导出内容 = 工位卡 + 卡里「必读」「按需」列出的全部文件正文（去重，按出现顺序）。
案例库和原始素材不导出。导出的是快照：规则更新后重新运行一次即可，不要手改导出文件。

用法：
  python3 tools/export_agent.py 美学图像            # → 系统提示词/导出/美学图像.md
  python3 tools/export_agent.py 美学图像 情绪导演     # 一次导出多张
  python3 tools/export_agent.py --all                # 导出 工位/ 下全部工位卡
"""
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "系统提示词", "导出")
PATH = re.compile(r"`([^`<>*]+\.(?:md|txt))`")
SKIP = ("范例/", "原始素材/", "工位/", "项目/", "日志/", "维护手册.md", "启动.md")


def version():
    t = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    m = re.search(r"当前版本：(v[\d.]+)", t)
    return m.group(1) if m else "?"


def commit():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "?"


def export(name):
    card = os.path.join(ROOT, "工位", f"{name}.md")
    if not os.path.exists(card):
        sys.exit(f"找不到工位卡：工位/{name}.md")
    card_text = open(card, encoding="utf-8").read()
    files = []
    for p in PATH.findall(card_text):
        if p.startswith(SKIP) and not p.startswith("工位/_共用/"):
            continue
        if p not in files and os.path.exists(os.path.join(ROOT, p)):
            files.append(p)
    parts = [
        f"# 系统提示词｜{name}（自动导出）",
        "",
        f"> 由 `tools/export_agent.py` 从知识库 {version()}（提交 {commit()}）导出。",
        "> 用法：整份粘贴给任意 AI 当系统提示词或项目知识。下面第一部分是你的角色和工作流程，后面是它要用到的规则全文。",
        "> 文中提到的文件路径，正文都已附在本文件后面，按标题找即可；提到但没附的（案例库、其他工位），表示在这个独立版本里不可用。",
        "",
        "---",
        "",
        "## 第一部分：角色与流程",
        "",
        re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", card_text, flags=re.M).strip(),
    ]
    for p in files:
        body = open(os.path.join(ROOT, p), encoding="utf-8").read().strip()
        body = re.sub(r"\A---\n.*?\n---\n", "", body, flags=re.S)  # 去掉技能的 frontmatter
        body = re.sub(r"^(#{1,5}) ", lambda m: "#" * min(len(m.group(1)) + 2, 6) + " ", body, flags=re.M)
        parts += ["", "---", "", f"## 附：`{p}`", "", body]
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"{name}.md")
    text = "\n".join(parts) + "\n"
    open(out, "w", encoding="utf-8").write(text)
    print(f"已导出 {os.path.relpath(out, ROOT)}：{len(files)} 个文件，{len(text)} 字")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    if args == ["--all"]:
        args = [os.path.splitext(os.path.basename(p))[0] for p in sorted(glob.glob(os.path.join(ROOT, "工位", "*.md")))]
    for a in args:
        export(a)


if __name__ == "__main__":
    main()
