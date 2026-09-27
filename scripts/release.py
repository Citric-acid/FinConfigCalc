"""Create and publish a FinConfigCalc Windows release."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INIT_PATH = ROOT / "src" / "fin_config_calc" / "__init__.py"
EXPECTED_PYTHON = ROOT / ".venv" / "python.exe"
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PACKAGE_VERSION_PATTERN = re.compile(
    r'(?m)^(__version__\s*=\s*")([^"]+)(")',
)


class ReleaseError(RuntimeError):
    """Raised when the release cannot safely continue."""


def run(command: list[str]) -> None:
    print(f"\n> {subprocess.list2cmdline(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def capture(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def parse_version(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ReleaseError("版本号必须使用不带前缀的 X.Y.Z 格式，例如 0.2.0。")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def parse_commit_summary(value: str) -> str:
    summary = value.strip()
    if not summary:
        raise argparse.ArgumentTypeError("提交摘要不能为空。")
    if "\n" in summary or "\r" in summary:
        raise argparse.ArgumentTypeError("提交摘要必须为单行。")
    return summary


def build_commit_message(version: str, summary: str) -> str:
    return f"release v{version}: {summary}"


def read_text(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as file:
        return file.read()


def read_version(path: Path, pattern: re.Pattern[str]) -> str:
    content = read_text(path)
    matches = pattern.findall(content)
    if len(matches) != 1:
        raise ReleaseError(f"无法在 {path.relative_to(ROOT)} 中唯一确定版本号。")
    return matches[0][1]


def read_head_version(path: Path, pattern: re.Pattern[str]) -> str:
    relative_path = path.relative_to(ROOT).as_posix()
    content = capture(["git", "show", f"HEAD:{relative_path}"])
    matches = pattern.findall(content)
    if len(matches) != 1:
        raise ReleaseError(f"无法从 HEAD 中唯一确定 {relative_path} 的版本号。")
    return matches[0][1]


def replace_version(path: Path, pattern: re.Pattern[str], version: str) -> None:
    content = read_text(path)
    updated, replacements = pattern.subn(rf"\g<1>{version}\g<3>", content)
    if replacements != 1:
        raise ReleaseError(f"无法在 {path.relative_to(ROOT)} 中唯一更新版本号。")
    path.write_text(updated, encoding="utf-8", newline="")


def ensure_release_preconditions(version: str) -> str:
    if not EXPECTED_PYTHON.is_file():
        raise ReleaseError("缺少 .venv\\python.exe。请先创建项目环境并安装依赖，再重新执行发布。")
    if Path(sys.executable).resolve() != EXPECTED_PYTHON.resolve():
        raise ReleaseError("必须使用 .\\.venv\\python.exe 运行发布脚本。")

    repository_root = Path(capture(["git", "rev-parse", "--show-toplevel"])).resolve()
    if repository_root != ROOT:
        raise ReleaseError(f"脚本必须在仓库 {ROOT} 中执行。")

    branch = capture(["git", "symbolic-ref", "--quiet", "--short", "HEAD"])
    if not branch:
        raise ReleaseError("当前处于 detached HEAD，不能自动推送发布提交。")

    capture(["git", "remote", "get-url", "origin"])
    run(["git", "diff", "--check"])
    run(["git", "diff", "--cached", "--check"])
    unresolved = capture(["git", "diff", "--name-only", "--diff-filter=U"])
    if unresolved:
        raise ReleaseError(f"存在未解决的合并冲突：\n{unresolved}")

    package_version = read_version(PACKAGE_INIT_PATH, PACKAGE_VERSION_PATTERN)
    target = parse_version(version)
    current = parse_version(package_version)
    if target < current:
        raise ReleaseError(f"新版本 {version} 不能低于工作区版本 {package_version}。")
    if target == current:
        head_package_version = read_head_version(PACKAGE_INIT_PATH, PACKAGE_VERSION_PATTERN)
        changed_paths = set(capture(["git", "diff", "--name-only", "HEAD"]).splitlines())
        package_path = PACKAGE_INIT_PATH.relative_to(ROOT).as_posix()
        if target <= parse_version(head_package_version) or package_path not in changed_paths:
            raise ReleaseError(f"新版本 {version} 必须高于当前已发布版本 {head_package_version}。")
        print(f"检测到未完成的版本更新 {version}，将从质量检查阶段继续。", flush=True)

    return branch


def run_quality_checks() -> None:
    python = str(EXPECTED_PYTHON)
    run([python, "-m", "pip", "install", "-e", ".[dev,build-exe]"])

    test_files = list((ROOT / "tests").glob("**/test_*.py"))
    if test_files:
        run([python, "-m", "pytest"])
    else:
        print("\n! 未发现 tests/test_*.py，跳过 pytest；其余质量检查仍会执行。")

    run([python, "-m", "ruff", "check", "."])
    run([python, "-m", "ruff", "format", "--check", "."])
    run([python, "-m", "pyright"])


def commit_and_push(version: str, summary: str, branch: str) -> str:
    run(["git", "add", "--all"])
    staged_files = capture(["git", "diff", "--cached", "--name-only"])
    if not staged_files:
        raise ReleaseError("没有可提交的变更，发布已停止。")

    run(["git", "commit", "-m", build_commit_message(version, summary)])
    commit = capture(["git", "rev-parse", "--short", "HEAD"])

    upstream = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if upstream.returncode == 0:
        run(["git", "push"])
    else:
        run(["git", "push", "--set-upstream", "origin", branch])

    return commit


def build_executable(version: str) -> Path:
    run(
        [
            str(EXPECTED_PYTHON),
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "fin-config-calc.spec",
        ]
    )
    executable = ROOT / "dist" / f"FinConfigCalc-{version}" / "FinConfigCalc.exe"
    if not executable.is_file():
        raise ReleaseError(f"PyInstaller 已结束，但未生成预期文件：{executable}")
    return executable


def release(version: str, summary: str) -> None:
    branch = ensure_release_preconditions(version)
    replace_version(PACKAGE_INIT_PATH, PACKAGE_VERSION_PATTERN, version)
    run_quality_checks()
    commit = commit_and_push(version, summary, branch)
    executable = build_executable(version)

    print("\n发布完成：")
    print(f"  版本：{version}")
    print(f"  分支：{branch}")
    print(f"  提交：{commit}")
    print(f"  程序：{executable}")
    print(f"  分发目录：{executable.parent}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="更新版本、运行检查、提交推送并构建 Windows EXE。",
    )
    parser.add_argument("version", help="新版本号，格式为 X.Y.Z，例如 0.2.0")
    parser.add_argument(
        "--summary",
        required=True,
        type=parse_commit_summary,
        help='人工确认的单行改动摘要，例如 "feat: 添加字段映射"',
    )
    args = parser.parse_args()

    try:
        parse_version(args.version)
        release(args.version, args.summary)
    except (ReleaseError, subprocess.CalledProcessError) as error:
        print(f"\n发布失败：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
