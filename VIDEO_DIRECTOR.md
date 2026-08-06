# Skill 44 提交包与录屏导演稿

## 一、参考产物是什么形式

参考文件 `D:\ADownloads\skill-buffett-moat-screener.zip` 是一个完整 BUILD 交付包：

| 项目 | 参考包内容 |
|---|---|
| ZIP 大小 | 52,384,986 bytes，约 50 MB |
| 文件条目 | 725 |
| 代码入口 | `SKILL.md`、`skill.json`、`scripts/` |
| 说明材料 | `README.md`、`references/`、`LICENSE` |
| 生产结果 | `生产产物/数据库.parquet`、回测 JSON、PNG、HTML |
| 演示结果 | `output/demo_result.json`、`output/demo_report.html` |
| 演示视频 | 根目录 `demo.mp4` |
| 视频规格 | 1920×1080、H.264 + AAC、3:39、约 24.9 MB |

它的视频是普通屏幕录制：先在 IDE 中介绍 SKILL 和 JSON，再打开本地 HTML 研究报告、回测曲线和明细表，最后回到文档总结边界。

参考包不能原样模仿的部分：

- 包含 412 个 PandaData 缓存 Parquet；
- 包含 73 个 `__pycache__/*.pyc`；
- 项目目录被重复嵌套了一次；
- Playwright 临时日志和截图也被打包；
- 体积主要来自缓存、重复生产文件和视频，而不是 Skill 源码。

我们的上传包应保留相同的核心交付形式，但删除缓存、编译文件、临时截图和重复目录。

## 二、我们的上传包结构

```text
skill-buffett-moat-screener/
├── SKILL.md
├── skill.json
├── README.md
├── README.en.md
├── VIDEO_DIRECTOR.md
├── CHANGELOG.md
├── LICENSE
├── requirements.txt
├── requirements-dev.txt
├── lavine_buffett/
├── scripts/
├── tests/
├── references/
├── production/
│   ├── SKILL.md
│   └── database.parquet
├── output/
│   └── screen-20251231-all-sh-sz-v12.json
└── demo.mp4                    # 录制完成后通过 -DemoPath 加入
```

禁止放入上传包：

- `output/panda-cache/`；
- `.git/`、`.pytest_cache/`、`__pycache__/`；
- `.env`、账号、密码、token；
- 旧版全市场结果和临时测试输出；
- Playwright session metadata；
- 重复嵌套项目目录。

## 三、打包命令

未录视频时先生成源码与生产结果包：

```powershell
Set-Location D:\Codex-Workspace\PandaAI\skill-buffett-moat-screener-lavine-version

powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1 `
  -OutputPath D:\ADownloads\skill-buffett-moat-screener-v2.0.0.zip
```

录制完成后，把视频保存为 `D:\ADownloads\demo.mp4`，重新生成最终上传包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_release.ps1 `
  -OutputPath D:\ADownloads\skill-buffett-moat-screener-v2.0.0.zip `
  -DemoPath D:\ADownloads\demo.mp4
```

打包脚本从 Git 当前提交生成源码，并额外加入 canonical JSON、production Parquet 和可选视频。它不会打包缓存和凭据。

## 四、录制规格

### 推荐软件

- 录屏：OBS Studio；已经安装 EV 录屏也可以使用。
- 浏览器：Microsoft Edge 或 Google Chrome。
- 代码与终端：Visual Studio Code。
- Markdown：VS Code 内置 Markdown Preview，快捷键 `Ctrl+Shift+V`。
- JSON：VS Code 直接打开并折叠节点。
- Parquet：不要安装额外查看器，使用项目自带 validator 和 Python 命令展示。

### 画面参数

| 参数 | 建议 |
|---|---|
| 分辨率 | 1920×1080 |
| 帧率 | 30 fps |
| 编码 | H.264 视频、AAC 音频 |
| 时长 | 2:40 至 3:10 |
| 浏览器缩放 | 110% 至 125% |
| VS Code 字号 | 18 至 20 px |
| 鼠标 | 慢速移动，点击后停留约 1 秒 |

录制前关闭通知、聊天窗口和密码管理器弹窗。不要展示 PandaData 环境变量值、缓存目录内容或任何 token。

## 五、录制前准备

### 浏览器预开页面

1. GitHub 项目主页：
   `https://github.com/lavine888/skill-buffett-moat-screener`
2. GitHub Actions：
   `https://github.com/lavine888/skill-buffett-moat-screener/actions`

浏览器只保留这两个标签页，关闭书签栏和无关标签。

### VS Code 预开文件

用 VS Code 打开目录：

```text
D:\Codex-Workspace\PandaAI\skill-buffett-moat-screener-lavine-version
```

按以下顺序预开标签：

1. `README.md`，打开 Markdown Preview；
2. `SKILL.md`；
3. `lavine_buffett/rules.py`；
4. `lavine_buffett/panda_client.py`；
5. `output/screen-20251231-all-sh-sz-v12.json`；
6. VS Code 集成 PowerShell 终端。

### 终端预置

先运行一次，确保录制时不会遇到意外：

