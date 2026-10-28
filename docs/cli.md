# 命令行参考

通常由 Codex 调用，使用者只需自然语言提出需求。成品包的启动器是 Mac `run.command` / Windows `run.cmd`；源码安装用 skill 的 `.venv` Python 执行 `scripts/apinebula_image.py`。以下以 Mac 成品启动器为例：

```sh
runner="$HOME/.agents/skills/apinebula-imagegen/run.command"
```

Windows PowerShell：

```powershell
$runner = Join-Path $env:USERPROFILE '.agents\skills\apinebula-imagegen\run.cmd'
& $runner --help
```

后续示例为 shell；PowerShell 改为 `& $runner`，参数含义不变。

## 隐藏配置密钥

```sh
"$runner" configure-key
```

由使用者在本机终端操作，不通过聊天接收密钥。可选私有 S3 使用 `configure-storage`，临时图床不需要这一步。

## 创建任务

先保存 UTF-8 提示词文件。文生图：

```sh
"$runner" submit --prompt-file prompt.txt --out-dir outputs/v1
```

本地参考图，在明确授权 tmpfiles.org 上传后：

```sh
"$runner" submit --prompt-file edit.txt --out-dir outputs/edit-v1 \
  --image /absolute/path/reference.png --upload-provider tmpfiles
```

默认 `--upload-provider s3`，因此只传 `--image` 时需要已配置私有 S3。不能在缺少 S3 时静默改走公开上传。

在线参考图：

```sh
"$runner" submit --prompt-file edit.txt --out-dir outputs/url-edit \
  --image-url 'https://example.com/reference.png'
```

`--image` 和 `--image-url` 可重复传多个。编辑父任务时不能混用这类显式参考图参数。

## 继续修改与指定版本

```sh
"$runner" submit --prompt-file next-edit.txt --out-dir outputs/v2 --continue
"$runner" submit --prompt-file alternative.txt --out-dir outputs/v1-alternative \
  --from-state outputs/v1/state.json
```

只有成功下载才更新本聊天的当前图。按 CODEX_THREAD_ID 隔离，同一工作目录的不同聊天也不共用图片；缺少该变量时，每次 submit 使用同一个聊天专属 `--session-file work/chat-a.json`，其他聊天必须换文件。

原任务下载链接不可取得时停止并保留本地文件，不自动退化成纯文生图或上传别的网站。

## 查询、恢复与清理

```sh
"$runner" status --state outputs/v2/state.json
"$runner" cleanup --state outputs/v2/state.json
```

status 查询同一任务并在完成后下载、验证图片；不要重复提交。cleanup 只在终止任务后执行：S3 删除本次记录的对象；tmpfiles 没有已核实的立即删除 API，仅报告自动到期。

通用 submit 参数：`--model`、`--quality low|medium|high|auto`、`--session-file`。各命令用 `--help` 查看精确参数。`--direct` 仅在诊断支持时用于单次关闭环境代理，不修改系统设置或 TLS 校验。

同一 out-dir 的状态文件采用独占创建，阻止重复任务。`submission_outcome_unknown` 且没有有效编号时，先查平台记录，不删状态换目录盲目重提。
