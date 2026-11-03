#!/usr/bin/env python3
"""验错：按错误库，把剧本或提示词草稿里能机器查出来的错误一次查完。

错误库（工位/_共用/错误库.md）是错题本；这个脚本把其中能靠文字规律发现的几类做成自动检查，
查不了的（信息越界、改写前提、巧合等）在报告末尾列成人工核对清单。

用法：
  python3 tools/check_errors.py 草稿.md                    # 查提示词或剧本草稿
  python3 tools/check_errors.py 草稿.md --script 剧本.md    # 再逐句核对：剧本台词有没有漏、改、加、顺序乱
  python3 tools/check_errors.py --selftest                  # 自检（check_kb.py 会调用）

查什么（括号里是错误库编号）：
  台词核对   剧本台词在草稿的 {} 里有没有漏掉、改动、多出、顺序颠倒（错01、错27、错28）
  人名符号   用 <名字> 包人名（错20）
  装饰拟声   "唰地""砰地"这类拟声，"像……一样"这类比喻（错25）
  机械表演   "视线先动、头随后、肩最后"这类固定顺序（错21）
  空反应镜   没有台词的镜头堆了三个以上微表情部位，却写不出触发（错28）
  时间戳     镜头时间不连续、和段落总时长对不上；有台词的镜头不足 2 秒
  保护项     代码块里缺"不要字幕""不要背景音乐"
  参考编号   同一个 @图片N 在一段里绑定了两次，或编号跳号（错20）
  只写本段   代码块里出现"下一段""下一组""下一幕"（v3.11 起只写本段画面）
  人物锁定   镜头里出现的人物本段没有锁定参考图；锁定里写了"全程、始终、一直"这类绝对状态时，提醒核对镜头有没有违反

自审（交付前必跑）：
  python3 tools/check_errors.py 草稿 --script 剧本 --review
  在上面的检查之外，再列出"逐段连贯表"（每段的站位、第一个镜头、落点），
  并打印自审清单。按清单逐条过一遍，回复用户时附一行"自审：查了什么，改了什么"。

结果分"错误"（必须改）和"提醒"（人工看一眼再决定）。有错误时退出码为 1。
"""
import difflib
import re
import sys

# ---------- 规则表（新错误能机器查的，在这里加一行） ----------

ONOMATOPOEIA = re.compile(r"[唰砰啪嗖哗咚嘭咣噗嗡]{1,2}[地的]|[“\"「][唰砰啪嗖哗咚嘭咣噗][！!]?[”\"」]")
SIMILE = re.compile(r"像[^，。；、\n]{1,15}一样|仿佛|宛如|如同[^，。；\n]{1,10}般|[^，。\n]{1,8}似的")
TEMPLATE = re.compile(r"(眼|视线|眼睛)先动[^。\n]{0,8}头|头(部)?随后|肩(膀)?最后|先眼后头|眼先.{0,3}头后")
NAME_TAG = re.compile(r"<[一-鿿]{1,8}>")
CUES = ["眼睛", "视线", "眼神", "眼皮", "下眼睑", "眉", "鼻翼", "嘴角", "嘴唇", "喉咙", "喉结",
        "下颌", "下巴", "手指", "肩"]
TRIGGERS = re.compile(r"听到|听见|看到|看见|说完|话音|因为|为了|这时|刚才|被|才|听完|一听|随即|接着上一镜")
SHOT = re.compile(r"镜头(\d+)[（(](\d+)-(\d+)秒[）)]")
DUR = re.compile(r"^\s*(\d+)秒")
BIND = re.compile(r"@图片(\d+)")
LOCK = re.compile(r"^([\u4e00-\u9fff]{1,6})：@图片\d+", re.M)
NEXT = re.compile(r"下一段|下一组|下一幕|下一集")
PREV = re.compile(r"同上一段|上一段|上一组|前一段|前面几场|刚才那|区分开")
ABSOLUTE = re.compile(r"全程|始终|一直|从头到尾")
STAGE_WORDS = re.compile(r"节奏|特写|镜头|字幕|片尾|政策|动作|画面|切点|转场|定格|场景|情节|人物|备注|说明|边界|依据")


def strip_code_names(s):
    return re.sub(r"`[^`\n]*`", "", s)


def norm(s):
    s = s.replace("‘", "\"").replace("’", "\"").replace("“", "\"").replace("”", "\"")
    return re.sub(r"\s+", "", s)


