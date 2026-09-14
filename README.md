# FinConfigCalc

FinConfigCalc 是一款面向企业财务管理报表加工场景的本地数据处理工具。财务人员通过Excel参数表配置
加工规则，即可将多个上游系统导出的数据自动处理成口径统一、可供分析的明细底表。

## 管报是怎样加工出来的

一张管理报表从源系统数据到最终展示，通常会经历三个阶段：

```mermaid
flowchart LR
	A["1. 上游数据<br/>财务系统 / 业务系统 / 预算系统<br/>导出 Excel 明细"]
	B["2. 管报明细加工<br/>清洗 / 映射 / 聚合 / 比对 / 分摊<br/>形成完整、统一的管报明细表"]
	C["3. 汇总呈现<br/>BI 看板 / Excel 报表<br/>分析指标与管理展示"]

	A --> B --> C

	classDef source fill:#e8f1f5,stroke:#477383,color:#172b33,stroke-width:1px;
	classDef scope fill:#e7f4e4,stroke:#39733c,color:#183b1a,stroke-width:3px;
	classDef presentation fill:#f7efe0,stroke:#9b6b24,color:#452f10,stroke-width:1px;
	class A source;
	class B scope;
	class C presentation;
```

### 1. 上游数据

数据来自财务系统、业务系统、预算系统或其他上游平台。实际工作中，财务人员通常先从各系统
分别导出 Excel：总账明细、费用明细、订单、组织架构、科目表、预算数据、分摊因子等。这些
文件的字段、粒度和编码口径往往并不统一，还不能直接用于管理分析。

### 2. 管报明细加工

这一阶段需要统一各来源 Excel 的字段、粒度和业务口径，并保留可追溯的业务明细。传统做法
通常包含大量重复的 Excel 操作：

- 用 `VLOOKUP`、`XLOOKUP` 等公式完成科目、组织、产品线和考核口径映射；
- 用透视表或分类汇总按主体、期间、科目等维度进行分组聚合；
- 用 `SUMIFS`、辅助列或手工勾稽比对不同来源的数据；
- 用公式按照人数、收入、面积或其他因子分摊公共费用；
- 合并多个文件，筛选数据，统一字段名，补充固定列，并将宽表转换成长表；
- 反复检查公式范围、映射遗漏、金额差异和最终数据行数。

**这正是 FinConfigCalc 的项目范围。** 财务人员将映射、筛选、聚合、比对、分摊等规则写入
Excel 参数表，工具便可按既定顺序自动执行。规则验证通过后，后续期间只需替换源数据或调整
少量参数即可重复运行。

### 3. 汇总呈现

明细加工完成后，财务分析师可通过成熟的BI工具或Excel制作损益表或经营看板，FinConfigCalc 不处理这一阶段。

## 工具带来的价值

手工加工的步骤多且每月重复，公式范围、筛选状态、文件版本或操作习惯都可能影响结果。
FinConfigCalc 将已经明确的加工规则沉淀下来并稳定执行：

- **减少重复操作**：一次配置读取、筛选、映射、汇总和输出步骤，以后按相同顺序重复运行。
- **沉淀管理口径**：将科目归类、组织映射、字段标准化和分摊因子从临时公式转为配置文件。
- **降低手工差错**：调度执行前检查必填列、步骤顺序和参数格式；某一步失败后立即停止，避免
-  带错继续加工。
- **让过程更容易复核**：运行界面展示每一步的状态、耗时、输入输出行数和结果路径，日志可一键
-  复制，便于定位问题。
- **提高月结复用效率**：期间、路径或规则变化时，只需调整参数即可复用既有流程。
- **数据留在本机**：工具可离线运行，业务数据无需上传到外部服务。

> FinConfigCalc 负责执行规则，不替代财务判断。业务口径、源数据完整性和最终结果仍需人工确认。

## 如何使用

### 方式一：运行 EXE

