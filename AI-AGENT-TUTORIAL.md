yan# 🧬 GCMS .D AI Agent — 完整使用教程 (DeepSeek版)

## 什么是这个 AI Agent？

一个**独立的 Python CLI 智能体**，用 **DeepSeek API**（国内直接访问）作为大脑，
专门处理 Agilent ChemStation `.D` 氨基酸分析数据。

你只需要用**自然语言**告诉它你要做什么，它会自动推理、调用工具、给出结果。

---

## 🚀 快速开始（5分钟）

### 第1步：安装依赖

```powershell
cd C:\Users\86150\gcms_analyzer
.\setup_agent.ps1
```

### 第2步：获取 DeepSeek API Key

1. 打开 **https://platform.deepseek.com** （国内直接访问，无需翻墙）
2. 注册账号（手机号即可）
3. 右上角 → **API Keys** → **创建新 Key**
4. 复制 `sk-` 开头的 Key

> 💰 费用：约 **¥1/百万输入tokens**，一次完整分析约 2000 tokens，**不到1分钱**。
> 新注册通常送 ¥10 额度。

### 第3步：设置 Key 并启动

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的Key"
& "C:\Users\86150\AppData\Local\Programs\Python\Python312\python.exe" gcms_agent.py
```

---

## 💬 使用示例

### 快速完整分析
```
🧬 你: /full

🤖 Agent: [自动: 扫描→提取→统计→6张图表→Excel+CSV导出]
  完成！14个样本，16种氨基酸。
  两组间2种氨基酸显著差异(p<0.05)。
  所有结果已保存到 output/agent_results/
```

### 针对性提问
```
你: 脱胆固醇液体组的氨基酸总量为什么比凝胶组高这么多？
你: 样本37的氨基酸组成有什么特点？
你: 帮我画一张只包含 glu, asp, lys 这三个氨基酸的对比图
你: 有没有异常样本？帮我检查一下
```

### 快捷命令
| 命令 | 作用 |
|------|------|
| `/scan` | 扫描数据目录 |
| `/run` | 提取数据 + 统计分析 |
| `/plot` | 生成全部6张图表 |
| `/full` | 完整流程（扫描→提取→分析→图表→导出） |
| `/status` | 查看当前状态 |
| `/clear` | 清除对话记忆 |

---

## 🛠 Agent 的 8 个工具

| 工具 | 触发条件（你这样说） |
|------|-------------------|
| `scan_data_directory` | "扫描数据"、"有多少样本" |
| `extract_all_data` | "提取数据"、"加载数据" |
| `get_sample_info` | "样本37的情况"、"看看XX号" |
| `compare_groups` | "比较A和B"、"哪个组更高" |
| `generate_plots` | "画热图"、"生成PCA" |
| `run_statistical_analysis` | "做统计"、"相关性分析" |
| `find_anomalies` | "找异常"、"检查离群值" |
| `export_report` | "导出Excel"、"保存报告" |

---

## ⚙️ 切换模型

在 `gcms_agent.py` 第 25 行修改：

```python
DEEPSEEK_MODEL = "deepseek-chat"       # V3 — 成本最低，日常分析够用（默认）
DEEPSEEK_MODEL = "deepseek-reasoner"   # R1 — 深度推理，复杂分析用
```

---

## 🔧 如果要用其他国内 API

Agent 使用 OpenAI 兼容格式，只需改两处：

```python
# 例如用通义千问
self.client = OpenAI(
    api_key="your-qwen-key",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DEEPSEEK_MODEL = "qwen-plus"

# 例如用智谱
self.client = OpenAI(
    api_key="your-zhipu-key",
    base_url="https://open.bigmodel.cn/api/paas/v4"
)
DEEPSEEK_MODEL = "glm-4-flash"
```

---

## ❓ 常见问题

**Q: 报错 "Connection refused"**
→ DeepSeek API 在国内可直接访问，检查网络，不需要代理。

**Q: 报错 "Insufficient Balance"**
→ 账户余额不足，去 platform.deepseek.com 充值。新用户送 ¥10。

**Q: 抗氧化剂组为什么被跳过？**
→ 12个样本没有 ChemStation 积分的报告文件。需先在 ChemStation 中打开处理。

**Q: 想用其他 LLM？**
→ 见上方「如果用其他国内 API」，修改3行代码即可。

---

## 📁 项目文件

```
C:\Users\86150\gcms_analyzer\
├── gcms_agent.py          ← 🧠 AI Agent 主程序（你要用的）
├── gcms_analyzer.py       ← 📊 批量分析脚本（无需API Key）
├── setup_agent.ps1        ← 🔧 一键安装
├── AI-AGENT-TUTORIAL.md   ← 📖 本教程
└── output\
    └── agent_results\     ← Agent 输出
        ├── plots\         ← 图表
        ├── *.xlsx         ← Excel报告
        └── *.csv          ← 数据文件
```
