# 安装与配置

官方技能发现说明：https://developers.openai.com/codex/skills/

## 环境与安装

Python 3.10+。macOS 用 `python3 --version` 检查；Windows 用 `py -3 --version` 或 `python --version` 检查。没有 Python 时从 https://www.python.org/downloads/ 安装官方版本；Windows 安装时启用 Python 命令/launcher。本包不依赖 bash、curl、Homebrew 或 PowerShell 的执行脚本策略。

解压分享包后运行其中的 `install.py`。默认目标是 `~/.agents/skills/apinebula-imagegen`，采用当前官方文档列出的个人技能发现位置。已有目标时停止，避免覆盖个人修改。

以下示例使用默认目录；若使用安装器的 `--destination` 自定义位置，请使用安装器实际输出，并确保该位置可被 Codex 发现。无需激活虚拟环境。

macOS Terminal：

```sh
skill_dir="$HOME/.agents/skills/apinebula-imagegen"
"$skill_dir/.venv/bin/python" "$skill_dir/scripts/apinebula_image.py" configure-key
```

Windows PowerShell：

```powershell
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\apinebula-imagegen'
& "$skillDir\.venv\Scripts\python.exe" "$skillDir\scripts\apinebula_image.py" configure-key
```

输入的是 APINebula 图片模型分组的 API Key，不是 Codex 登录密码或 OpenAI 官方 API Key。密钥保存在 `~/.config/codex-imagegen/apinebula-api-key`（Windows 为用户目录内同一路径）。macOS 文件权限 0600；Windows 创建文件后先用 `icacls` 关闭继承、授权当前用户，再写入密钥。若权限设置失败则停止，不写入密钥。它是限制权限的本地文件，不是加密保险库；勿同步/分享该配置目录。

也支持由使用者自己的凭证管理流程设置进程环境变量 `APINEBULA_API_KEY`，其优先级高于密钥文件。脚本不读取或更改 `OPENAI_API_KEY`，也不修改 Codex 的模型配置。

## 本地图片：配置私有 S3 兼容存储

这一步只在本地参考图选择私有 S3 上传时需要。连续修改本聊天的 APINebula 出图可直接复用原任务图片链接；无需配置 S3。普通非敏感参考图也可在用户授权后用免注册临时图床，见下一节。可使用支持 S3 API 的私有存储，例如 AWS S3 或 Cloudflare R2；其他服务需自行确认兼容签名 URL。脚本采用 path-style、SigV4，并要求 HTTPS。

1. 在你选择的存储服务里创建**私有桶**，不要开启公开访问。账号、付款、服务条款由使用者操作。
2. 创建仅能对该桶的 `codex-image-reference/` 前缀执行 PutObject、GetObject、DeleteObject 的专用凭证。不要使用管理员/root 密钥。
3. 记录 S3 API endpoint、region、bucket 和专用访问密钥。AWS 示例 endpoint 为 `https://s3.<region>.amazonaws.com`；R2 使用控制台提供的 S3 endpoint，region 通常为 `auto`。不要把控制台网页 URL 当成 endpoint。
4. 运行下面命令，依提示填写；访问密钥使用隐藏输入。

   macOS：
   ```sh
   "$skill_dir/.venv/bin/python" "$skill_dir/scripts/apinebula_image.py" configure-storage
   ```

   Windows：
   ```powershell
   & "$skillDir\.venv\Scripts\python.exe" "$skillDir\scripts\apinebula_image.py" configure-storage
   ```

5. 配置文件单独保存在 `~/.config/codex-imagegen/apinebula-storage.json`，采用与 API Key 相同的文件权限保护。不要发给同事。
6. 参考图以随机对象名上传，签名链接有效期 24 小时；临时链接持有人在有效期内可访问图片。任务结束后运行 `cleanup`，或在存储控制台给该前缀设置 1–2 天的自动删除规则。**链接到期不等于对象被删除**；存储与流量可能计费。

使用原始 PNG/JPEG/WebP，不自动压缩，单张辅助脚本上限 20 MiB。超过时先另存较小副本。没有存储配置时，脚本在付费生成请求之前停止。

## 不配置 S3：临时上传（可选）

