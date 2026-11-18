#!/usr/bin/env python3
"""导出一份"给其他 AI 的接入说明"：日志＋调用方式，整份交给其他 AI 就知道这个知识库怎么用。

内容全部从仓库现有文件自动拼出来（规则只写一处，这里不另写规则）：
  CLAUDE.md 的角色与不可破规则 → 新窗口启动卡.md → 启动.md（调用方式）
  → 工位/_共用/错误速查.md → 日志/当前状态.md（日志）→ CHANGELOG.md 的版本标题

用法：python3 tools/export_guide.py   → 系统提示词/导出/给其他AI的接入说明.md
（`python3 tools/export_agent.py --all` 结束时会自动调用本脚本）
"""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "系统提示词", "导出", "给其他AI的接入说明.md")
REPO = "wen9732/short-drama-kb"


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def shift(text, n=2):
    """把正文的标题统一降 n 级，嵌进本文件不抢一级标题。"""
    return re.sub(r"^(#{1,6}) ", lambda m: "#" * min(len(m.group(1)) + n, 6) + " ", text.strip(), flags=re.M)


def drop_title(text):
    """去掉文件自己的一级标题，避免和本文件的小节标题重复。"""
    return re.sub(r"\A# .*\n+", "", text.strip())


def section(text, head):
    m = re.search(rf"^## {re.escape(head)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def commit():
    try:
        return subprocess.check_output(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "?"


def main():
    claude = read("CLAUDE.md")
    ver = re.search(r"当前版本：(v[\d.]+)", claude)
    ver = ver.group(1) if ver else "?"
    exports = sorted(
        f for f in os.listdir(os.path.dirname(OUT))
        if f.endswith(".md") and f not in ("README.md", os.path.basename(OUT))
    )
    history = re.findall(r"^# (v\d+\.\d+｜.+)$", read("CHANGELOG.md"), re.M)

    parts = [
        "# 短剧编导知识库｜给其他 AI 的接入说明（日志＋调用方式）",
        "",
        f"> 由 `tools/export_guide.py` 从知识库 {ver}（提交 {commit()}）自动导出，不要手改。规则改了、升了版本，重新运行一次。",
        "> 用法：把这份文件整份交给其他 AI（GPT、豆包、Kimi、新开的 Claude 窗口……），放在最前面。它说明了这个知识库是什么、怎么接入、怎么下口令、现在进展到哪。",
        "",
        "---",
        "",
        "## 一、这是什么",
        "",
        "一个面向 AI 视频短剧（主要是豆包 Seedance 2.5）的编导知识库：从一个想法写到剧本（山音编剧系统），再从剧本设计成导演方案和可直接复制的视频提示词。"
        "知识库按「工位」组织，每个工位是一张卡，写着这个角色读哪些文件、交付什么；规则只写在 `.claude/skills/` 里。",
        "",
        "## 二、两种接入方式",
        "",
        f"**A. 能连 GitHub（推荐）：** 接入仓库 `{REPO}`，只读 `启动.md` 和 `日志/当前状态.md`，然后等口令。"
        "用户下口令后，按 `启动.md` 找到工位卡，**只读卡里列出的文件**，不要通读整个仓库。下面第四节就是 `新窗口启动卡.md` 的全文。",
        "",
        "**B. 连不了仓库：** 用导出的独立系统提示词，每个文件＝一张工位卡＋它要读的规则全文，整份粘贴即可：",
        "",
        "| 要做的事 | 给 AI 的文件 |",
        "|---|---|",
    ]
    names = {"导演.md": "剧本 → 导演设计 → Seedance 提示词", "情绪导演.md": "真人情绪戏（克制／爆发）",
             "爆款策划.md": "短视频选题", "编导总监.md": "总控、挑错、批改", "美学图像.md": "美术定调、参考图、生图提示词",
             "音效配乐.md": "Doubao-Seed-Audio 1.0 独立音效与配乐设计（支持提示词转音效）"}
    for f in exports:
        parts.append(f"| {names.get(f, os.path.splitext(f)[0])} | `系统提示词/导出/{f}` |")
    parts += [
        "| 写剧本（山音编剧） | 把仓库里 `.claude/skills/script-shanyin/` 整个文件夹上传为知识库，`SKILL.md` 当系统提示词；再加上 `工位/_共用/错误速查.md` |",
        "",
        "B 方式下，文中提到的仓库路径（如 `工位/导演.md`）如果没有附在你拿到的文件里，就表示这一项在独立版里不可用；案例库在独立版里都不可用。",
        "",
        "## 三、必须遵守的规则（摘自 `CLAUDE.md`）",
        "",
        "**角色：** " + section(claude, "你的角色"),
        "",
        section(claude, "不可破的规则"),
        "",
        "## 四、新窗口怎么开始（`新窗口启动卡.md` 全文）",
        "",
        shift(drop_title(read("新窗口启动卡.md"))),
        "",
        "## 五、调用方式（`启动.md` 全文）",
        "",
        shift(drop_title(read("启动.md"))),
        "",
        "## 六、交付前自检（`工位/_共用/错误速查.md` 全文）",
        "",
        shift(drop_title(read("工位/_共用/错误速查.md"))),
        "",
        "## 七、日志：现在到哪一步了（`日志/当前状态.md` 全文）",
        "",
        shift(drop_title(read("日志/当前状态.md"))),
        "",
        "## 八、版本历史（`CHANGELOG.md` 的标题，详情看原文件）",
        "",
    ]
    parts += [f"- {h}" for h in history]
    text = "\n".join(parts) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(text)
    print(f"已导出 {os.path.relpath(OUT, ROOT)}：{len(text)} 字")


if __name__ == "__main__":
    main()
