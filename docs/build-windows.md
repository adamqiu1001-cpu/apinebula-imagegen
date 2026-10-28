# Windows 本机打包说明

这份说明给负责打包的维护者；同事使用最终包时不用安装 Python。**在 Windows 电脑上打包，不能在 Mac 上制作后宣称 Windows 已验证。**

## 前提

- Windows 10/11 **x64**，原生 PowerShell 和普通用户权限；本版不支持原生 ARM64 Windows。
- 安装 Git、Python 3.13 和 Python Launcher；`py -3.13 --version` 能工作。构建用 Python 与包中自带运行环境互相独立。
- GitHub Releases、raw.githubusercontent.com 和 PyPI 可访问；预留数 GB 磁盘空间。
- 不需要真实 APINebula Key；准备和构建不提交生图请求。

## 1. 获取源码

```powershell
git clone https://github.com/adamqiu1001-cpu/apinebula-imagegen.git
Set-Location apinebula-imagegen
git config --local pull.ff only
git config --local core.longpaths true
py -3.13 --version
```

源码使用 UTF-8；Git 的 `.gitattributes` 为 `.cmd` / `.bat` 设置 CRLF，shell/Python 代码用 LF。不要把维护者个人电脑路径或密钥写进脚本。

## 2. 构建

```powershell
powershell -NoProfile -File .\packaging\build-windows.ps1
```

如果本机策略不允许执行 `.ps1`，不要关闭策略或使用 Bypass；使用下面等价的逐条命令，或交给单位管理员按正常流程批准脚本：

```powershell
py -3.13 -m venv .build\venv
& .\.build\venv\Scripts\python.exe -B packaging\prepare.py windows
& .\.build\venv\Scripts\python.exe -B packaging\build_packages.py windows
```

每条命令成功后再运行下一条。脚本内部会检查返回码，失败即停止。

准备步骤下载清单固定的 Windows x64 CPython 独立环境（包含 python.exe 和运行 DLL），核对 SHA-256；按 `packaging/locks/windows-x64.txt` 校验并安装 CPython 3.13 / win_amd64 wheel。它不会使用维护者本机的 `.venv` 当作可分发运行环境。

构建复制仓库源码，生成 UTF-8 指令、CRLF 批处理入口、安装器与说明，真实运行 Windows 自带环境的导入、TLS CA 和 PNG/JPEG/WebP 编解码检查。结果为：

```text
dist\APINebula-Windows-x64.zip
dist\APINebula-Windows-x64.sha256
```

下载及依赖缓存位于 `.build\downloads`，暂存目录位于 `.build\packages`，均不上传 Git。更改依赖后更新 requirements.lock 与平台哈希锁定文件，并重新 prepare；不能只复制旧缓存冒充新构建。

## 3. 运行离线测试

```powershell
& .\.build\venv\Scripts\python.exe -m pip install -r apinebula-imagegen\requirements.lock
& .\.build\venv\Scripts\python.exe -B -m unittest discover -s apinebula-imagegen\tests -v
& .\.build\venv\Scripts\python.exe -B -m unittest discover -s packaging\tests -v
```

测试不读取真实 Key、不出图。部分 POSIX 文件权限测试在 Windows 自动跳过；Windows ACL 行为仍应在真实安装中验收。

## 4. 验收最终 ZIP

```powershell
Expand-Archive -LiteralPath .\dist\APINebula-Windows-x64.zip -DestinationPath '.build\解压 验收'
& '.\.build\解压 验收\APINebula-Windows-x64\runtime\windows-x64\python.exe' -I -B `
  '.\.build\解压 验收\APINebula-Windows-x64\installer.py' --check-package
```

建议先指定隔离目录安装，不改变自己已安装的 skill：

```powershell
& '.\.build\解压 验收\APINebula-Windows-x64\runtime\windows-x64\python.exe' -I -B `
  '.\.build\解压 验收\APINebula-Windows-x64\installer.py' `
  --target "$PWD\.build\隔离 安装\.agents\skills\apinebula-imagegen" --no-key
& '.\.build\隔离 安装\.agents\skills\apinebula-imagegen\run.cmd' --help
& '.\.build\隔离 安装\.agents\skills\apinebula-imagegen\runtime\python.exe' -I -B `
  -m unittest discover -s '.build\隔离 安装\.agents\skills\apinebula-imagegen\tests' -v
```

在实际同事环境继续检查：完整解压后双击 Install.cmd；隐藏输入自己的 Key；使用 `icacls` 确认密钥 ACL 已限制到当前用户；更新时保留 Key 并备份旧 skill；路径含空格、中文时正常；无需系统 Python 也能运行安装后的 `run.cmd`。这些操作不需要管理员权限。

如果 Defender、SmartScreen 或单位策略拦截，先核对来源与校验值，按正常审批处理，不关闭安全软件。当前包未做 Authenticode 签名。正式分发需签名时另行准备受信任证书，凭据存到合适的私密配置或 CI secrets，不能提交 Git。

## 5. 发布前记录

```powershell
Get-FileHash .\dist\APINebula-Windows-x64.zip -Algorithm SHA256
Get-Content .\dist\APINebula-Windows-x64.sha256
```

比对两个值；检查包内有 `BUILD-MANIFEST.json`、`verification.json`、许可证和使用说明。确认不含 Key、私人图、任务状态或本机配置。将实际 Windows 版本、架构、安装/升级/入口测试结果写入分发说明，不把 Mac 上的静态检查当成真机成功。

源码仓库当前记录的是 Mac 实机验证，**尚未执行 Windows 真机打包或安装**。到 Windows 电脑执行本文之后再更新验证记录。最终 ZIP 与校验值可作为 GitHub Release 资产分发，源代码 Git 不存成品与依赖。
