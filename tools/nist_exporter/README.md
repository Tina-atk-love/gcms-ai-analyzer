# NIST JCAMP Exporter — 独立桌面应用

批量导出 NIST 谱库为 JCAMP-DX 格式，带图形界面。可打包为 .exe 分发给任何人使用。

## 快速开始

```powershell
pip install pywinauto
python nist_exporter_gui.py
```

## 打包为 .exe 独立程序

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed --name "NIST_Exporter" nist_exporter_gui.py
```

生成的 `dist/NIST_Exporter.exe` 可以直接发给任何人，不需要装 Python。双击即用。

## 使用方法

1. 打开 NIST MS Search，加载谱库
2. 双击 `NIST_Exporter.exe`（或 `python nist_exporter_gui.py`）
3. 选择 NIST 库文件夹和输出目录
4. 设置批次大小（推荐 500）
5. 点击 **Start Export**
6. 等待完成，导出期间不要碰电脑

## 导出后在智能体中使用

在 GC-MS AI Analyzer Web 界面侧边栏 -> NIST Library -> 输入导出目录路径 -> Index

## 两个版本区别

| 文件 | 说明 |
|------|------|
| `nist_exporter_gui.py` | **GUI 版（推荐）** — 独立窗口，进度条，可打包 .exe |
| `nist_auto_export.py` | CLI 版 — 命令行运行，适合脚本集成 |
