"""Offline installer, launched only by the bundled platform interpreter."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid


class InstallError(Exception):
    pass


def runtime_name(system, machine):
    mapping = {("Darwin", "arm64"): "macos-arm64", ("Darwin", "aarch64"): "macos-arm64",
               ("Darwin", "x86_64"): "macos-x64", ("Windows", "amd64"): "windows-x64",
               ("Windows", "x86_64"): "windows-x64"}
    try:
        return mapping[(system, machine.lower())]
    except KeyError:
        raise InstallError("此安装包不支持当前系统或芯片。Windows 请使用 x64 电脑；Mac 支持 Apple 芯片和 Intel。") from None


def python_path(runtime, system):
    return runtime / ("python.exe" if system == "Windows" else "bin/python3")


def validate_runtime(runtime, system):
    executable = python_path(runtime, system)
    if not executable.is_file():
        raise InstallError("运行环境不完整，请完整解压安装包后重试。")
    probe = """import io, ssl, requests, boto3, certifi
from PIL import Image
for fmt in ('PNG', 'JPEG', 'WEBP'):
    b = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(b, format=fmt)
    b.seek(0)
    with Image.open(b) as im: im.verify()
assert ssl.create_default_context(cafile=certifi.where())
print('runtime-ok')
"""
    result = subprocess.run([str(executable), "-I", "-B", "-c", probe],
                            capture_output=True, text=True, timeout=45)
    if result.returncode or "runtime-ok" not in result.stdout:
        raise InstallError("自带运行环境检查未通过。请确认安装包与系统匹配，并完整解压；未修改原有技能。")


def write_launchers(target, system):
    if system == "Windows":
        text = ('@echo off\r\nsetlocal\r\n'
                '"%~dp0runtime\\python.exe" -I -B "%~dp0scripts\\apinebula_image.py" %*\r\n'
                'exit /b %ERRORLEVEL%\r\n')
        (target / "run.cmd").write_bytes(text.encode("ascii"))
    else:
        text = ('#!/bin/sh\n'
                'APINEBULA_SKILL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1\n'
                'exec "$APINEBULA_SKILL_DIR/runtime/bin/python3" -I -B '
                '"$APINEBULA_SKILL_DIR/scripts/apinebula_image.py" "$@"\n')
        launcher = target / "run.command"
        launcher.write_text(text, encoding="utf-8")
        launcher.chmod(0o755)


def install_package(package_root, target, system=None, machine=None):
    system = system or platform.system()
    selected = runtime_name(system, machine or platform.machine())
    package_root, target = Path(package_root).resolve(), Path(target).absolute()
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise InstallError("安装位置不是普通文件夹，已停止以保护原文件。")
    source, runtime = package_root / "skill", package_root / "runtime" / selected
    if not (source / "SKILL.md").is_file() or not runtime.is_dir():
        raise InstallError("请先将 ZIP 完整解压，再双击安装。当前包缺少技能或运行环境。")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".apinebula-install-", dir=target.parent))
    backup = None
    try:
        shutil.copytree(source, staging, dirs_exist_ok=True)
        shutil.copytree(runtime, staging / "runtime", symlinks=True)
        write_launchers(staging, system)
        validate_runtime(staging / "runtime", system)
        metadata = {"format": 1, "runtime": selected, "installed_at": datetime.now(timezone.utc).isoformat()}
        (staging / "portable-install.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if target.exists():
            backup_root = target.parent.parent / "skill-backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / (target.name + ".backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
            target.rename(backup)
        try:
            staging.rename(target)
        except Exception:
            if backup:
                backup.rename(target)
            raise
        return {"target": str(target), "backup": str(backup) if backup else None, "runtime": selected}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def configure_key(target):
    executable = python_path(target / "runtime", platform.system())
    script = target / "scripts/apinebula_image.py"
    if not executable.is_file() or not script.is_file():
        raise InstallError("尚未安装，请先双击 Install 文件。")
    if not sys.stdin.isatty():
        print("请由使用者双击 Configure-Key 文件，在本机终端隐藏输入 API Key；不要把密钥发到聊天。")
        return 0
    print("输入你自己的 APINebula 图片模型分组 API Key。输入时屏幕不显示字符，粘贴后按回车。")
    return subprocess.call([str(executable), "-I", "-B", str(script), "configure-key"])


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="APINebula 技能离线安装器，无需另装 Python")
    parser.add_argument("--target", type=Path, default=Path.home() / ".agents/skills/apinebula-imagegen")
    parser.add_argument("--configure-key", action="store_true")
    parser.add_argument("--no-key", action="store_true", help="只安装，稍后配置密钥")
    parser.add_argument("--check-package", action="store_true", help="仅验证自带环境，不安装、不联网、不出图")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parent
        if args.check_package:
            name = runtime_name(platform.system(), platform.machine())
            validate_runtime(root / "runtime" / name, platform.system())
            print("自带环境检查通过（未联网、未出图）。")
            return 0
        if args.configure_key:
            return configure_key(args.target)
        print("正在安装 APINebula 技能，自带运行环境；无需另装 Python，也不需要管理员权限。")
        result = install_package(root, args.target)
        print("安装完成：" + result["target"])
        if result["backup"]:
            print("原技能已备份：" + result["backup"])
        keyfile = Path.home() / ".config/codex-imagegen/apinebula-api-key"
        if not args.no_key:
            if keyfile.exists() or os.environ.get("APINEBULA_API_KEY"):
                print("检测到已有 API Key，保留原配置。需要更换时双击 Configure-Key 文件。")
            elif configure_key(args.target):
                print("技能已安装；密钥尚未配置成功，可稍后双击 Configure-Key 文件重试。")
                return 1
        print("回到 Codex，输入：用 apinebula-imagegen 生成一张图片。若技能未显示，重新启动 Codex。")
        print("之后直接描述修改需求即可，无需重复附图。本次安装未发起付费生成请求。")
        return 0
    except InstallError as exc:
        print("安装未完成：" + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print("操作中断（" + type(exc).__name__ + "）。保留原配置，请将此错误类型告知协助安装的人。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
