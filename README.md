# FinConfigCalc

通过 Excel 参数表配置数据读取、清洗、映射、转换和分摊，用于生成财务管理报表。

## 目录

- `src/fin_config_calc/utils`：通用数据处理工具。
- `src/fin_config_calc/service`：参数解析、处理步骤、执行编排和审计。
- `src/fin_config_calc/ui`：预留的用户界面包，暂不绑定具体框架。
- `tests`：单元测试和集成测试。
- `templates`：Excel 参数模板。

## 运行调度界面

安装项目后，通过 Textual 界面选择要执行的 Excel 调度表：

```powershell
.\.venv\python.exe -m fin_config_calc.ui
```

在“调度表路径”中输入 `.xlsx` 或 `.xlsm` 文件路径，确认工作表名称后点击“执行”。
工作表名称默认为“调度”，执行结果或错误信息会显示在界面日志中。

安装生成的命令入口也可以直接启动界面：

```powershell
.\.venv\Scripts\fin-config-calc.exe
```

## 构建 Windows EXE

项目使用 PyInstaller 生成带控制台窗口的 Windows 目录版应用。Textual 运行在终端中，
因此不能使用 PyInstaller 的 `--windowed` 模式。

先安装项目及打包依赖：

```powershell
.\.venv\python.exe -m pip install -e ".[build-exe]"
```

再从仓库根目录执行构建：

```powershell
.\.venv\python.exe -m PyInstaller --clean --noconfirm fin-config-calc.spec
```

构建完成后双击以下文件即可打开调度界面：

```text
dist\FinConfigCalc\FinConfigCalc.exe
```

打包版在 Windows Terminal 可用时会自动使用它承载界面，以改善中文和等宽字体的渲染；
字体可在 Windows Terminal 设置中按需调整。系统未安装 Windows Terminal 时，程序仍会在
传统控制台中正常运行，但字体外观取决于该控制台的配置。

分发时需要复制整个 `dist\FinConfigCalc` 目录，不能只复制其中的 EXE。
目录版比单文件版启动更快，也更适合本项目包含的 Polars 等原生依赖。
