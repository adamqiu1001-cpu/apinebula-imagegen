# macOS 本机打包说明

这份说明给**负责制作成品包的维护者**。最终同事使用成品包时不需要 Python。

## 前提

- 在 macOS 上操作，推荐 macOS 11 或以上；不要在 Windows 上交叉制作 Mac 包。
- 安装 Git 和 Python 3.13（含 pip/venv）；`python3 --version` 应为 3.13.x。使用其他命令名时，通过 `APINEBULA_BUILD_PYTHON` 指定其绝对路径。
- 网络能访问 GitHub Releases、raw.githubusercontent.com 与 PyPI。
- 需要数 GB 空间存放缓存、两个架构运行环境、暂存目录与压缩包。
- 打包不需要 APINebula Key，不需要服务商额度，不会出图。

## 1. 克隆与检查

```sh
git clone https://github.com/adamqiu1001-cpu/apinebula-imagegen.git
cd apinebula-imagegen
git config --local pull.ff only
python3 --version
```

源码修改使用功能分支。打包已经检查过的 commit，记录 `git rev-parse HEAD` 方便追溯。

## 2. 一条命令构建

```sh
sh packaging/build-macos.sh
```

以上命令无需依赖脚本可执行位，也无需修改系统设置。

该入口会：

1. 创建仓库内 `.build/venv`，供维护者运行构建工具。
2. 根据 `packaging/runtime-manifest.json` 获取固定的 CPython 3.13.18 独立运行环境，分别为 Apple arm64 与 Intel x86_64；核对 SHA-256。
3. 根据 `packaging/locks/macos-*.txt` 下载平台 wheel，用 `--require-hashes` 校验，并装入对应独立环境。保存许可证和来源信息。
4. 复制仓库 `apinebula-imagegen/` 源码，生成适配自带环境的 skill 指令、安装器与双击入口；不会读取个人已安装 skill 或密钥。
5. 对当前架构实际执行导入、TLS CA 和 PNG/JPEG/WebP 编解码检查，再生成 ZIP、校验文件和包内验证记录。

最终文件：

```text
dist/APINebula-macOS.zip
dist/APINebula-macOS.sha256
```

包中同时含两种 Mac 架构，安装时仅复制对应架构。Apple 芯片机器若终端通过 Rosetta 运行，选中的是当前进程的 x86_64 环境；推荐原生终端运行。自动构建只验证当前可执行架构，不声称 Intel 已运行。

## 3. 需要分步排查时

```sh
python3 -m venv .build/venv
.build/venv/bin/python -B packaging/prepare.py macos
.build/venv/bin/python -B packaging/build_packages.py macos
```

下载在 `.build/downloads/`，中间成品在 `.build/packages/APINebula-macOS/`。这些目录不入 Git。重跑 prepare 会重新展开固定运行环境、重新安装锁定依赖；缓存完好的下载可复用。仅重新复制源码出包可运行 build；但依赖变动时必须重新 prepare。

## 4. 分发前验收

先在源码环境运行测试：

```sh
.build/venv/bin/python -m pip install -r apinebula-imagegen/requirements.lock
.build/venv/bin/python -B -m unittest discover -s apinebula-imagegen/tests -v
.build/venv/bin/python -B -m unittest discover -s packaging/tests -v
```

然后使用系统解压器或 `ditto` 解压**最终 ZIP**到新的路径，最好含中文和空格：

```sh
ditto -x -k dist/APINebula-macOS.zip '.build/解压 验收'
'.build/解压 验收/APINebula-macOS/Check-Environment.command'
```

检查双击入口的执行权限和 runtime 软链接保留。仅做隔离安装时可用包内对应架构的 Python：

```sh
'.build/解压 验收/APINebula-macOS/runtime/macos-arm64/bin/python3' -I -B \
  '.build/解压 验收/APINebula-macOS/installer.py' \
  --target "$PWD/.build/隔离 安装/.agents/skills/apinebula-imagegen" --no-key
```

Intel Mac 把 `macos-arm64` 改为 `macos-x64`。确认新安装的 `run.command --help` 可执行，并可用安装目录 `runtime/bin/python3 -I -B -m unittest discover -s <安装目录>/tests -v` 跑全部工作流测试。

还应在实际接收者环境验收 Finder 双击 Install、隐藏输入自己的 Key、升级保留 Key、备份旧 skill、失败不替换旧安装。不要把测试 Key 放进源码或包；构建检查不需要真实 Key。真实生图若要验证，另行明确授权费用并记录结果。

有 Intel 真机或已经由使用者配置好的 Rosetta 才能执行 x86_64 验证；没有则在分发说明中明确未运行。不要为测试静默安装 Rosetta。

## 5. 校验与发布

```sh
(cd dist && shasum -a 256 -c APINebula-macOS.sha256)
```

确认包内有 `BUILD-MANIFEST.json`、`verification.json`、许可证、安装说明，没有个人 Key、签名链接、state.json 或私人图片。按测试结果维护验证说明。

ZIP 和 `.sha256` 作为 GitHub Release 资产上传，不提交进源码 Git。当前工具不执行发布、签名或 Apple 公证；没有签名时说明 macOS 可能要求首次打开确认。需要正规开发者签名和公证时由维护者另外配置 Apple Developer 证书，凭据不要进仓库。
