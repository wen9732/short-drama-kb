#!/usr/bin/env python3
"""仓内商业短剧库按需检索工具（一体集成版，读 原始素材/script-shanyin/short-writing-db/）。

直读仓内 manifest.jsonl（319 部商业短剧元数据）与 mechanisms.jsonl（24 商业母题），
毫秒级检索；仅在传入 --preview 时单部按需解密样本开头，不拷贝明文进范例库。

用法：
  python tools/search_duanju_db.py --cats                         # 1毫秒列出20个赛道统计
  python tools/search_duanju_db.py --pick "重生复仇"              # 一条命令：Top5目录 + #1完本前1800字
  python tools/search_duanju_db.py "职场 证据" --full-only --top 5
  python tools/search_duanju_db.py --id fs0072 --preview 1800
  python tools/search_duanju_db.py --mech "直播 舆论"
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_ROOT = REPO_ROOT / "原始素材" / "script-shanyin" / "short-writing-db"

_CIPHER = "aes-256-cbc"
_ITERATIONS = "20000"
_KEY_ENV = "VSDW_FULL_SCRIPT_KEY"
_BUILTIN_KEY = (
    "vsdw-full-script-library"
    "::private-obfuscation"
    "::2026-06-02"
    "::do-not-use-for-strong-secrecy"
)


def find_openssl() -> str | None:
    """定位系统或 Git for Windows 自带的 openssl 可执行文件。"""
    exe = shutil.which("openssl")
    if exe:
        return exe
    for cand in (
        r"C:\Program Files\Git\usr\bin\openssl.exe",
        r"C:\Program Files (x86)\Git\usr\bin\openssl.exe",
    ):
        if Path(cand).is_file():
            return cand
    return None


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def score_record(rec: dict, terms: list[str], fields: tuple[str, ...]) -> int:
    if not terms:
        return 1
    hay = " ".join(json.dumps(rec.get(k, ""), ensure_ascii=False) for k in fields).lower()
    score = 0
    for t in terms:
        tl = t.lower()
        if tl in str(rec.get("title", "")).lower():
            score += 5
        elif tl in str(rec.get("category", "")).lower() or tl in str(rec.get("topic", "")).lower():
            score += 3
        elif tl in hay:
            score += 1
    return score


def decrypt_script(db_root: Path, rec: dict, limit: int) -> str:
    """优先直接读取仓内明文 .md（1毫秒、无需 openssl），缺文件时回退解密 .enc。"""
    md_dir = db_root / "明文剧本"
    if md_dir.is_dir():
        matches = sorted(md_dir.glob(f"{rec['id']}_*.md"))
        if matches:
            text = matches[0].read_text(encoding="utf-8", errors="ignore")
            if "## 正文" in text:
                text = text.split("## 正文", 1)[1]
            return text.strip()[:limit]

    openssl = find_openssl()
    if not openssl:
        raise RuntimeError("未找到明文剧本且系统缺少 openssl")

    enc_path = db_root / "full-scripts" / rec["filename"]
    if not enc_path.is_file():
        raise FileNotFoundError(f"找不到文件：{enc_path}")

    env = os.environ.copy()
    env[_KEY_ENV] = os.environ.get(_KEY_ENV) or _BUILTIN_KEY
    proc = subprocess.run(
        [
            openssl,
            "enc",
            "-d",
            f"-{_CIPHER}",
            "-pbkdf2",
            "-iter",
            _ITERATIONS,
            "-md",
            "sha256",
            "-in",
            str(enc_path),
            "-pass",
            f"env:{_KEY_ENV}",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    text = proc.stdout.decode("utf-8", errors="ignore")
    if "## 正文" in text:
        text = text.split("## 正文", 1)[1]
    return text.strip()[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="仓内商业短剧库按需检索")
    parser.add_argument("query", nargs="*", help="检索关键词（空格分隔）")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_ROOT, help="数据库目录")
    parser.add_argument("--top", type=int, default=8, help="返回条目上限")
    parser.add_argument("--full-only", action="store_true", help="只看 is_full_length=true 完本")
    parser.add_argument("--id", dest="script_id", help="按剧本 ID（如 fs0072）精准定位")
    parser.add_argument("--preview", type=int, default=0, help="按需解密预览前 N 字（仅限单部，上限3500）")
    parser.add_argument("--cats", action="store_true", help="列出所有赛道及完本数量")
    parser.add_argument("--pick", action="store_true", help="一锤子模式：返回Top5目录并只解密第1名开头1800字")
    parser.add_argument("--mech", action="store_true", help="改为检索 24 个商业母题库")
    args = parser.parse_args()

    db_root: Path = args.db
    if not db_root.is_dir():
        print(f"找不到仓内短剧数据库：{db_root}")
        return 1

    if args.cats:
        rows = load_jsonl(db_root / "manifest.jsonl")
        c_all = Counter(r["category"] for r in rows)
        c_full = Counter(r["category"] for r in rows if r.get("is_full_length"))
        for cat in sorted(c_all):
            print(f"{cat}: 共 {c_all[cat]} 部 / 完本 {c_full[cat]} 部")
        return 0

    if args.mech:
        mechs = load_jsonl(db_root / "mechanisms.jsonl")
        scored = []
        for m in mechs:
            sc = score_record(
                m,
                args.query,
                ("id", "title", "category", "topic", "tags", "opening_model", "transferable_mechanism", "use_for"),
            )
            if sc > 0:
                scored.append((sc, m))
        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        for _, m in scored[: args.top]:
            print(f"{m['id']} | [{m['category']}/{m['topic']}] {m['title']}")
            print(f"  开场：{m['opening_model']}")
            print(f"  机制：{m['transferable_mechanism']}")
            print(f"  必换：{m['must_replace']} | 雷区：{m['originality_risk']}")
        return 0

    rows = load_jsonl(db_root / "manifest.jsonl")
    if args.script_id:
        hits = [r for r in rows if r.get("id") == args.script_id]
        if not hits:
            print(f"未找到剧本 ID：{args.script_id}")
            return 1
        rec = hits[0]
        print(f"{rec['id']} | {rec['title']} | {rec['category']} | {rec['chars']}字 | 完本={rec.get('is_full_length')}")
        if args.preview > 0:
            cap = min(args.preview, 3500)
            print(f"\n--- 样本预览前 {cap} 字（严禁照抄 OS/括号/降智对白，只看节奏与钩子密度）---\n")
            print(decrypt_script(db_root, rec, cap))
        return 0

    if args.full_only:
        rows = [r for r in rows if r.get("is_full_length")]
    scored = []
    for r in rows:
        sc = score_record(r, args.query, ("id", "title", "category"))
        if sc > 0:
            if args.pick and r.get("is_full_length"):
                sc += 4
            scored.append((sc, r))
    scored.sort(key=lambda x: (-x[0], -int(x[1].get("is_full_length", False)), -x[1].get("chars", 0)))
    top_n = 5 if args.pick else args.top
    for _, r in scored[:top_n]:
        tag = "完本" if r.get("is_full_length") else "短样"
        print(f"{r['id']} | [{tag}] {r['category']} | {r['chars']}字 | {r['title']}")
    print(f"\n共匹配 {len(scored)} 部（当前展示前 {min(len(scored), top_n)} 部）。")
    if args.pick and scored:
        best = scored[0][1]
        print(f"\n=== 首推样本 [{best['id']}] {best['title']}（前 1800 字节奏参考，严禁照抄 OS/括号）===\n")
        print(decrypt_script(db_root, best, 1800))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