```powershell
python -m pytest -q
python scripts/validate.py output/screen-20251231-all-sh-sz-v12.json
python scripts/validate.py production/database.parquet
```

录制时只重复这些离线命令，不要现场请求 PandaData。

准备一条 production 摘要命令，录制时直接粘贴：

```powershell
python -c "import pandas as pd; f=pd.read_parquet('production/database.parquet'); print(f[['symbol','status','signal','score','rank']].query('status == \'pass\'').sort_values('rank').to_string(index=False)); print(f'\nrows={len(f)}, columns={len(f.columns)}, duplicate_keys={f.duplicated([\'trade_date\',\'factor_id\',\'symbol\']).sum()}')"
```

## 六、分镜与口播

目标时长：约 2 分 55 秒。全程屏幕录制，不需要摄像头画中画。

| 时间 | 打开什么 | 画面动作 | 口播 |
|---|---|---|---|
| 00:00-00:12 | GitHub 项目主页 | 停在 README 首屏，缓慢划过名称、版本、CI 徽章 | “这是我为量枢院第 44 号任务实现的 Buffett Moat Screener。它使用 PandaData，对沪深 A 股执行严格的 point-in-time 护城河硬筛选。” |
| 00:12-00:30 | GitHub README | 滚到“项目定位” | “这个版本不是软评分。只有全部适用条件通过才会入选；数据缺失、冲突或历史不可见时会直接拒绝推断。” |
| 00:30-00:50 | GitHub README | 滚到 Mermaid 工作流程 | “输入是决策日期和当时股票池。系统分别取得财报版本、行业归属和价格，再计算十年 ROE 或 ROA、毛利率、资本开支、债务和 TTM PE。” |
| 00:50-01:08 | GitHub README | 滚到普通公司与银行规则表 | “普通公司使用 ROE、毛利率、资本开支和债务规则。银行走独立 ROA 分支，避免把工业企业口径错误套到银行。” |
| 01:08-01:25 | VS Code `SKILL.md` | 展示 Core Workflow 和 Output Contract，不快速滚动 | “SKILL 文件冻结了执行步骤和输出契约。每只股票都返回 pass、fail 或 insufficient_data，并保留具体检查和证据日期。” |
| 01:25-01:42 | VS Code `rules.py` | 定位 `screen_symbol`，展示银行分支和 checks | “规则引擎坚持 fail closed。已知负利润或负 EPS 属于明确失败；只有原始证据缺失才属于数据不足。” |
| 01:42-01:57 | VS Code `panda_client.py` | 展示 `fetch_reports` 和 `fetch_industries` | “数据层按公告日选择历史版本，并对请求做节流、并发和原子缓存。缓存还绑定 SDK、接口环境和响应哈希，便于复现。” |
| 01:57-02:12 | VS Code 终端 | 运行 JSON validator，再运行 Parquet validator | “这里使用项目自带 validator 检查最终产物。全市场 JSON 和 production Parquet 都通过严格契约校验。” |
| 02:12-02:32 | VS Code JSON | 折叠到顶层，依次展示 `counts`、`selected_symbols`、`diagnostics` | “截至 2025 年 12 月 31 日，沪深股票池共 5,182 只，17 只通过，3,386 只规则失败，1,779 只因为证据不足没有进入候选。” |
| 02:32-02:45 | VS Code 终端 | 运行 production 摘要命令 | “生产数据库共 5,182 行、23 列，复合主键没有重复。这里列出的 17 只只是硬筛选结果，不是自动交易指令。” |
| 02:45-02:55 | GitHub Actions | 打开最新绿色 workflow | “项目目前有 36 项自动测试，覆盖未来函数、版本冲突、三态语义、缓存 provenance 和生产防覆盖。” |
| 02:55-03:05 | GitHub README 免责声明 | 停在免责声明和 License | “这个项目用于研究和教育，不构成投资建议。源码、方法边界和复现命令已经完整公开。” |

## 七、导演执行要点

- 每个页面切换前停顿半秒，切换后停顿一秒再讲话。
- 展示代码只定位关键函数，不逐行讲实现。
- JSON 先折叠所有节点，再单独展开 `counts`、`selected_symbols` 和 `diagnostics`。
- 终端命令提前放进剪贴板，避免录制中长时间输入。
- 口播中的数字必须与 `2.0.0` 最终产物一致。
- 不讲参考包的软评分、美股或回测收益；那是另一套实现，不是我们的交付口径。
- 不说“推荐买入”，统一说“硬筛选通过”“研究候选”或“规则结果”。
- 如果口误，停两秒后从该句重说，后期直接剪掉错误段。

## 八、视频结束后的检查

1. 从头检查一次，确认没有账号、密码、token、通知和私人路径弹窗。
2. 确认声音没有爆音，页面文字在 1080p 下可读。
3. 导出 MP4，文件名固定为 `demo.mp4`。
4. 使用带 `-DemoPath` 的打包命令重新生成 ZIP。
5. 检查 ZIP 根目录只有一个 `skill-buffett-moat-screener/`，不存在重复嵌套。
6. 解压到临时目录，运行 `python -m pytest -q` 和两个 validator。
7. 最后上传 `skill-buffett-moat-screener-v2.0.0.zip`。