def bare(s):
    return re.sub(r"[\W_]+", "", s)


def script_lines(text):
    """剧本台词：优先取「」里的；没有「」就取"角色：台词"格式的行。"""
    quoted = re.findall(r"「([^」]+)」", text)
    # 去掉标题里的品牌词（例如 「不烧心」系列）：太短且没有标点的不算台词
    quoted = [q for q in quoted if len(q) > 4 or re.search(r"[，。？！…]", q)]
    if quoted:
        return quoted
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*([一-鿿]{1,6})(?:（[^）]*）)?[：:]\s*(.+)$", line)
        if m and not STAGE_WORDS.search(m.group(1)):
            out.append(m.group(2).strip())
    return out


def code_blocks(text):
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.S)


def shot_paragraphs(block):
    """把一个代码块切成镜头段：从「镜头N（」开始到下一个镜头或下一个【】段为止。"""
    parts = []
    idx = [m.start() for m in SHOT.finditer(block)]
    for i, st in enumerate(idx):
        end = idx[i + 1] if i + 1 < len(idx) else len(block)
        seg = block[st:end]
        cut = seg.find("【")
        if cut > 0:
            seg = seg[:cut]
        parts.append(seg)
    return parts


# ---------- 检查 ----------

def unify_shots(text):
    """把「SHOT 01｜0–2秒」这种写法（真人情绪表演的结构）统一成「镜头1（0-2秒）」再查。"""
    return re.sub(r"SHOT\s*0*(\d+)\s*[｜|]\s*(\d+)\s*[-–—]\s*(\d+)\s*秒",
                  lambda m: f"镜头{m.group(1)}（{m.group(2)}-{m.group(3)}秒）", text)


