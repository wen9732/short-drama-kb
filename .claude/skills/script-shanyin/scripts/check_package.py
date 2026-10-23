"""Check deterministic package integrity; do not grade story quality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def inspect_package(root: Path) -> dict:
    root = root.resolve()
    errors: list[dict] = []
    files = sorted(root.rglob("*.md"))
    reference_count = 0

    def fail(path: Path, line: int, reason: str) -> None:
        errors.append({"file": str(path.relative_to(root)), "line": line, "reason": reason})

    skill = root / "SKILL.md"
    if not skill.is_file():
        errors.append({"file": "SKILL.md", "line": 1, "reason": "missing entrypoint"})

    resource_pattern = re.compile(
        r"(?<![\w./-])((?:(?:references|assets|scripts)/)?"
        r"[A-Za-z][A-Za-z0-9._/-]*\.(?:md|json|py))(?![\w/-]|\.[\w-])"
    )
    marker_class = re.escape(chr(96))
    fence_pattern = re.compile(r"^ {0,3}(" + marker_class + r"{3,}|~{3,})(.*)$")
    escaped_fence_pattern = re.compile(r"^ {0,3}\\+(?:" + marker_class + r"{3,}|~{3,})")

    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            fail(path, 1, "document is not UTF-8")
            continue

        if "\x00" in text:
            fail(path, 1, "document contains NUL")
        if path == skill and not re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", text, re.S):
            fail(path, 1, "entrypoint frontmatter is missing or unterminated")

        opened = None
        for number, line in enumerate(text.splitlines(), 1):
            if escaped_fence_pattern.match(line):
                fail(path, number, "escaped code fence cannot delimit a Markdown block")
            match = fence_pattern.match(line)
            if match:
                marker, info = match.groups()
                if opened is None:
                    opened = (marker[0], len(marker), number)
                elif marker[0] == opened[0] and len(marker) >= opened[1] and not info.strip():
                    opened = None
            elif opened is None and re.search(r"(?<!\\)\\n", line):
                fail(path, number, "literal newline escape outside a code block")

            if not re.search(r"https?://", line):
                for reference in resource_pattern.findall(line):
                    reference_count += 1
                    candidates = [root / reference, path.parent / reference, root / "references" / reference]
                    existing = [item.resolve() for item in candidates if item.is_file()]
                    if not existing:
                        fail(path, number, f"missing resource: {reference}")
                    elif not any(item == root or root in item.parents for item in existing):
                        fail(path, number, f"resource escapes package: {reference}")
        if opened is not None:
            fail(path, opened[2], "unclosed Markdown code fence")

    return {"root": str(root), "markdown_files": len(files), "references_checked": reference_count,
            "errors": errors, "ok": not errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = inspect_package(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