适合直接执行管报任务的财务用户，不需要安装 Python 或项目依赖。

1. 获取打包后的完整 `FinConfigCalc` 文件夹。
2. 不要改变文件夹内的目录结构，也不要只复制其中的 EXE。
3. 双击以下程序启动调度界面：

```text
FinConfigCalc\FinConfigCalc.exe
```

程序使用终端界面。系统安装了 Windows Terminal 时会自动使用它，以改善中文和等宽字体显示；
未安装时仍可在传统控制台中运行。工具本身不要求联网。

### 方式二：源码调用

适合开发、调试或需要修改处理逻辑的用户。当前项目按 Windows 环境维护，源码运行需要：

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 或 Windows 11 |
| Python | 3.12 或更高版本，本项目以 3.12 为基准 |
| 环境管理 | Miniconda 或 Anaconda |
| 网络 | 首次安装依赖时需要，运行管报任务时不需要联网 |

#### 1. 获取代码

使用 Git 克隆仓库：

```powershell
git clone https://github.com/Citric-acid/-FinConfigCalc.git
Set-Location .\-FinConfigCalc
```

也可以下载源码压缩包并解压，然后在 PowerShell 中进入包含 `pyproject.toml` 的项目根目录。

#### 2. 创建项目环境

在项目根目录创建 Python 3.12 环境。`--prefix .venv` 会将环境放在当前项目内，避免与其他
Python 项目相互影响：

```powershell
conda create --prefix .venv python=3.12 pip -y
```

如果命令提示找不到 `conda`，请先安装 Miniconda 或 Anaconda，再重新打开 PowerShell。仓库中
已经存在可用的 `.venv` 时，可以跳过此步骤。

#### 3. 安装项目

始终使用项目环境中的 Python 安装依赖：

```powershell
.\.venv\python.exe -m pip install --upgrade pip
.\.venv\python.exe -m pip install -e .
```

#### 4. 验证环境

```powershell
.\.venv\python.exe --version
.\.venv\python.exe -c "import fin_config_calc, polars, textual; print('环境安装成功')"
```

第一条命令应显示 Python 3.12，第二条命令应输出“环境安装成功”。

#### 5. 启动工具

通过 Python 模块启动与 EXE 版本相同的调度界面：

```powershell
.\.venv\python.exe -m fin_config_calc.ui
```

源码方式和 EXE 方式使用相同的调度表、功能参数和执行流程。本项目的解释器位于
`.venv\python.exe`；不要使用 `.venv\Scripts\python.exe`、系统 Python 或全局安装的工具。

### 准备调度表

调度表是一个 `.xlsx` 文件，默认工作表名称为“调度”。每一行代表一个处理步骤：

| 列名 | 是否必填 | 作用 |
| --- | --- | --- |
| `order` | 是 | 唯一数值，决定步骤执行顺序，例如 `10`、`20`、`30` |
| `function` | 是 | 要执行的处理功能，例如 `service.standardize_columns` |
| `params` | 是 | JSON 对象，填写该步骤的输入文件、规则文件、输出文件及其他参数 |
| `enabled` | 是 | `Y` 表示执行，`N` 或空值表示跳过 |
| `comments` | 否 | 用业务语言说明步骤目的，会显示在预览和运行日志中 |

示例：

```text
order:    10
function: service.filter_by_conditions
params:   {"input_file_path":"D:/finance/detail.xlsx","input_sheet_name":"明细","conditions":{"period":"202601"},"output_file_path":"D:/finance/output/filtered.parquet"}
enabled:  Y
comments: 筛选 2026 年 1 月实际明细
```

在 JSON 参数中，Windows 路径建议使用 `/`，例如 `D:/finance/detail.xlsx`，以避免反斜杠转义问题。

### 预览并执行