def check(draft, script=None):
    errors, notes = [], []
    draft = unify_shots(draft)
    body = strip_code_names(draft)
    blocks = code_blocks(draft) or [draft]

    # 台词核对
    if script is not None:
        want = script_lines(script)
        got = re.findall(r"\{([^{}]+)\}", draft)
        gn = [norm(g) for g in got]
        gb = [bare(g) for g in got]
        pos = []
        for w in want:
            n, b = norm(w), bare(w)
            if n in gn:
                pos.append(gn.index(n))
            elif b in gb:
                notes.append(f"台词只差标点（错28）：{w}")
                pos.append(gb.index(b))
            else:
                best = difflib.get_close_matches(n, gn, n=1, cutoff=0.6)
                if best:
                    errors.append(f"台词被改动（错01）：剧本「{w}」→ 草稿「{got[gn.index(best[0])]}」")
                    pos.append(gn.index(best[0]))
                else:
                    errors.append(f"台词漏了（错01、错28）：{w}")
        for g in got:
            if not any(bare(g) == bare(w) or difflib.SequenceMatcher(None, norm(g), norm(w)).ratio() >= 0.6
                       for w in want):
                notes.append(f"剧本里没有这句台词，是不是加的（错01）：{g}")
        if pos != sorted(pos):
            notes.append("台词顺序和剧本不一致（错27）：检查是不是有意调整的")

    # 人名符号
    for m in sorted(set(NAME_TAG.findall(body))):
        errors.append(f"用 <> 包人名（错20）：{m}，人名只在锁定段绑定一次，之后直接写名字")

    # 装饰拟声、比喻
    for m in sorted(set(x if isinstance(x, str) else x[0] for x in ONOMATOPOEIA.findall(body))):
        notes.append(f"拟声词（错25）：{m}，没有剧情功能就删")
    for m in sorted(set(SIMILE.findall(body)))[:10]:
        notes.append(f"比喻（错25）：{m}，不推动剧情、不帮生成就删")

    # 机械表演
    for m in TEMPLATE.finditer(body):
        errors.append(f"机械表演模板（错21）：「{m.group(0)}」，改写成真实因果")

    all_names = sorted({n for blk in blocks for n in LOCK.findall(blk)}, key=len, reverse=True)
    for bi, block in enumerate(blocks, 1):
        tag = f"第{bi}个代码块" if len(blocks) > 1 else "草稿"
        is_prompt = bool(SHOT.search(block))

        if is_prompt:
            # 只写本段
            for m in sorted(set(NEXT.findall(block))):
                errors.append(f"{tag} 提示词里写了「{m}」：只写本段画面，段与段怎么接写在设计表里（v3.11）")
            for m in sorted(set(PREV.findall(block))):
                notes.append(f"{tag} 提示词里写了「{m}」：模型看不到别段，需要的状态在本段写全（v3.14）")
            # 人物锁定
            first = SHOT.search(block).start()
            shots_text = block[first:]
            locked = set(LOCK.findall(block))
            masked = shots_text
            for name in all_names:
                cnt = masked.count(name)
                masked = masked.replace(name, "＃")
                if cnt and name not in locked:
                    notes.append(f"{tag} 「{name}」在镜头里出现了{cnt}次，但本段没有锁定参考图：画面里有他就补上锁定，只是提到就忽略")
            for line in block.splitlines():
                if LOCK.match(line) and ABSOLUTE.search(line):
                    notes.append(f"{tag} 锁定里写了绝对状态「{line.strip()[:40]}」：核对本段每个镜头有没有违反，违反就改锁定，写清这一段的实际状态")

        # 空反应镜
        for seg in shot_paragraphs(block):
            if "{" in seg:
                continue
            hit = [c for c in CUES if c in seg]
            if len(hit) >= 3 and not TRIGGERS.search(seg):
                head = SHOT.search(seg).group(0)
                errors.append(f"{tag} {head} 是没有台词的反应镜，堆了{len(hit)}个部位（{'、'.join(hit)}），"
                              f"却没写触发（错28）：写清她因为什么、读出什么，是否符合人设；说不出来就删")

        if not is_prompt:
            continue

        # 时间戳
        shots = [(int(a), int(b), int(c)) for a, b, c in SHOT.findall(block)]
        prev = None
        for n, a, b in shots:
            if b <= a:
                errors.append(f"{tag} 镜头{n} 时间倒置：{a}-{b}秒")
            if prev is not None and a != prev:
                errors.append(f"{tag} 镜头{n} 没有接上一镜：上一镜到第{prev}秒，这一镜从第{a}秒开始")
            prev = b
        m = DUR.search(block)
        if m and shots and shots[-1][2] != int(m.group(1)):
            errors.append(f"{tag} 总时长写的是{m.group(1)}秒，镜头排到第{shots[-1][2]}秒")
        for seg in shot_paragraphs(block):
            sm = SHOT.search(seg)
            if "{" in seg and int(sm.group(3)) - int(sm.group(2)) < 2:
                notes.append(f"{tag} {sm.group(0)} 有台词但不足2秒，念不完")

        # 保护项
        for need in ("不要字幕", "不要背景音乐"):
            if need not in block:
                errors.append(f"{tag} 缺保护项「{need}」")

        # 参考编号
        nums = [int(x) for x in BIND.findall(block)]
        for x in sorted(set(nums)):
            if nums.count(x) > 1:
                notes.append(f"{tag} @图片{x} 出现了{nums.count(x)}次，人名只绑定一次（错20）")
        if nums and sorted(set(nums)) != list(range(1, max(nums) + 1)):
            notes.append(f"{tag} @图片编号跳号：{sorted(set(nums))}，按首次出场顺序从1连续编")

    return errors, notes


MANUAL = """自审清单（脚本查不了，逐条过；对照 工位/_共用/错误速查.md）：
  1. 用户这次说的每一点，逐条列出来打勾了吗？有没有顺手改了他没让改的？（错01、错02）
  2. 物件去向：每个人物、每件关键道具这一段在哪、什么状态，和上一段的落点对得上吗？现实里它还可能在那儿吗？（错05、错09）
  3. 人物状态：姿态、手里拿着什么、和谁在一起、情绪到哪一档，前后一致吗？情绪档位是用户定的，还是我加的？
  4. 空间：布局、楼层、左右站位、动线，和参考图一致吗？参考图里带着、但这一场不该有的东西，写明"画面里没有"了吗？
  5. 命名：同一个人物全文只有一个称呼吗？有没有和其他角色、道具、设定里的名字撞？
  6. 参考图：文字写的长相、服装、颜色，有没有和参考图打架？同一件道具的颜色、款式前后一致吗？
  7. 台词：每句只说这个人此刻知道的事吗？念出来像人话吗？我改动的台词向用户说明了吗？（错24、错27）
  8. 剧本之外我加的每个镜头：触发是什么、观众读出什么、合不合人设？（错28）
  9. 冷读：把每段提示词当成模型第一次看到的唯一一段，只靠这段文字，画面会不会生成错？"""


# ---------- 自审：逐段连贯表 ----------

