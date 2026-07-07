# Changelog

## 2026-07-07 — v3.2.0: 重复实验支持 + JCAMP 谱库集成

### 新增功能

#### 重复实验 (Batch) 支持
- 新增 `load_replicate_batch` 工具：加载第二批次重复实验数据，自动匹配样品名和分组
- 新增 `batch` 列追踪数据来源批次
- 自动重命名：batch 2 的原始样品名自动映射为 batch 1 的显示名
- 自动分组：batch 2 的样品自动归入与 batch 1 相同的实验组
- 柱状图、PCA、热图等所有图表的 error bar 自动反映批次间变异
- `/batch` 快捷命令
- `/status` 命令显示每批次统计

#### 实验配置文件 (Profile)
- 支持 JSON 配置文件一键加载实验：样品名、分组、批次路径、默认过滤参数
- `--profile` CLI 参数：`python gcms_agent.py -d <dir> --profile <profile.json>`
- 自动检测数据目录下的 `profile.json`
- `/profile` 快捷命令

#### JCAMP-DX 谱库集成
- 新增 `parse_jcamp_file()` 解析器：支持 JCAMP-DX 4.24 格式的 EI-MS 质谱数据
- 自动提取化合物名、CAS号、分子式、分子量、Kovats 保留指数、峰表
- 支持多条目文件（`##TITLE=...##END=` 拼接格式）
- `PublicLibraryManager.load_jcamp_file()` 方法
- `load_downloaded_libraries()` 自动扫描 `.jdx`/`.jcamp`/`.dx` 文件
- `/jcamp` 快捷命令：扫描 D 盘并加载新导出的 JCAMP 文件
- 已加载：15 个 JCAMP 文件，~2,900 张 EI-MS 谱图，其中 1,114 张含 Kovats RI

### 改进

#### 标签去硬编码
- 移除所有图表中的 "Amino Acid" 硬编码默认标签
- 柱状图、热图、PCA 等标题改为用户可自定义
- 系统提示更新：出图前智能体主动询问标题和坐标轴标签
- 移除 egg yolk 参考文献模板，替换为通用 GC-MS 风味分析文献

#### 谱库状态
- 本地总谱图：**29,452 张**（MassBank 28,191 + JCAMP 1,075 + built-in 186）
- 唯一 CAS 号：7,555
- 含 RI 数据：2,167 种化合物（RI 范围 54–3,343）
- MoNA 在线 API：100 万+ 谱图实时检索

### 修复
- `_filter_data` 返回 JSON 中的 boolean 序列化错误
- `_auto_apply_batch_mappings` 跨批次命名匹配：支持大小写、数字格式差异（Sample001 vs sample1）、序数位置回退匹配
- 工具描述中的 "amino acid" 全部替换为通用术语

### 文件变更
- `gcms_agent.py`：+~350 行（batch 支持、JCAMP 集成、profile 加载、标签去硬编码）
- `public_library_manager.py`：+~150 行（JCAMP-DX 解析器、load_jcamp_file）
- `.gitignore`：新增 JCAMP 文件和 profile.json 排除规则

---

## 之前版本

### v3.1.0 — 初始开源版本
- Agilent ChemStation .D 数据全自动分析
- TIC CSV 峰检测 + 积分
- MassHunter data.ms 质谱提取
- 5 层化合物鉴定策略（NIST 导出 → MSP 余弦匹配 → MassBank 在线 → RT 库 → RT 标签）
- 8 种发表级图表（300dpi）
- DeepSeek API 驱动 AI 解读
- 开源谱库：MassBank EU 12,709 + 风味 9,310 张