1. 在“调度表路径”中输入 Excel 文件的完整路径。
2. 确认“调度表名称”，未修改时默认为“调度”。
3. 点击“预览任务步骤”，检查启用的功能、顺序和备注。
4. 关闭正在打开的同名输出 Excel，再点击“执行调度”。
5. 根据进度和日志检查每一步的 `START`、`DONE`、处理行数及输出路径。
6. 执行完成后复核关键汇总数、差异结果和最终报表。

界面中的“使用说明”会打开随程序提供的完整用户手册，其中包含全部功能的参数、示例和常见
问题；源码中的同一份手册位于 [src/fin_config_calc/ui/user_guide.html](src/fin_config_calc/ui/user_guide.html)。

## 使用时要特别注意

- **先用小样本验证**：新映射、新分摊因子或新数据源上线前，先用少量脱敏数据核对结果。
- **保留勾稽检查**：对关键金额设置汇总对账步骤，并在交付前核对源数据总额、加工后总额和差异。
- **关闭输出文件**：Excel 正在占用同名文件时，程序通常无法写入。
- **失败后检查已生成文件**：任一步骤失败都会中止后续步骤，但不会自动删除此前已经输出的文件。
- **谨慎使用原位更新**：`append_with_overwrite` 会直接更新存量文件，首次使用或变更条件前应备份。
- **妥善维护配置**：调度表、映射表、元数据和分摊因子共同构成管理口径，建议按期间或版本归档。
- **反馈前先脱敏**：日志、配置和样本中可能包含路径或业务信息，对外发送前请移除敏感数据。

当前版本采用本地文件和线性步骤调度，不包含参数审批、权限控制、多人并发、集中式任务平台、
自动回滚或完整的数据版本管理。输入支持 `.xlsx`、`.xlsm` 和 `.parquet`，输出支持 `.xlsx` 和
`.parquet`。

## 技术框架

FinConfigCalc 使用 Python 3.12 开发，核心组件如下：

| 组件 | 用途 |
| --- | --- |
| Polars | 内存中的表格数据清洗、关联、汇总、转换和计算 |
| openpyxl | 读取和生成 Excel 工作簿及差异报表 |
| Textual / Rich | 提供本地终端界面、进度和日志展示 |
| Loguru | 记录各处理步骤的运行信息 |
| PyInstaller | 构建可分发的 Windows 目录版程序 |
| pytest / Ruff / Pyright | 测试、代码检查和类型检查 |

项目采用 `src` 布局和单向依赖：

```text
ui -> service -> utils
```

- `src/fin_config_calc/ui`：调度界面和内置用户手册；
- `src/fin_config_calc/service`：面向财务场景的处理步骤；
- `src/fin_config_calc/utils`：通用 DataFrame、文件读写和调度执行工具；
- `tests/unit`：底层工具与单项服务测试；
- `tests/integration`：从输入文件到输出结果的集成测试；
- `templates`：预留的参数模板目录。

## 本地开发

完成上述源码环境安装后，如需运行测试和代码检查，再安装开发依赖：

```powershell
.\.venv\python.exe -m pip install -e ".[dev]"
```

运行测试和质量检查：

```powershell
.\.venv\python.exe -m pytest
.\.venv\python.exe -m ruff check .
.\.venv\python.exe -m ruff format --check .
.\.venv\python.exe -m pyright
```

项目编码约定见 [docs/coding-standards.md](docs/coding-standards.md)。

## 构建 Windows 程序

安装项目及打包依赖：

```powershell
.\.venv\python.exe -m pip install -e ".[build-exe]"
```

从仓库根目录构建：

```powershell
.\.venv\python.exe -m PyInstaller --clean --noconfirm fin-config-calc.spec
```

构建结果位于：

```text
dist\FinConfigCalc\FinConfigCalc.exe
```

Textual 运行在终端中，因此不能使用 PyInstaller 的 `--windowed` 模式。分发时必须复制整个
`dist\FinConfigCalc` 目录；目录版也更适合 Polars 等包含原生依赖的组件。