def review(draft):
    """把每段的站位、第一个镜头、落点并排列出来，方便逐段核对连贯。"""
    draft = unify_shots(draft)
    heads = [(m.start(), m.group(1)) for m in re.finditer(r"^#{2,4}\s*(.+)$", draft, re.M)]
    out = ["逐段连贯表（上一段的落点 ↔ 这一段的站位和第一个镜头，逐行对照）："]
    for m in re.finditer(r"```[^\n]*\n(.*?)```", draft, re.S):
        block = m.group(1)
        if not SHOT.search(block):
            continue
        title = next((t for pos, t in reversed(heads) if pos < m.start()), "（无标题）")
        stand = re.search(r"站位：([^\n]*)", block)
        first = SHOT.search(block)
        first_line = block[first.start():].split("\n", 2)
        first_txt = (first_line[1] if len(first_line) > 1 else first_line[0])[:70]
        end = re.search(r"【结尾与转场】\n([^\n]*)", block)
        out.append(f"■ {title}")
        out.append(f"  站位：{(stand.group(1) if stand else '（没写）')[:90]}")
        out.append(f"  开头：{first_txt}")
        out.append(f"  落点：{(end.group(1) if end else '（没写）')[:90]}")
    return "\n".join(out)


# ---------- 自检 ----------

SELFTEST_SCRIPT = "甲：你好。\n乙：「这是剧本台词。」\n"
SELFTEST_DRAFT = """
```
6秒，9:16。
【分镜】
镜头1（0-2秒）｜说话：<小明>用中文说：{这是剧本台词。}他的耳朵唰地压平，像风一样。
镜头2（3-5秒）｜听者：她的眼睛往桌上瞟了一下，嘴角还在，喉咙动了一下。
镜头3（5-6秒）｜视线先动，头随后，肩最后。
保护项：不要字幕。
@图片1 @图片1 @图片3
```
"""


def selftest():
    errs, notes = check(SELFTEST_DRAFT, "乙：「这是剧本台词。」「这句被漏掉了。」")
    text = "\n".join(errs + notes)
    expect = ["台词漏了", "<小明>", "唰地", "比喻", "机械表演", "反应镜", "没有接上一镜",
              "缺保护项「不要背景音乐」", "@图片1 出现了2次", "跳号"]
    missing = [e for e in expect if e not in text]
    if missing:
        print("验错自检失败，没查出：", "、".join(missing))
        return False
    clean = """```
4秒，9:16。
镜头1（0-2秒）｜听到这句，她手停住，眼睛和嘴角都没动：{好。}
镜头2（2-4秒）｜空镜。
保护项：不要字幕，不要背景音乐。
@图片1 @图片2
```"""
    e2, _ = check(clean, "「好。」")
    if e2:
        print("验错自检失败，干净样例被误报：", e2)
        return False
    e4, n4 = check("```\n角色甲：@图片1，全程站着。\n镜头1（0-2秒）｜角色甲坐下，角色乙走过来，站位同上一段。下一段从屋里开始。\n不要字幕，不要背景音乐。\n```\n```\n角色乙：@图片1。\n镜头1（0-2秒）｜空镜。\n不要字幕，不要背景音乐。\n```")
    t4 = "\n".join(e4 + n4)
    for want in ("下一段", "上一段", "绝对状态", "「角色乙」在镜头里出现"):
        if want not in t4:
            print("验错自检失败，新检查没查出：", want)
            return False
    e3, _ = check("```\nSHOT 01｜0–2秒｜空镜。\nSHOT 02｜3–5秒｜说：{好。}\n不要字幕，不要背景音乐。\n```")
    if not any("没有接上一镜" in e for e in e3):
        print("验错自检失败，SHOT 写法的时间戳没查到")
        return False
    return True


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        ok = selftest()
        print("验错自检通过" if ok else "")
        sys.exit(0 if ok else 1)
    want_review = "--review" in args
    if want_review:
        args.remove("--review")
    script = None
    if "--script" in args:
        i = args.index("--script")
        script = open(args[i + 1], encoding="utf-8").read()
        del args[i:i + 2]
    if not args:
        print(__doc__)
        sys.exit(2)
    draft = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
    errors, notes = check(draft, script)
    for e in errors:
        print("错误 ", e)
    for n in notes:
        print("提醒 ", n)
    if script is None:
        print("（没给 --script，台词完整性没查）")
    if want_review:
        print(review(draft))
    print(MANUAL)
    print("通过" if not errors else f"未通过：{len(errors)} 个错误")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
