# GC-MS AI Analyzer 使用教程

> 开源免费的 GC-MS 数据分析平台，NIST 商业谱库的替代方案。

---

## 目录

1. [安装与启动](#1-安装与启动)
2. [Web 界面使用](#2-web-界面使用)
3. [命令行使用](#3-命令行使用)
4. [完整分析流程](#4-完整分析流程)
5. [化合物鉴定](#5-化合物鉴定)
6. [统计分析](#6-统计分析)
7. [风味分析专项](#7-风味分析专项)
8. [重复实验处理](#8-重复实验处理)
9. [NIST 谱库接入](#9-nist-谱库接入)
10. [常见问题](#10-常见问题)

---

## 1. 安装与启动

### 1.1 环境要求

- Python 3.10+
- Windows / macOS / Linux
- 4GB+ 内存（加载谱库需要 ~2GB）

### 1.2 安装

```powershell
# 克隆项目
git clone https://github.com/Tina-atk-love/gcms-ai-analyzer.git
cd gcms-ai-analyzer

# 安装依赖（清华镜像加速）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 1.3 获取 API Key

本工具使用 DeepSeek API 驱动 AI 交互（国内直连，无需翻墙）：

1. 打开 [platform.deepseek.com](https://platform.deepseek.com)
2. 注册账号（手机号即可）
3. 右上角 → API Keys → 创建新 Key
4. 复制 `sk-` 开头的密钥
5. 新用户赠送 ¥10 额度，一次分析约几分钱

### 1.4 启动

**方式一：Web 界面（推荐）**

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的密钥"
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`，所有操作在网页上完成。

**方式二：命令行**

```powershell
$env:DEEPSEEK_API_KEY = "sk-你的密钥"
python gcms_agent.py -d "D:\你的数据目录"
```

**方式三：Docker（最省事）**

```bash
docker-compose up -d
# 浏览器打开 http://localhost:8501
```

---

## 2. Web 界面使用

### 2.1 侧边栏

打开界面后，左侧边栏从上到下：

1. **API Key** → 输入 DeepSeek 密钥
2. **NIST Library（可选）** → 如果你有 NIST 谱库，指向 JCAMP 文件目录
3. **Data Source** → 选数据来源：
   - `Local Directory`：输入 .D 文件夹所在目录
   - `Upload .D ZIP`：上传打包的 .D 文件夹
   - `Demo Data`：合成演示数据（不包含真实实验数据）
4. **Rename & Group** → 展开后配置样品名和分组

### 2.2 五个标签页

| 标签 | 做什么 |
|------|--------|
| 📊 **Data** | 查看数据、设置过滤条件（峰面积/匹配度/排除污染物） |
| 📈 **Plots** | 选图表类型 → 设标题 → 一键生成 → 预览 → 打包下载 |
| 👃 **Flavor** | OAV 计算、风味轮、异味检查、形成路径标记 |
| 📐 **Statistics** | ANOVA、PLS-DA、随机森林、结果可视化 |
| 📥 **Export** | HTML 交互报告、Word 三线表、Excel 导出 |

### 2.3 典型操作

1. 加载数据（侧边栏 → 输入目录 → Load Data）
2. 配置样品名（侧边栏 → Rename & Group → 展开设置）
3. 过滤数据（Data 标签 → 设参数 → 自动过滤）
4. 生成图表（Plots 标签 → 选类型 → Generate）
5. 导出结果（Export 标签 → 选格式 → 下载）

---

## 3. 命令行使用

### 3.1 基本命令

启动后进入交互界面，输入命令即可：

| 命令 | 作用 |
|------|------|
| `/run` | 提取数据（自动峰检测 + 谱库匹配） |
| `/rename Sample001.D=对照,Sample002.D=处理` | 给样品起名字 |
| `/groups 对照组=对照1,对照2` | 分配样品到实验组 |
| `/batch D:\重复实验` | 加载重复实验批次 |
| `/filter min_area 10000` | 过滤低峰面积 |
| `/plot bar` | 生成柱状图 |
| `/plot heatmap` | 生成聚类热图 |
| `/plot pca` | 生成 PCA 图 |
| `/plot volcano` | 生成火山图 |
| `/full` | 一键全流程 |

### 3.2 自然语言

不用记命令，直接说话：

> "比较对照组和处理组的差异"
> "画一张火山图"
> "帮我看看有没有异味化合物"
> "哪些化合物对风味贡献最大"

### 3.3 完整命令列表

**数据加载：** `/scan` `/check` `/run` `/batch` `/profile`

**样品管理：** `/rename` `/groups` `/filter`

**鉴定：** `/id` `/identify` `/enhanced` `/diagnose` `/class` `/batchid` `/deconv` `/mirror` `/nist`

**风味：** `/oav` `/flavor` `/pathway`

**统计：** `/anova` `/plsda` `/rf`

**定量：** `/calibrate` `/ionratio` `/istd` `/blank`

**图表：** `/plot bar|pca|heatmap|volcano|boxplot|dashboard|all`

**RT校正：** `/drift` `/align`

**模板：** `/template list|flavor_analysis|metabolomics`

**导出：** `/report` `/html` `/word` `/export`

**其他：** `/status` `/jcamp` `/batchfix`

---

## 4. 完整分析流程

### 4.1 首次分析

```
# 启动（自动加载数据）
> /run D:\Tina

# 样品命名（重要！出图全靠这个）
> /rename Sample001.D=Raw-MP,Sample002.D=PB,Sample003.D=pH2-B,...

# 分组（统计分析用）
> /groups Raw_Protein=Raw-MP
> /groups pH_Treated=PB,pH2-B,pH8-B
> /groups Fermentation=N-F,A-F,P-F,T-F

# 过滤（排除干扰）
> /filter exclude_unidentified=true exclude_contaminants=true

# 数据分析
> /anova         # 找组间差异
> /oav            # 找风味贡献化合物
> /off_flavor_check  # 查异味

# 出图
> /plot bar      # 柱状图
> /plot pca      # PCA
> /plot heatmap  # 热图
> /plot volcano  # 火山图

# 导出
> /word          # Word 表格
> /export excel  # Excel 文件
```

### 4.2 有重复实验时

```
> /run D:\Tina_batch1        # 第一批
> /rename ...                 # 命名
> /groups ...                 # 分组
> /batch D:\Tina_batch2       # 第二批（自动匹配命名和分组）
> /filter ...                 # 过滤
> /plot bar                   # error bar 自动反映批间变异
```

### 4.3 使用配置文件的快速模式

在数据目录下放一个 `profile.json`：

```json
{
  "name": "我的实验",
  "batches": ["D:\\Tina_batch1", "D:\\Tina_batch2"],
  "samples": {
    "Sample001.D": "Raw-MP",
    "Sample002.D": "PB"
  },
  "groups": {
    "Raw_Protein": ["Raw-MP"],
    "pH_Treated": ["PB", "pH2-B", "pH8-B"],
    "Fermentation": ["N-F", "A-F", "P-F", "T-F"]
  },
  "defaults": {
    "min_area": 10000,
    "exclude_unidentified": true,
    "exclude_contaminants": true
  }
}
```

然后：
```powershell
python gcms_agent.py -d "D:\Tina" --profile "D:\Tina\profile.json"
```

一键加载全部配置，直接进入分析状态。

---

## 5. 化合物鉴定

### 5.1 鉴定策略（按可靠性排序）

| 方法 | 可靠性 | 使用场景 |
|------|--------|---------|
| NIST 谱库匹配 | ★★★★★ | 有 NIST 许可证 |
| RI + MS 双维度 | ★★★★★ | 有烷烃标准品 |
| 增强鉴定（多源共识） | ★★★★ | 通用 |
| MassBank 余弦匹配 | ★★★ | 开源替代 |
| MoNA 在线检索 | ★★★ | 罕见化合物 |
| RT 风味库 | ★★ | 快速初筛 |

### 5.2 使用建议

```
> /id           # RI+MS 双维度鉴定（有烷烃标准品时首选）
> /enhanced     # 四层交叉验证（MS+RI+同位素+多源共识）
> /identify     # 开源谱库批量鉴定未知峰
> /batchid      # 并行搜索所有未知峰（更快）
> /diagnose RT_5.230  # 诊断特定未知峰
```

### 5.3 鉴定结果解读

```
confirmed   → MS≥900 且 RI<20 或多源确认 → 可直接写进论文
high        → MS≥800 或双源 → 进一步确认后可发表
probable    → MS≥700 → 建议 NIST 或标准品确认
tentative   → MS≥600 → 仅供参考
```

---

## 6. 统计分析

### 6.1 组间比较

```
> /anova                         # 单因素方差分析 + Tukey HSD
> /compare_groups A组 B组       # 两组 t-test + FDR
> /volcano A组 vs B组           # 火山图
```

### 6.2 多变量分析

```
> /plsda                         # PLS-DA + VIP 得分
> /rf                            # 随机森林特征重要性
> /pca                            # PCA（通过 /plot pca）
```

### 6.3 数据质量

```
> /quality                       # 质量报告（缺失率/CV%/离群值）
> /drift                         # RT 漂移检测
> /align                         # RT 漂移校正
> /batchfix                      # 批次效应校正
```

---

## 7. 风味分析专项

### 7.1 OAV（气味活度值）

```
> /oav                           # 计算所有化合物的 OAV
```

OAV = 浓度 ÷ 气味阈值。OAV > 1 表示该化合物对风味有贡献。

### 7.2 风味轮

```
> /flavor                        # 生成风味轮雷达图 + 异味检查
```

自动按 odor 类别（青草/果香/烤香/硫味等）汇总风味特征。

### 7.3 异味数据库

```
> /off_flavor_check              # 检查是否检出微藻常见异味物
```

内置 15 种常见异味化合物（geosmin、2-MIB、dimethyl trisulfide 等）。

### 7.4 形成路径标记

```
> /pathway                       # 标记 Maillard / 脂质氧化 / 异味
```

---

## 8. 重复实验处理

```
> /run D:\实验1                  # 加载第一批
> /rename ...                    # 样品命名
> /groups ...                    # 分组
> /batch D:\实验2                # 加载第二批（自动匹配命名和分组）
```

第二批的样品会自动重命名并归入相同的组。所有后续分析的 error bar 自动反映批间变异。

---

## 9. NIST 谱库接入

如果你有商业 NIST 谱库许可证：

1. 从 NIST MS Search 导出 JCAMP-DX 文件（.jdx）
2. 放到一个目录（如 `D:\NIST_JCAMP`）
3. 在 Web 界面侧边栏输入该路径，点击 Index
4. 或用命令行：`/nist D:\NIST_JCAMP`

NIST 谱库数据**不会**被复制或上传——所有文件留在原位，智能体只读不写。这完全符合 NIST 许可协议。

---

## 10. 常见问题

**Q: 报错 "DEEPSEEK_API_KEY not set"**
→ 设置环境变量 `$env:DEEPSEEK_API_KEY = "sk-xxx"` 或在 Web 界面侧边栏输入。

**Q: 提取数据时报错**
→ 检查 .D 文件夹是否完整（需包含 data.ms 和 tic_front.csv）。如果只有 .CH 文件，需要先从 ChemStation 导出。

**Q: 化合物鉴定全是 RT_XX.XXX**
→ 说明谱库没有匹配到。尝试：
1. `/identify` 用开源谱库搜索
2. 从 MassHunter 导出 NIST 匹配结果 CSV
3. 接入 NIST 本地谱库 `/nist`

**Q: 出图时标签是默认的英文**
→ 智能体会主动问你标题和坐标轴标签，直接告诉它中文即可。

**Q: 耗多少 Token？**
→ 一次完整分析约 2000-5000 tokens。DeepSeek 定价 ¥1/百万 tokens，一次分析不到 1 分钱。

**Q: 能处理 Thermo/Shimadzu 的数据吗？**
→ 需要将数据导出为 mzML 格式（通用标准），然后 `/read_mzml` 加载。

**Q: Windows 上字体显示方块**
→ 确保系统安装了宋体和 Times New Roman。Windows 10+ 自带。

---

## 引用

使用本工具发表论文时，请引用：

- 本工具：GC-MS AI Analyzer (2025). https://github.com/Tina-atk-love/gcms-ai-analyzer
- MassBank: Horai et al. (2010) *J. Mass Spectrom.* 45(7), 703-714
- NIST WebBook: Linstrom & Mallard (eds.), NIST SRD 69
- MoNA: https://mona.fiehnlab.ucdavis.edu