先告知用户具体图片将交给 tmpfiles.org，取得对图片和服务的授权。该服务无需账户或 API Key，按其 API 文档设置 `expire=3600`（约一小时）；有效期内任何持有直链的人可读取，且没有已核实的立即删除接口。不要用于未获授权的私密图片。已有适用授权就直接执行，不要求用户每次重复确认同一范围。

```text
PYTHON SCRIPT submit --prompt-file "edit.txt" --out-dir "outputs/edit-v1" --image "reference.png" --upload-provider tmpfiles
```

脚本随机化上传文件名，识别网页地址与已经是直链的地址，下载核验原图字节后才提交编辑任务。不发送 APINebula Key 给图床，不在任务状态中记录临时链接。失败时保留状态，不自动切换服务或重复付费提交。

## 连续修改，不必再次附图

```text
PYTHON SCRIPT submit --prompt-file "next-edit.txt" --out-dir "outputs/edit-v2" --continue
```

在 Codex 中按 `CODEX_THREAD_ID` 自动隔离聊天，记录位于当前工作目录 `.apinebula/sessions/`。需要保留这个工作目录和任务文件。没有线程环境变量的终端/其他运行环境，在每次 submit 中加上同一聊天专属 `--session-file "work/chat-a.json"`；不同聊天不能共用。成功下载后该文件才选中新的当前图。

旧任务或指定版本可用 `--from-state "outputs/edit-v1/state.json"`，无需重新附图，也无需 S3。查询父任务获取新鲜下载链接，直接交给 APINebula 编辑接口，不记录带签名的 URL。父任务下载链接失效且无法重新取得时，再依据本地副本和用户已授权的上传方式处理。

## 手动执行示例

通常让 Codex 按 SKILL.md 执行即可。以下命令方便验证安装；先创建包含你需求的 UTF-8 `prompt.txt`，在自己的工作目录执行。

macOS：
```sh
"$skill_dir/.venv/bin/python" "$skill_dir/scripts/apinebula_image.py" submit --prompt-file "prompt.txt" --out-dir "output/imagegen/demo"
"$skill_dir/.venv/bin/python" "$skill_dir/scripts/apinebula_image.py" status --state "output/imagegen/demo/state.json"
```

Windows：
```powershell
& "$skillDir\.venv\Scripts\python.exe" "$skillDir\scripts\apinebula_image.py" submit --prompt-file "prompt.txt" --out-dir "output\imagegen\demo"
& "$skillDir\.venv\Scripts\python.exe" "$skillDir\scripts\apinebula_image.py" status --state "output\imagegen\demo\state.json"
```

本地图片在 `submit` 后加 `--image "图片绝对路径"`（默认私有 S3；临时图床额外加 `--upload-provider tmpfiles`）；在线图片加 `--image-url "https://..."`。两者均可重复传入，全部使用异步编辑接口。每次新生成用新目录；查询同一任务则继续使用原 state.json。

`status` 完成时自动下载真实格式的 `image.png`、`image.jpg` 或 `image.webp`，返回实际尺寸。`cleanup --state ".../state.json"` 只删除该状态文件记录的、已终止任务的 S3 参考图对象，不删除生成图片。对 tmpfiles 只提示自动到期，不伪报立即删除。

## 故障恢复

- 缺依赖：使用安装目录的虚拟环境解释器运行 `-m pip install -r "skill目录/requirements.txt"`。若安装器创建虚拟环境失败，使用 Python 的 `-m venv "skill目录/.venv"` 创建后安装依赖。
- 401/403：在平台核实密钥、分组和权限，用 `configure-key` 更新。环境变量已设置时先检查它是否覆盖了新文件。
- 额度不足或模型不可用：到服务商后台确认额度/图片分组。不要换成其他模型冒充成功。
- 代理/证书错误：保留 TLS 验证，先检查系统/企业代理及证书。确认能直连后可为命令加 `--direct`；这不会修改全局网络设置。
- `submission_outcome_unknown` 且无任务编号：不要再次提交。查平台任务/用量记录，确认是否已受理；本地超时不证明未计费。
- 已有任务编号：重复执行 `status`，无需重新生成；下载失败也只重复查询/下载。
- 长时间排队：保留 state.json 稍后继续。脚本一次查询不会在后台自动轮询。
- 私有存储授权/签名错误：核对 endpoint、region、桶名、桶权限和计算机时间。生成任务完成前保留参考图对象；链接过期时要先确认旧任务状态，不能盲目新建。
