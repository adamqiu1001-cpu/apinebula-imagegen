# APINebula ImageGen for Codex

在 macOS / Windows 的 Codex 中使用 APINebula 异步生成和编辑图片。默认服务商模型标识：`gpt-image-2.5`。

## 从 GitHub 安装

把本仓库链接发给 Codex，并说明：

> 请从这个 GitHub 仓库安装 `apinebula-imagegen` skill，技能目录是仓库根目录下的 `apinebula-imagegen/`。请放到当前用户的 `~/.agents/skills/apinebula-imagegen`，创建独立 Python 虚拟环境，安装该目录的 requirements.txt。安装完成后引导我在本机终端运行 configure-key，密钥由我隐藏输入，不在聊天中发送。

安装工具可能只下载 skill 文件，不一定安装依赖；上面的提示词明确包含依赖配置。私有仓库需要同事先取得仓库访问权限，并在自己的 Codex/GitHub 环境登录。

也可以下载或克隆本仓库，在仓库根目录执行：

- macOS：`python3 install.py`
- Windows PowerShell：`py -3 install.py`（或 `python install.py`）

安装器不会覆盖已存在的同名目录。安装后新开对话，输入：

> 使用 $apinebula-imagegen 画一张赛博朋克城市夜景，完成后显示图片。

## 配置和使用

每位使用者需要自己的 APINebula API Key。文生图及在线图片仅需 API Key；本地参考图默认临时上传到 tmpfiles.org，设置为一小时后由服务方自动删除，并在回复中告知使用者；有效期内持有直链者可访问。也可显式选择自己的私有 S3 兼容对象存储。连续修改本聊天已生成的图片优先复用原任务下载链接。

- [开始使用](开始使用.md)
- [详细安装与配置](apinebula-imagegen/references/setup.md)
- [Skill 指令](apinebula-imagegen/SKILL.md)
- [验证范围与限制](验证记录.md)

## 维护与更新

推荐为稳定版本创建 Git tag / Release，方便同事安装指定版本。升级时让 Codex比较当前安装版本和目标版本，保留本地修改并更新 skill 与依赖。已有配置保存在用户目录 `.config/codex-imagegen/`，不属于仓库；不要上传这些配置。

新增支持：新版 tmpfiles 展示页自动解析、本地参考图上传中断恢复、短时自动查询，以及已完成结果本机读取。`resume` 只恢复确定尚未提交的任务；结果未知或已有任务编号时继续查询，避免重复扣费。详见 Skill 指令。

此仓库不包含个人密钥、生成图片或产品源代码。第三方 API 与对象存储的用量由各自服务商计费。


## 开发与协作

日常使用支持 Python 3.10+；维护验证使用 `.python-version` 中的 Python 3.13。`requirements.lock` 固定本次验证过的依赖版本，`requirements.txt` 记录兼容范围。源代码脚本不需要编译；安装器只在本机创建独立虚拟环境，不提交依赖或生成图片。

```text
python -m venv .venv
python -m pip install -r apinebula-imagegen/requirements.lock
python -m unittest discover -s apinebula-imagegen/tests -v
```

以上 pip 和测试命令请使用刚创建的 `.venv` 解释器：macOS 为 `.venv/bin/python`，Windows 为 `.venv/Scripts/python.exe`，无需激活。

- 每台电脑克隆同一个仓库，并执行一次 `git config --local pull.ff only`。
- 开始工作前先提交本地修改，再执行 `git pull --ff-only`；出现分歧时检查两边变更，再选择合并或变基。
- 功能修改使用分支和 Pull Request，保持 `main` 可用。
- 切换电脑前推送完成的工作。
