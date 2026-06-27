# GC-MS AI Analyzer Agent

**开源 NIST 替代方案** — 基于 DeepSeek API 的 Agilent ChemStation `.D` 数据全自动分析智能体。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Spectra](https://img.shields.io/badge/EI--MS_Spectra-12,709-orange)](#谱库)
[![RI](https://img.shields.io/badge/RI_Database-1,498-teal)](#保留指数)

## 核心能力

| 功能 | 说明 |
|------|------|
| 数据提取 | 自动解析 REPORT01.CSV / Report.TXT / XLSX / TIC CSV |
| 化合物鉴定 | 5 层策略：NIST 导出 → MSP 余弦匹配 → 在线 MassBank → 内置 RT 库 → RT 标签 |
| EI-MS 谱库 | 12,709 张参考谱图，24 个化学类别，0.1-0.5s 检索 |
| RI 数据库 | 1,498 个 Kovats 保留指数，支持自动校准 |
| 统计分析 | Welch t-test + Mann-Whitney U + FDR + Cohen's d |
| 可视化 | 8 种发表级图表（300dpi，中文字体）|
| AI 解读 | DeepSeek 自动生成分析报告 |
| 成本 | ~¥0.01/次分析 |

## 快速开始

```powershell
# 1. 安装依赖
pip install -r requirements.txt

# 2. 设置 DeepSeek API Key
$env:DEEPSEEK_API_KEY = "sk-xxx"

# 3. 启动智能体
python gcms_agent.py -d "D:\your_data"
```

## 快捷命令

| 命令 | 功能 |
|------|------|
| `/run` | 提取数据 + 自动鉴定 |
| `/plot bar/pca/heatmap/volcano` | 选择性出图 |
| `/identify` | 开源谱库鉴定 |
| `/ri` | RI 自动校准（需烷烃标准品）|
| `/filter` | 数据过滤 |
| `/report` | 发表级报告 |

## 谱库

| 来源 | 谱图数 | 类型 |
|------|--------|------|
| MassBank EU (NIST 格式) | 12,516 | EI-MS 名义质量数 |
| 内置精选 | 193 | EI-MS 精选 |
| NIST WebBook (公开) | 1,498 | Kovats RI |
| MassBank.eu v3 API | 139,000+ | 在线按需检索 |

## 文件结构

```
gcms_analyzer/
├── gcms_agent.py              # AI 智能体主程序
├── gcms_analyzer.py           # 非交互式分析器
├── public_library_manager.py  # 统一谱库管理器
├── spectral_match.py          # 余弦相似度匹配引擎
├── spectral_library.py        # 内置 MSP 谱库 (~193 张)
├── mona_client.py             # MassBank 在线 API 客户端
├── mass_spectra_reader.py     # data.ms 读取器
├── download_public_libs.py    # 公共谱库下载工具
├── public_libraries/
│   ├── ei_ms_combined.msp     # 合并的 12,709 张 EI-MS 谱图
│   └── nist_webbook_ri.json   # 1,498 条 RI 数据
├── GEMINI.md                  # 智能体详细文档
└── requirements.txt
```

## 与 NIST 对比

| 指标 | NIST 2023 | 本智能体 |
|------|-----------|---------|
| 本地 EI-MS | 350,000 | 12,709 |
| 在线检索 | 无 | 139,000 (MassBank) |
| RI 数据库 | 350,000 | 1,498 + 自动校准 |
| 统计分析 | 无 | ✅ |
| AI 解读 | 无 | ✅ |
| 成本 | ¥数万/年 | ¥0.01/次 |
| 开源 | ❌ | ✅ MIT |

## 发表引用

使用本智能体鉴定化合物时，请引用：
- MassBank: Horai et al. (2010) *J. Mass Spectrom.* 45(7), 703-714
- NIST WebBook: Linstrom & Mallard (eds.), NIST SRD 69
