#!/usr/bin/env python3
"""检测多个 PR 之间是否互相冲突。

GitHub 只提示“当前 PR 与 base 分支”的冲突，看不到两个并行 PR 之间的冲突：
两人改同一文件的相邻位置时，各自对 main 都干净，先合的那个会让另一个直接冲突。
本脚本把多个 PR 的 head 两两做一次合并试算，输出冲突对与同文件重叠清单。

用法：
    # 已 fetch 的本地引用
    python scripts/check_pr_conflicts.py --base origin/main \
        origin/pr-12 origin/pr-15 origin/pr-18

    # 直接读 GitHub 上的开放 PR（需要 gh 已登录或设置 GH_TOKEN）
    python scripts/check_pr_conflicts.py --gh --base origin/main

    # 只高亮某个 PR 参与的冲突对，并写出 markdown
    python scripts/check_pr_conflicts.py --gh --base origin/main \
        --focus 15 --markdown conflict-report.md

退出码：0 无冲突（可能有同文件重叠）；1 存在文本冲突；2 运行错误。

说明：
- 冲突判定用 `git merge-tree --write-tree`（git ≥ 2.38），只算不落地，不改工作区。
- “同文件重叠”指两 PR 都改了同一文件但合并没有文本冲突，仍需人工确认语义。
"""

import argparse
import subprocess
import sys

MERGE_TREE_MIN = (2, 38)


class GitError(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 失败：{proc.stderr.strip()}")
    return proc


def check_git_version() -> None:
    out = git("--version").stdout.strip()          # git version 2.42.0.windows.1
    parts = out.split()
    ver = parts[2] if len(parts) > 2 else "0"
    major, minor = (int(x) for x in ver.split(".")[:2])
    if (major, minor) < MERGE_TREE_MIN:
        raise SystemExit(
            f"需要 git ≥ {MERGE_TREE_MIN[0]}.{MERGE_TREE_MIN[1]}（支持 merge-tree --write-tree），"
            f"当前 {major}.{minor}"
        )


def resolve(ref: str) -> str:
    return git("rev-parse", "--verify", ref + "^{commit}").stdout.strip()


def changed_files(base: str, ref: str) -> set:
    out = git("diff", "--name-only", f"{base}...{ref}").stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def conflicts(a: str, b: str) -> list:
    """返回冲突文件列表；无冲突返回空列表。

    使用 `--no-messages` 的机器格式：首行是试算出的树 OID，其后每行形如
        <mode> <oid> <stage>\t<path>
    stage 0 为合并结果，1/2/3 为该路径的冲突暂存版本，同一路径会出现多行。
    """
    proc = git("merge-tree", "--write-tree", "--no-messages", a, b, check=False)
    if proc.returncode == 0:
        return []
    if proc.returncode != 1:
        raise GitError(f"merge-tree 异常：{proc.stderr.strip()}")

    files = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        stage = meta.split()[-1]
        if stage != "0" and path not in files:
            files.append(path)
    return files or ["(冲突，文件未解析)"]


def open_prs() -> list:
    """通过 gh 读取开放 PR。"""
    proc = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--limit", "100",
         "--json", "number,title,headRefName,baseRefName"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"读取 PR 列表失败（gh 是否登录？）：{proc.stderr.strip()}")
    import json
    return json.loads(proc.stdout)


def fetch_pr_heads(prs: list) -> dict:
    """把每个 PR 的 head 抓到本地 refs/pr/<编号>，返回 编号 -> ref。"""
    refs = {}
    for pr in prs:
        num = pr["number"]
        ref = f"refs/pr/{num}"
        git("fetch", "--no-tags", "origin", f"+refs/pull/{num}/head:{ref}")
        refs[num] = ref
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description="检测多个 PR 之间的相互冲突")
    ap.add_argument("refs", nargs="*", help="要比较的引用，如 origin/pr-12")
    ap.add_argument("--base", default="origin/main", help="基线分支，默认 origin/main")
    ap.add_argument("--gh", action="store_true", help="从 GitHub 读取开放 PR 并抓取其 head")
    ap.add_argument("--focus", type=int, help="只高亮该 PR 编号参与的冲突对")
    ap.add_argument("--markdown", help="把报告写到指定文件（markdown）")
    args = ap.parse_args()

    check_git_version()
    base_sha = resolve(args.base)

    labels = {}          # ref -> 展示名
    if args.gh:
        prs = open_prs()
        if not prs:
            print("没有开放的 PR，无需检查。")
            return 0
        ref_map = fetch_pr_heads(prs)
        for pr in prs:
            labels[ref_map[pr["number"]]] = f"#{pr['number']} {pr['title']}"
        refs = list(ref_map.values())
    else:
        if len(args.refs) < 2:
            ap.error("至少给两个引用，或用 --gh 读取开放 PR")
        refs = []
        for ref in args.refs:
            resolve(ref)
            refs.append(ref)
            labels[ref] = ref

    files = {ref: changed_files(args.base, ref) for ref in refs}

    rows = []
    hard = 0
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            overlap = sorted(files[a] & files[b])
            clash = conflicts(a, b)
            if clash:
                hard += 1
                rows.append(("冲突", labels[a], labels[b], clash, overlap))
            elif overlap:
                rows.append(("同文件", labels[a], labels[b], [], overlap))

    show = rows
    if args.focus is not None:
        token = f"#{args.focus}"
        show = [r for r in rows if token in r[1].split()[0] or token in r[2].split()[0]]

    out = []
    out.append("### PR 间冲突检查\n")
    out.append(f"基线 `{args.base}`（{base_sha[:8]}），参与比较 {len(refs)} 个引用。\n")
    if not rows:
        out.append("未发现 PR 之间的文本冲突或同文件重叠。\n")
    else:
        out.append(f"发现 {hard} 对文本冲突，{len(rows) - hard} 对同文件重叠。\n")
        out.append("| 类型 | A | B | 冲突文件 / 重叠文件 |")
        out.append("| --- | --- | --- | --- |")
        for kind, a, b, clash, overlap in show:
            detail = "、".join(clash[:3]) if clash else "、".join(overlap[:3])
            if len((clash or overlap)) > 3:
                detail += " 等"
            out.append(f"| {kind} | {a} | {b} | {detail} |")
        out.append("")
        if len(show) < len(rows):
            out.append(f"（共 {len(rows)} 对，此处仅列 `--focus` 相关部分。）\n")
    if hard:
        out.append("处理建议：先合并任一方并 rebase 另一方，或在 PR 描述里说明按谁的版本为准。\n")

    report = "\n".join(out)
    print(report)
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
    return 1 if hard else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GitError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        sys.exit(2)
