"""Build offline platform folders and ZIPs from checksum-verified inputs."""
import argparse
import platform
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
DOWNLOADS = ROOT / ".build/downloads"
STAGE = ROOT / ".build/packages"
OUTPUTS = ROOT / "dist"
SKILL_SOURCE = ROOT / "apinebula-imagegen"
SKILL_FILES = ["SKILL.md", "agents/openai.yaml", "scripts/apinebula_image.py",
               "references/api.md", "requirements.txt", "requirements.lock", "tests/test_workflow.py"]


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def packaged_skill(target):
    for name in SKILL_FILES:
        dst = target / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILL_SOURCE / name, dst)
    p = target / "SKILL.md"
    text = p.read_text(encoding="utf-8")
    before = "首次使用读 [安装与配置](references/setup.md)。使用本 skill 的 `.venv/bin/python`（macOS）或 `.venv/Scripts/python.exe`（Windows）。下文的 `PYTHON`、`SCRIPT` 是解释器和脚本绝对路径的占位说明，不要原样执行。密钥由用户在自己终端 `configure-key` 隐藏输入；不索取聊天中的完整密钥。"
    after = "首次使用读 [安装与配置](references/setup.md)。这是自带运行环境的版本，无需另装 Python 或运行 pip。安装后，macOS 用技能根目录的 `run.command`，Windows 用 `run.cmd` 调用；下文 `RUN` 代表该启动器的绝对路径，实际执行时正确引用路径。Mac 例：`\"/path/to/skill/run.command\" submit ...`；Windows PowerShell 例：`& \"C:\\path\\to\\skill\\run.cmd\" submit ...`。不要再寻找 `.venv`，不要改用系统 Python。密钥由使用者双击安装包里的 Configure-Key 文件在本机隐藏输入，或调用 `RUN configure-key`；不索取聊天中的完整密钥。"
    if before not in text:
        raise RuntimeError("Skill source changed; review portable instructions")
    text = text.replace(before, after).replace("PYTHON SCRIPT", "RUN")
    p.write_text(text, encoding="utf-8")
    (target / "references/setup.md").write_text("""# 自带环境版：安装与使用

本包已经包含对应系统的 Python 和全部依赖。无需另装 Python、运行 pip、申请 S3 或使用管理员权限。仍需已安装 Codex、网络连接，以及每位使用者自己的 APINebula 图片模型分组 API Key 和可用额度。

## 首次安装

1. 将 ZIP 完整解压到普通文件夹。不要在压缩软件预览里直接运行。
2. Windows 10/11 x64 双击 `Install.cmd`；macOS 11 及以上双击 `Install.command`。Mac 会按当前进程架构选择 Apple 芯片或 Intel 环境。
3. 安装器先离线验证自带依赖，再复制到个人目录 `.agents/skills/apinebula-imagegen`。已有版本备份到 `.agents/skill-backups/`，现有密钥不变。安装器不会发送出图请求。
4. 首次在弹出的本机终端隐藏输入自己的 API Key；输入时不显示字符。稍后配置或更换时双击 `Configure-Key.cmd` / `Configure-Key.command`。不要把密钥发到聊天中。
5. 回到 Codex，使用 `$apinebula-imagegen` 或明确说“用 apinebula-imagegen 生图”。若没有发现技能，重新启动 Codex。

个人密钥在 `~/.config/codex-imagegen/apinebula-api-key`，Windows 对应用户目录下相同路径，权限保护沿用原脚本。支持进程环境变量 `APINEBULA_API_KEY`，优先于密钥文件；改了文件但仍鉴权失败时检查是否有旧环境变量覆盖。不修改 Codex 登录或 OpenAI Key。

## 启动入口

macOS：技能根目录 `run.command`；Windows：`run.cmd`。启动器自动使用技能内 `runtime`，保留调用者工作目录以便聊天索引与输出保持一致。不要在命令中引用原下载目录；安装后只用个人技能目录的启动器。

所有原 CLI 参数保留：`submit`、`status`、`cleanup`、`configure-key`、`configure-storage`。如 `RUN submit --prompt-file edit.txt --out-dir outputs/v2 --continue`（RUN 应替换为实际启动器路径）。路径含空格或中文时正确引用。Windows PowerShell 用调用操作符 `&` 执行 `run.cmd`。

## 四种使用方式

- 纯文生图：描述内容，不加参考图参数。
- 本地参考图：首次附图，明确允许上传到 tmpfiles.org 后，用 `--image` 和 `--upload-provider tmpfiles`；该图床无需账户，约一小时自动到期，持有直链者可访问。也保留 `--upload-provider s3` 私有上传方案。
- 网页图片直链：用 `--image-url`；必须是可访问的图片地址，不能是需要登录的分享页或普通网页。
- 出图后继续修改：同一聊天直接说修改要求，用 `--continue`；指定旧版本用 `--from-state`，不要求重新附图。原任务可取得图片链接时无需图床。

## 验证、更新与排错

安装包中的 Check-Environment 文件只做离线依赖和图片读写检查，不验证 API Key，不联网或计费。安装器无法在对话内安全接收密钥时只完成安装，提示使用者双击 Configure-Key 文件。

若安装被系统拦截，先核对来源与 SHA-256，按所在系统的正常首次打开流程确认，不关闭系统安全保护。此包未提供开发者证书签名或 Apple 公证。Windows 包使用本机 x64 环境；ARM Windows 不在本次支持范围。Mac 包包含 arm64 和 x86_64，分别安装合适版本。

任务失败保留 state.json；有编号只查原任务，未知提交不盲目重试。不要为测试安装而自动发起付费生图。平台及网络兼容说明见 [API 说明](api.md)。
""", encoding="utf-8")


