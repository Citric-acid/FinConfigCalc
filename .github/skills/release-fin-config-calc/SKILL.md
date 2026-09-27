---
name: release-fin-config-calc
description: "自动发布 FinConfigCalc：更新版本、执行检查、提交推送并构建 Windows EXE。"
---

# FinConfigCalc 发布流程

当用户要求发布、升级版本或打包 FinConfigCalc 时，使用本技能。

## 必需信息

发布版本必须是明确的 `X.Y.Z` 格式。如果用户没有提供版本号，先从
`src/fin_config_calc/__init__.py` 的 `__version__` 读取当前版本，再询问目标版本。
不要自行推断应升级主版本、次版本或修订版本。

## 发布步骤

1. 运行 `git status --short`、`git diff --stat` 和 `git diff --cached --stat`。
2. 审阅所有将被提交的路径。发布脚本会暂存全部已跟踪和未跟踪的改动。如果发现无关文件、
   疑似密钥、未解决的冲突或生成产物，暂停并询问用户。
3. 根据已审阅的改动生成简洁的 Conventional Commit 风格摘要。类型标签使用英文小写，
   例如 `feat`、`fix`、`style`；冒号后的摘要内容必须使用中文。例如：
   `feat: 增加分摊预览`、`fix: 修复空映射处理`、`style: 完善发布文档`。向用户展示完整提交标题
   `release v<版本号>: <类型>: <中文摘要>`，并等待明确确认。用户要求修改时，重新生成并再次确认；
   未经确认不得运行发布脚本。
4. 在仓库根目录运行，并原样传入已确认的中文摘要：

   ```powershell
   .\.venv\python.exe scripts\release.py <版本号> --summary "<已确认的类型和中文摘要>"
   ```

5. 不要单独修改版本文件、提交、推送或调用 PyInstaller。发布脚本负责按顺序执行这些操作，
   任一步失败都会停止。
6. 报告发布版本、已推送的提交和分支，以及需要分发的完整
   `dist\FinConfigCalc-<版本号>` 目录。

## 流程保证

发布脚本会：

- 要求使用仓库本地的 `.venv\python.exe`；
- 要求新版本高于 `__init__.py` 中的当前版本；
- 更新唯一版本来源 `src\fin_config_calc\__init__.py`；
- 刷新 editable 安装元数据和打包依赖；
- 存在测试时运行 pytest，然后执行 Ruff 检查、格式检查和 Pyright；
- 创建标题为 `release v<版本号>: <已确认的类型和中文摘要>` 的提交，包含当前迭代的改动；
- 推送当前分支；如尚未设置 upstream，则为 `origin` 设置 upstream；
- 只有推送成功后才构建程序；
- 验证 `dist\FinConfigCalc-<版本号>\FinConfigCalc.exe` 存在。

如果任一步失败，说明具体失败阶段。只有发布命令成功退出且对应版本的 EXE 存在，才能确认发布成功。
终端输出中的 `发布完成` 是提示信息；如果输出被截断，不要求必须看到这行。不能仅凭文件存在判断成功，
因为它可能是之前尝试留下的旧产物。

## 重要说明

- 此流程不会创建 Git 标签或 GitHub Release。
- 提交前失败时，版本修改会保留在工作区，供诊断使用。
- 提交或推送后失败时，不要改写 Git 历史。修复构建原因后，从已推送的提交运行文档中说明的
  PyInstaller 命令；只有修复需要另一个提交时才使用新版本号。
- 分发整个版本目录，不要只分发 `FinConfigCalc.exe`。
