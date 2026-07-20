# 数据智能分析（data-intel-profiler）

## 功能
输入 CSV/Excel 数据或自然语言查询，自动完成数据画像、质量检测、异常检测与归因、NL2SQL 转换、清洗方案输出，全程不修改原始数据。

## 价值量化（可验证）

| 场景 | 人工操作 | 本 Skill | 验证方式 |
|---|---|---|---|
| CSV 数据画像（50列） | 手写 describe()+info() 约10分钟 | data_profiler.py ~1秒 | `sample_sales.csv` 52行8列实测 |
| 缺失值 + 异常值检测 | 逐列目测后再写代码 | 一次输出全列画像+质量评分 | IQR/Z-score双方法交叉验证 |
| 自然语言→SQL | 需懂SQL语法 | NL2SQL规则库一键映射 | 场景二 3条查询输出 |
| 异常归因 | 需业务经验 | 3类模式自动推测+处理建议 | 场景三 录入错误检测 |

## 创新点
- **双方法异常检测**：IQR + Z-score 可选，交叉验证减少误报
- **异常归因**：不仅标异常，还推测原因（录入错误/业务突变/季节性），区别于只标不解释的工具
- **NL2SQL 规则库**：覆盖 SELECT/WHERE/GROUP BY/JOIN/HAVING 五大子句的 10+ 常见映射模式
- **一站式画像**：数值列（均值/中位/标准差/分位/异常值）+ 文本列（高频值/基数/单值占比）
- **多工具协同**：`scripts/data_profiler.py` 支持 `--method iqr|zscore` + `--sample`
- 全程不修改原始数据，安全合规

## 目录结构
```
data-intel-profiler/
├── SKILL.md
├── README.md
├── references/
│   └── reference.md           # 质量规则/异常检测/NL2SQL映射/清洗策略
├── examples/
│   ├── input.md               # 3场景（数据画像/NL2SQL/异常归因）
│   ├── output.md              # 对应输出
│   └── sample_sales.csv       # 52条超市销售数据（含缺失/异常）
└── scripts/
    └── data_profiler.py       # CSV画像+异常检测，支持IQR/Z-score
```

## 数据来源
- `sample_sales.csv`：基于真实零售场景构造的模拟数据，含12个月跨度的门店/品类/价格/销量/会员维度

## 使用方法
1. 粘贴 CSV/Excel 数据或文件路径，说"分析这份数据"
2. 有 CSV 文件时让技能调用 `scripts/data_profiler.py --input data.csv`
3. 可选 `--method zscore` 切换异常检测方法，大数据用 `--sample 1000`

## 免责声明
本技能仅做数据分析与建议输出，不自动修改原始数据，不连接外部数据源。所有结论基于所提供数据。
