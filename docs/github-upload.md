# 直接上传 GitHub（无需网页上传文件）

维护者使用 Git 推送源码，用 GitHub 官方命令行工具 `gh` 完成登录和管理 Pull Request。首次登录可能需要在浏览器确认一次授权；日常上传无需打开 Chrome，也不用逐个选择文件。这些工具只用于维护源码，使用生图技能的同事无需安装它们。

## 每台电脑首次配置

先安装 Git 和 [GitHub CLI](https://cli.github.com/)，均不需要 Python。

- Windows：安装 [Git for Windows](https://git-scm.com/downloads/win)，再在 PowerShell 执行 `winget install --id GitHub.cli --exact`。
- macOS：已有 Homebrew 时执行 `brew install gh`；没有 Homebrew 时可从 [官方 Releases](https://github.com/cli/cli/releases/latest) 下载与你芯片对应的 macOS ZIP，解压后将其中的 `bin/gh` 放到自己的工具目录，使用完整路径运行。Git 可通过 `xcode-select --install` 安装。

安装后重新打开终端，确认 `git --version` 和 `gh --version`。手动安装且未加入 PATH 时，将下文 `gh` 换成可执行文件的完整路径。

```sh
gh auth login --hostname github.com --git-protocol https --web
```

按提示选择允许 Git 使用此登录，使用浏览器打开官方设备登录页面、输入一次性验证码，并核对账号后授权。`gh` 默认尝试将凭据存进系统凭据管理器；用 `gh auth status` 确认存储位置和账号。如果系统安全存储不可用，先修复它，不要将明文凭据文件提交到仓库。不要把令牌、密码或 API Key 发到聊天里。

首次克隆项目：

```sh
gh repo clone adamqiu1001-cpu/apinebula-imagegen
cd apinebula-imagegen
git config --local pull.ff only
git config --local core.quotepath false
```

Windows 再执行 `git config --local core.longpaths true`。已有本地仓库直接进入原目录，不要重新初始化或覆盖文件。确认 `git config user.name`、`git config user.email` 是自己的提交身份；它们与登录授权是两件事。

## 日常上传

可直接对 Codex 说：“检查修改和敏感文件，把本次源码上传到 GitHub，并创建或更新 Pull Request。”已完成本机登录后，Codex 可以直接推送。

手动操作时，先在干净工作区更新主分支、建立功能分支：

```sh
git switch main
git pull --ff-only
git switch -c codex/my-change
```

修改和验证后，先查看 `git status --short`、`git diff`，再把本次实际修改的文件加入暂存区，例如：

```sh
git add README.md docs/github-upload.md
git diff --cached
git commit -m "docs: explain direct GitHub uploads"
git push -u origin HEAD
gh pr create --base main --fill
```

将文件名、分支名和提交说明换成本次内容。继续更新同一个 Pull Request 时，留在对应分支，提交后执行 `git push` 即可，不用重复创建 Pull Request。已有未合并的功能分支应继续更新原分支，或明确选择后续工作的基准。

只上传源码和文档。`.build/`、`dist/`、虚拟环境、API 配置、任务状态、用户图片以及 GitHub 凭据不提交；成品 ZIP 通过 GitHub Release 分发。macOS 包在 Mac 上打包，Windows 包在 Windows 上打包。

## 遇到错误

- **403 / Permission denied**：先 `gh auth status` 核对账号，并确认该账号有仓库写入权限。旧凭据可能仍被 Git 使用；确认需要替换的账号后，再 `gh auth login`、`gh auth setup-git --hostname github.com`。连接器可读取仓库不代表它具备写入权限，连接器登录与本机 CLI 登录也相互独立。
- **连接 127.0.0.1 失败**：检查本机代理是否启动。`git config --show-origin --get-regexp proxy` 可查看 Git 的代理设置，终端环境也可能配置了代理。修正对应设置，不要为了排错关闭 HTTPS 证书验证。
- **non-fast-forward / 分支有分歧**：先 `git fetch origin`，查看双方提交后再决定合并或变基。不要强制推送或丢弃本地修改。尤其不要把网页上传产生的提交覆盖成另一套本地历史。
- **安全存储提示或无法保存登录**：检查系统钥匙串或凭据管理器；不要使用 `--insecure-storage` 作为默认解决方案。

每台电脑各自登录一次；不要复制他人的凭据。上传成功后可用 `git status --short --branch`、`git log -1 --oneline` 以及仓库页面核对本地和远端结果。