def shell_launcher(action):
    text = """#!/bin/sh
APINEBULA_PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
case "$(uname -m)" in
  arm64) APINEBULA_RUNTIME=macos-arm64 ;;
  x86_64) APINEBULA_RUNTIME=macos-x64 ;;
  *) echo "Unsupported Mac architecture."; exit 1 ;;
esac
"$APINEBULA_PACKAGE_DIR/runtime/$APINEBULA_RUNTIME/bin/python3" -I -B "$APINEBULA_PACKAGE_DIR/installer.py" ACTION
APINEBULA_RESULT=$?
if [ -t 0 ]; then
  printf '\\nPress Enter to close. '
  read -r APINEBULA_CLOSE
fi
exit "$APINEBULA_RESULT"
"""
    return text.replace("ACTION", action)


def cmd_launcher(action):
    text = ('@echo off\r\nsetlocal\r\nchcp 65001 >nul\r\n'
            '"%~dp0runtime\\windows-x64\\python.exe" -I -B "%~dp0installer.py" ACTION\r\n'
            'set "APINEBULA_RESULT=%ERRORLEVEL%"\r\necho.\r\npause\r\n'
            'exit /b %APINEBULA_RESULT%\r\n')
    return text.replace("ACTION", action).encode("ascii")


def guide(system):
    suffix = "cmd" if system == "Windows" else "command"
    platform_note = "Windows 10/11 x64；Windows ARM 不在本次支持范围" if system == "Windows" else "macOS 11 及以上的 Apple 芯片和 Intel"
    verification_note = "请以本包 verification.json 记录为准；打包检查不等于真实 API 出图已验证。"
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>APINebula 安装与使用</title><style>body{{font:17px/1.8 system-ui,sans-serif;max-width:860px;margin:50px auto;padding:0 24px;color:#243247;background:#f6f8fc}}h1{{font-size:32px}}section{{background:white;border:1px solid #dde4ee;padding:22px 28px;border-radius:14px;margin:22px 0}}code{{background:#eef3fa;padding:3px 7px;border-radius:4px}}table{{width:100%;border-collapse:collapse}}td,th{{text-align:left;vertical-align:top;border-bottom:1px solid #dde4ee;padding:12px}}small{{color:#526276}}</style>
<h1>APINebula · {system} 自带环境版</h1><p>不用安装 Python、不用输入安装命令。一次配置，之后在 Codex 里直接聊天生图。</p>
<section><h2>首次使用，只做这三步</h2><ol><li>先把 ZIP <strong>完整解压</strong>，不要从压缩包预览中运行。</li><li>双击 <code>Install.{suffix}</code>，等待显示“安装完成”。首次按提示隐藏输入你自己的 APINebula 图片分组 API Key。</li><li>回到 Codex，输入：<strong>用 apinebula-imagegen 生成一张有太阳、白鸽和向日葵的徽章图。</strong>若未识别技能，重新启动 Codex。</li></ol><p>已有密钥会保留；以后更换密钥，双击 <code>Configure-Key.{suffix}</code>。无需在聊天中发送密钥。</p></section>
<section><h2>四种使用方式</h2><table><tr><th>情况</th><th>你怎么说</th></tr><tr><td>1 · 纯文生图</td><td>“用 APINebula 生成一张海边日落插画，横向构图。”</td></tr><tr><td>2 · 本地参考图</td><td>首次把图片附到聊天：“去掉蓝色飘带上的文字。允许将这张图临时上传到 tmpfiles.org 用于修图。”</td></tr><tr><td>3 · 网页图片链接</td><td>粘贴可访问的原图直链：“参考这个图片链接，把背景改成白色，其他内容保留。”</td></tr><tr><td>4 · 出图后继续修改</td><td>在同一个聊天直接说：“把飘带改成深蓝色。”<strong>不必再次附图或贴链接。</strong>默认基于最近一张成功出图，也可以指定第一版。</td></tr></table><p><small>临时图床约一小时后自动到期，链接持有者可访问；上传需你授权。继续修改已有出图通常直接复用 APINebula 原任务图片，无需图床。</small></p></section>
<section><h2>环境检查与常见问题</h2><p>双击 <code>Check-Environment.{suffix}</code> 可做离线检查，<strong>不联网、不出图、不扣费</strong>。安装检查不代表 API Key 或服务额度有效；实际出图按 APINebula 计费。</p><p>本包仍需要已安装 Codex、网络和你自己的 APINebula Key。本包面向 {platform_note}。未提供开发者签名或 Apple 公证；若出现系统首次打开提示，核对来源和校验值后按系统正常流程确认，不必关闭安全保护。</p><p>升级时会备份原技能到个人 <code>.agents/skill-backups/</code>；你的密钥保存在技能目录以外，升级不覆盖。任务与原图请保留，以便继续修改。</p><p><small>验证状态：{verification_note} 详见包内 verification.json。</small></p></section>
<small>版本日期：2026-10-28 · 安装包不含任何人的 API Key、私人图片或出图记录。</small></html>"""


def build_folder(system, runtimes):
    name = "APINebula-Windows-x64" if system == "Windows" else "APINebula-macOS"
    root = STAGE / name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    packaged_skill(root / "skill")
    shutil.copy2(SOURCE / "installer.py", root / "installer.py")
    runtime_manifest = json.loads((DOWNLOADS / "runtime-manifest.json").read_text())
    shutil.copytree(DOWNLOADS / "runtime-licenses", root / "licenses/runtime")
    wheels = {}
    for target in runtimes:
        src = DOWNLOADS / ("runtime-" + target)
        shutil.copytree(src, root / "runtime" / target, symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        wheels[target] = [{"file": w.name, "sha256": checksum(w)}
                          for w in sorted((DOWNLOADS / ("wheels-" + target)).glob("*.whl"))]
    suffix = "cmd" if system == "Windows" else "command"
    for entry, action in [("Install", ""), ("Configure-Key", "--configure-key"),
                          ("Check-Environment", "--check-package")]:
        path = root / (entry + "." + suffix)
        if system == "Windows":
            path.write_bytes(cmd_launcher(action))
        else:
            path.write_text(shell_launcher(action), encoding="utf-8")
            path.chmod(0o755)
    (root / "先读我-安装与使用.html").write_text(guide(system), encoding="utf-8")
    (root / "BUILD-MANIFEST.json").write_text(json.dumps({"built_for": system, "runtimes": runtimes,
         "runtime_source": "https://github.com/astral-sh/python-build-standalone/releases/tag/20261026",
         "runtime_assets": runtime_manifest, "wheels": wheels,
         "skill_sha256": {f: checksum(root / "skill" / f) for f in SKILL_FILES}}, indent=2), encoding="utf-8")
    (root / "THIRD-PARTY-NOTICES.txt").write_text("""This distribution includes CPython from astral-sh/python-build-standalone.
Source: https://github.com/astral-sh/python-build-standalone/releases/tag/20261026
CPython license: runtime/*/lib/python3.13/LICENSE.txt (macOS), runtime/*/LICENSE.txt or Lib/LICENSE.txt (Windows).
Third-party Python package licenses are included in each runtime's site-packages, in the corresponding .dist-info directories.
Pillow's license file includes its bundled image-library notices. Runtime sources, asset SHA-256 values and wheel hashes are recorded in BUILD-MANIFEST.json.
No credentials, private reference images or task records are distributed.
""", encoding="utf-8")
    return root


def zip_folder(root):
    validate_distribution(root)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    output = OUTPUTS / (root.name + ".zip")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root.parent).as_posix()
            if path.is_symlink():
                item = zipfile.ZipInfo(relative)
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, os.readlink(path))
            elif path.is_file():
                z.write(path, relative)
    print(output.name, output.stat().st_size, checksum(output), flush=True)
    return output


def check_build_host(target, host=None):
    expected = {"windows": "Windows", "macos": "Darwin"}[target]
    if (host or platform.system()) != expected:
        raise ValueError(f"Build {target} on its native {expected} host; cross-platform packaging is disabled")


def validate_distribution(root):
    forbidden = {"apinebula-api-key", "apinebula-storage.json", "state.json", ".env", "download.part"}
    for p in root.rglob("*"):
        public_ca = (p.name == "cacert.pem" and p.parent.name in {"certifi", "botocore"}
                     and "runtime" in p.relative_to(root).parts)
        if p.name in forbidden or p.name.startswith(".env.") or (p.suffix in {".pyc", ".pem", ".key"} and not public_ca):
            raise ValueError("Personal, secret, task or cache file in distribution: " + p.name)
        if p.is_symlink():
            if not p.resolve().is_relative_to(root.resolve()):
                raise ValueError("Distribution symlink escapes package")


def main():
    parser = argparse.ArgumentParser(description="Build a native, offline APINebula distribution")
    parser.add_argument("target", choices=["macos", "windows"])
    args = parser.parse_args()
    check_build_host(args.target)
    targets = {"macos": ("macOS", ["macos-arm64", "macos-x64"]),
               "windows": ("Windows", ["windows-x64"])}
    root = build_folder(*targets[args.target])
    from installer import validate_runtime, runtime_name
    native = runtime_name(platform.system(), platform.machine())
    validate_runtime(root / "runtime" / native, platform.system())
    verification = {"date": "2026-10-28", "native_runtime_checked": native,
        "offline_codecs_checked": ["PNG", "JPEG", "WEBP"], "paid_requests": 0,
        "other_architectures": "not executed by this build", "code_signed": False,
        "notes": "Run the tests and fresh-extraction steps in docs/build-*.md before sharing."}
    (root / "verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    output = zip_folder(root)
    output.with_suffix(".sha256").write_text(checksum(output) + "  " + output.name + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
