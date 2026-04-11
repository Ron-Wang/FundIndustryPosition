# IndustryPosition
# 基金行业仓位测算工具

基于滚动窗口二次规划方法，估算股票型基金在申万一级行业上的仓位配置，支持大规模并行计算。

## 功能特点

- **多类型基金支持**：灵活配置型、偏股混合型、普通股票型基金
- **滚动窗口回归**：使用滑动窗口（默认126个交易日）动态估算行业仓位
- **二次规划优化**：在权重非负且和为1的约束下，最小化拟合误差
- **并行处理**：多进程并行计算，充分利用CPU资源
- **断点续算**：自动跳过已处理基金，支持增量更新
- **结果汇总**：生成每只基金的最新仓位、拟合优度、前五大行业等统计信息
- **分析工具**：提供持仓集中度分析、行业暴露趋势图等辅助函数

## 文件结构
.
├── README.md # 本文件
├── industry_position.py # 主程序（代码文件）
└── results/ # 输出目录（自动创建）
├── {fund_code}_positions.csv # 每只基金的行业仓位时序
└── summary_statistics.csv # 所有基金的汇总统计


## 安装与依赖

### 环境要求
- Python 3.7+
- 推荐使用Anaconda环境

### 依赖库安装

```bash
pip install pandas numpy scipy openpyxl xlrd matplotlib
```

主要依赖说明：

pandas：数据处理

numpy：数值计算

scipy：二次规划优化

openpyxl / xlrd：读取Excel行业数据

matplotlib：绘制行业暴露图（可选）

数据准备
1. 基金净值数据
存放路径结构：

text
Fund_value/
├── 2020/
│   ├── 净值_灵活配置型.csv
│   ├── 净值_偏股混合型.csv
│   └── 净值_普通股票型.csv
├── 2021/
│   └── ...
└── 2026/
    └── ...
CSV文件格式要求：

列名	说明
code	基金代码
day	日期（YYYY-MM-DD）
refactor_net_value	复权单位净值
程序会自动计算日收益率（return），并逐年合并数据。

2. 申万一级行业指数数据
存放路径结构：

text
行业仓位测算/
├── 2025/
│   ├── 801010.xls   (农林牧渔)
│   ├── 801020.xls   (采掘)
│   └── ...
└── 2026/
    └── ...
Excel文件格式要求：

文件名：{行业代码}.xls 或 {行业代码}.xlsx（如 801010.xls）

必须包含列：交易日期 或 日期

必须包含价格列：收盘价 / close / CLOSE（程序会自动识别）

数据行末可能含有一行无效脚注，程序使用 skipfooter=1 自动跳过

使用方法
快速开始
编辑主程序中的路径配置，然后直接运行：

python
if __name__ == "__main__":
    FUND_DATA_PATH = r"你的基金净值数据根目录"
    INDUSTRY_DATA_PATH = r"你的行业指数数据根目录"
    OUTPUT_PATH = r"输出结果目录"
    
    process_fund_industry_positions_parallel(
        fund_data_path=FUND_DATA_PATH,
        industry_data_path=INDUSTRY_DATA_PATH,
        output_path=OUTPUT_PATH,
        window_size=126,      # 滚动窗口天数（半年）
        min_periods=63,       # 最小有效观测数（季度）
        start_year=2020,
        end_year=2026,
        skip_existing=True,   # 跳过已存在的结果文件
        max_workers=6         # 并行进程数（None表示自动使用全部CPU）
    )
参数说明
参数名	类型	默认值	说明
fund_data_path	str	必填	基金净值数据根目录
industry_data_path	str	必填	行业指数数据根目录
output_path	str	./results/	结果输出目录
window_size	int	126	滚动窗口大小（交易日数，约6个月）
min_periods	int	63	窗口内最小有效观测数（约3个月）
start_year	int	2020	基金数据起始年份
end_year	int	2026	基金数据结束年份
skip_existing	bool	True	是否跳过已存在的结果文件
max_workers	int	None	并行进程数，默认使用CPU核心数
注意：行业数据仅加载 2025-2026 年（根据原代码逻辑），如需调整可修改 load_industry_data 调用处的起止年份。

输出结果说明
1. 单基金仓位文件：{fund_code}_positions.csv
列名	说明
date	窗口结束日期（索引列）
801010 ...	各申万一级行业的仓位权重（0~1）
r_squared	窗口回归的拟合优度（R²）
示例：

csv
date,801010,801020,801030,...,r_squared
2025-06-30,0.12,0.05,0.08,...,0.85
2025-07-01,0.13,0.04,0.09,...,0.87
2. 汇总统计文件：summary_statistics.csv
列名	说明
fund_code	基金代码
last_date	最后一个计算窗口的日期
r_squared	最后一个窗口的拟合优度
top_industry_1	第一大行业代码
weight_1	第一大行业权重
top_industry_2	第二大行业代码
weight_2	第二大行业权重
total_periods	有效窗口总数
avg_r_squared	全部窗口的平均拟合优度
processed_date	处理时间
status	success / failed / skipped
分析工具使用
持仓集中度分析
python
from industry_position import analyze_fund_concentration

positions = pd.read_csv('results/000001.OF_positions.csv', index_col='date', parse_dates=True)
concentration = analyze_fund_concentration(positions, top_n=3)
print(concentration.tail())
返回DataFrame包含：

hhi：赫芬达尔指数（行业权重平方和）

top_3_concentration：前三大行业权重之和

num_industries：有效行业数量（权重>1%）

top_industry / top_weight：第一大行业及权重

行业暴露趋势图
python
from industry_position import plot_industry_exposure

positions = pd.read_csv('results/000001.OF_positions.csv', index_col='date', parse_dates=True)
# 自动选取平均权重最大的8个行业绘图
plot_industry_exposure(positions)
# 或指定行业代码列表
plot_industry_exposure(positions, industry_codes=['801010', '801020', '801030'])
注意事项
数据对齐：基金与行业数据按日期内连接，确保使用相同的交易日历。

窗口长度：window_size=126 约半年，min_periods=63 约一季度，可根据数据频率调整。

行业代码：需与文件名中的代码一致（如 801010.xls → 列名 801010）。

内存使用：并行处理时每只基金独立加载数据，内存占用约为单基金数据 × 进程数，请合理设置 max_workers。

拟合优度：r_squared 反映行业收益率对基金收益率的解释程度，过低（如 <0.5）可能表明存在其他资产（债券、现金）或风格因子未被纳入。

断点续算：skip_existing=True 时，若输出目录已存在同名 _positions.csv 文件，将跳过该基金。如需重新计算，请删除对应文件或设置 skip_existing=False。

常见问题
Q：加载行业数据时报错 skipfooter 相关？
A：部分Excel文件可能没有多余脚注，可修改 load_industry_data 中的 pd.read_excel(file_path, skipfooter=1) 去掉 skipfooter 参数。

Q：基金数据很多，运行速度慢怎么办？
A：增加 max_workers 值（不超过CPU核心数）；或先筛选部分基金进行测试。

Q：仓位结果出现负数或大于1？
A：优化器已约束 bounds=(0,1)，如仍出现异常，检查行业数据是否有缺失或异常值，可增加 min_periods 提高稳健性。

Q：如何只计算特定年份的行业数据？
A：修改 process_fund_industry_positions_parallel 函数中调用 load_industry_data 时的起止年份参数（目前硬编码为2025,2026），或将其改为函数参数。

许可证
本项目仅供学习研究使用。
