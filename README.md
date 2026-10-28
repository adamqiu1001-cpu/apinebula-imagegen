# APINebula ImageGen for Codex

在 Codex 中通过 APINebula 异步生成和修改图片。支持文字生成、本地参考图、网页图片直链，以及出图后直接描述修改需求，无需重复附图。默认模型为服务商标识 `gpt-image-2.5`；不代表已独立核实其上游模型。

## 给日常使用者

**成品安装包自带运行环境，不需要另装 Python。**每个人仍需已安装 Codex、联网，并配置自己的 APINebula 图片模型分组 API Key 和额度。

1. 从维护者取得与你系统对应的成品 ZIP，完整解压。
2. Mac 双击 `Install.command`；Windows x64 双击 `Install.cmd`。
3. 在弹出的本机终端隐藏输入自己的 API Key，回到 Codex 使用。

GitHub 的 **Code → Download ZIP 是源码，不是成品免安装包**。如果仓库尚未发布相应 Release 资产，请让维护者按下文打包；不要把源码 ZIP 当成成品运行。

| 情况 | 使用示例 |
|---|---|
| 纯文生图 | “用 apinebula-imagegen 生成一枚有太阳、白鸽和向日葵的珐琅徽章。” |
| 本地参考图 | 首次附图：“去掉飘带上的文字。允许将这张图临时上传到 tmpfiles.org 用于修图。” |
| 网页图片直链 | 粘贴可直接读取原图的 HTTPS 链接：“参考这张图，把背景改成白色。” |
| 出图后继续修改 | 在同一个聊天直接说：“把飘带改成深蓝色。”不用再次附图或链接。 |

- [完整使用说明](docs/user-guide.md)：首次安装、四种用法、连续修改、版本选择、密钥、任务恢复、升级和排错。
- [维护者：macOS 打包](docs/build-macos.md)
- [维护者：Windows 打包](docs/build-windows.md)
- [命令行参考](docs/cli.md)
- [维护者：直接上传 GitHub](docs/github-upload.md)：首次登录、Mac/Windows 安装、日常推送与权限排错，无需网页逐个上传。
- [实际验证范围](验证记录.md)

临时图床需要用户对图片和服务的授权：约一小时自动到期，持有直链者可访问。也可用自己的私有 S3 存储。继续修改已生成图片通常直接复用 APINebula 原任务链接，不需要图床或重新上传。实际出图按服务商计费。

## 给开发者：从源码安装

源码安装需要 Python 3.10+；维护和打包统一用 Python 3.13。源码用户可克隆仓库，再在根目录运行：

```sh
# macOS
python3 install.py
```

```powershell
# Windows PowerShell
py -3 install.py
```

默认安装到个人 `~/.agents/skills/apinebula-imagegen`。源码安装器创建独立 `.venv`、安装锁定依赖，拒绝覆盖已有同名目录；成品包的安装器则会先备份旧版本。配置命令详见[源码配置说明](apinebula-imagegen/references/setup.md)。**不要在聊天中发送 API Key。**

也可把本仓库链接交给 Codex，明确要求安装 `apinebula-imagegen/` 子目录、配置独立依赖，再引导你本机隐藏输入密钥。仅下载 skill 文件不等于完成运行环境安装。

## 从源码构建成品包

**Mac 在 Mac 上打包，Windows 在 Windows 上打包。**脚本主动拒绝跨系统打包。成品包接收者不需要 Python，负责打包的维护者需要 Python 3.13、Git 和网络。

Mac：

```sh
sh packaging/build-macos.sh
```

Windows PowerShell：

```powershell
powershell -NoProfile -File .\packaging\build-windows.ps1
```

脚本会创建 `.build/venv`，下载并校验固定版本的独立运行环境及锁定依赖，再输出 `dist/` 下的 ZIP 和 `.sha256`。Mac 包包含 Apple 芯片和 Intel 环境，Windows 包面向 Windows 10/11 x64。不会读取个人 APINebula 配置，不提交付费生图任务。详细前提、手动命令和验收步骤见两份打包说明。

项目不携带开发者签名、Apple 公证或 Windows Authenticode 证书。分发前按对应文档检查系统首次打开流程；发布包应说明实际测试过的平台，不能把模拟测试当成真机验证。

## 开发和验证

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r apinebula-imagegen/requirements.lock
.venv/bin/python -m unittest discover -s apinebula-imagegen/tests -v
.venv/bin/python -m unittest discover -s packaging/tests -v
```

Windows 用 `py -3.13 -m venv .venv`，后续改用 `.venv\Scripts\python.exe`。测试使用隔离文件和假凭证，不需要真实 API Key，不产生绘图费用。构建会校验运行环境的原图 PNG/JPEG/WebP 编解码和依赖导入。

源码结构：`apinebula-imagegen/` 为可安装 skill，`install.py` 为源码安装器，`packaging/` 为自带环境版准备、构建和安装工具，`docs/` 为完整使用和分平台打包文档。`requirements.lock` 固定日常依赖，`packaging/locks/` 固定各平台 wheel 哈希，`packaging/runtime-manifest.json` 固定独立运行环境及 SHA-256。

## 多电脑协作

- 每台电脑克隆同一个仓库，并执行一次 `git config --local pull.ff only`；Windows 可额外设 `git config --local core.longpaths true`。
- 开始工作前先提交本地修改，再 `git pull --ff-only`；分支有分歧时检查后再决定合并或变基。
- 使用 `codex/` 等功能分支和 Pull Request，保持 `main` 可用；切换电脑前推送已完成工作。
- `.build/`、`dist/`、虚拟环境、密钥、任务状态和用户图片留在本机，不提交到 Git。较大的成品 ZIP 应作为 Release 资产分发。

Codex skill 个人目录与调用方式见 [OpenAI 官方文档](https://developers.openai.com/codex/skills/)。本项目通过 APINebula 提供图像服务，不使用 Codex 登录凭据或 OpenAI 官方 API Key。
