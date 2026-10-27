---
name: apinebula-imagegen
description: Generate or edit images through APINebula's asynchronous image API in Codex on macOS or Windows. Use when the user selects APINebula or invokes this skill; supports text prompts, image URLs, and local reference images via user-configured private S3-compatible storage.
---

# APINebula 异步绘图

使用随包的 `scripts/apinebula_image.py`，无需 Canva、OpenAI 官方密钥或其他绘图 skill。模型默认 `gpt-image-2.5`，是 APINebula 的模型标识，不等于独立核实了其上游模型。

## 首次使用

读取 [安装与配置](references/setup.md)。Python 3.10+；依赖装入 skill 自己的 `.venv`。macOS 使用 `.venv/bin/python`，Windows 使用 `.venv/Scripts/python.exe`；下文以 `PYTHON` 表示该解释器、`SCRIPT` 表示本 skill 内的脚本绝对路径，不把占位词原样执行。

API Key 从 `APINEBULA_API_KEY` 或用户目录下的独立密钥文件读取。让用户在自己终端运行 `configure-key` 隐藏输入；不要索取聊天中的完整密钥，不借用 OpenAI/Codex 登录凭证。每位使用者分别配置。

## 生成工作流

1. 按用户意图整理提示词，保留题材、风格、文字和参考图角色，保存 UTF-8 `prompt.txt`。未指定模型时用默认模型。若用户明确指定其他模型，按实际文档核实，不静默替换。
2. 根据输入选择参数；三种模式最终全部提交异步任务：
   - 文生图：无图片参数。
   - 在线参考图：`--image-url "https://..."`，可重复。
   - 本地参考图：`--image "绝对路径"`，可重复。先配置用户自己的私有 S3 兼容对象存储；脚本上传后生成临时 HTTPS 链接。**平台已实测拒绝 data URL；不要将 base64、本地路径、localhost 填入 image_url，不改走同步接口。** 没有存储时，完成提示词等准备，说明所需配置；不要擅自选择公开图床。
3. 提交一次，使用新的、语义明确的输出目录：

   ```text
   PYTHON SCRIPT submit --prompt-file "prompt.txt" --out-dir "output/imagegen/city-v1"
   PYTHON SCRIPT submit --prompt-file "prompt.txt" --out-dir "output/imagegen/edit-v1" --image "reference.png"
   ```

   文件路径在当前 shell 中正确引用。可加 `--quality low|medium|high|auto`。首次请求沿用系统代理；只有连接诊断支持时加 `--direct`，其作用仅限本次脚本，不修改系统代理或 TLS 校验。
4. 保存 `state.json` 中的任务编号；每隔约 15–30 秒查询一次：

   ```text
   PYTHON SCRIPT status --state "output/imagegen/city-v1/state.json"
   ```

   `queued`/`in_progress` 时继续查询同一任务，每次工具等待不超过 60 秒，并适时说明状态。`completed` 自动下载并验证原图。`failed` 汇报平台错误；不自动新建任务。等待约 10 分钟仍未结束时保留任务供恢复，清楚说明尚未完成，不承诺后台持续运行。
5. 检查返回图的实际内容、尺寸、格式，再用绝对路径内嵌图片并提供本地文件链接；报告模型标识和提示词文件。原图尺寸由平台决定，指定比例/尺寸可写入提示词，但不要承诺精确像素。需要转换或缩放时保存为另一文件。

## 中断、计费与文件

- 提交前独占创建状态文件；相同目录不重复提交。网络断开、非 JSON 响应或缺少任务编号意味着结果可能未知，保留状态，不以换目录/删除状态方式盲目重试。先查平台任务/用量记录，无法确认时告知用户。
- 查询和下载可重试，始终复用已获得的任务编号。请求成功不等于图片成功，只有下载并检查文件后才报告完成。
- 已有生成授权可执行正常提交；新一笔付费重试应按用户已有授权与失败信息判断，不能无限循环。脚本不自动重试 POST。
- 对象存储可能产生存储/流量费用；临时 URL 到期不会删除源文件。任务完成或失败后可运行 `cleanup --state ...` 删除本次上传的参考图，或使用用户配置的生命周期规则。先完成下载，再清理。
- 不覆盖正式产品资源，除非用户已授权替换。

接口字段、当前验证边界与错误排查见 [API 说明](references/api.md)。
