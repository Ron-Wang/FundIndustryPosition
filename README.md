# 基金行业仓位测算工具
基于滚动二次规划的公募基金行业仓位测算工具，支持多进程并行处理，高效计算基金在申万一级行业上的动态暴露。

## 功能特性
- 📊 **多类型基金支持**：灵活配置型、偏股混合型、普通股票型基金
- 📈 **行业数据适配**：自动解析申万一级行业指数收益率数据
- 🔄 **滚动窗口测算**：支持自定义滚动窗口和最小数据期数
- ⚡ **多进程并行**：充分利用CPU核心，大幅提升处理效率
- 📝 **结果自动保存**：单基金明细+汇总统计，一键导出
- 📉 **分析工具**：持仓集中度分析、行业暴露可视化

## 目录结构
```
项目根目录/
├── Fund_data/                # 基金净值数据目录
│   └── Fund_value/           # 按年份存放的基金净值文件
├── 行业仓位测算/              # 行业指数数据目录
│   └── results/              # 输出结果保存目录
└── fund_industry_position.py # 主程序代码
```

## 数据格式要求
### 基金数据
- 命名格式：`净值_灵活配置型.csv`、`净值_偏股混合型.csv`、`净值_普通股票型.csv`
- 必选字段：`code`(基金代码)、`day`(日期)、`refactor_net_value`(复权净值)
- 编码格式：GBK

### 行业数据
- 格式：Excel文件（.xls/.xlsx）
- 必选字段：交易日期/日期、收盘价
- 命名：行业代码作为文件名（如801010.xlsx）

## 快速开始
### 1. 环境依赖
```bash
pip install pandas numpy scipy openpyxl matplotlib
```

### 2. 运行配置
修改代码中`if __name__ == "__main__":`部分的路径配置：
```python
FUND_DATA_PATH = "你的基金净值数据路径"
INDUSTRY_DATA_PATH = "你的行业指数数据路径"
OUTPUT_PATH = "结果输出路径"
```

### 3. 执行程序
```bash
python fund_industry_position.py
```

## 核心参数说明
| 参数 | 默认值 | 说明 |
|------|--------|------|
| window_size | 126 | 滚动窗口大小（交易日，默认6个月） |
| min_periods | 63 | 最小有效数据期数（默认3个月） |
| start_year | 2020 | 基金数据起始年份 |
| end_year | 2026 | 基金数据结束年份 |
| skip_existing | True | 跳过已计算完成的基金 |
| max_workers | CPU核心数 | 并行处理进程数 |

## 输出结果
### 1. 单基金仓位文件
`{基金代码}_positions.csv`
- 索引：日期
- 列：各行业仓位权重 + r_squared（拟合优度）

### 2. 汇总统计文件
`summary_statistics.csv`
- 基金代码、最新日期、拟合优度
- 前5大重仓行业及权重
- 总测算期数、平均拟合优度

## 核心模块说明
### 1. 数据加载模块
- `load_fund_data()`：加载多年份多类型基金净值数据，计算日收益率
- `load_industry_data()`：加载申万一级行业指数数据，计算行业收益率

### 2. 仓位计算模块
- `quadratic_programming()`：二次规划求解最优行业权重
  - 目标：最小化收益率拟合误差
  - 约束：权重非负、权重和为1
- `calculate_rolling_positions()`：滚动窗口计算动态行业仓位

### 3. 并行处理模块
- `process_single_fund()`：单基金仓位测算逻辑
- `process_fund_industry_positions_parallel()`：多进程并行调度

### 4. 分析工具
- `analyze_fund_concentration()`：计算HHI指数、行业集中度
- `plot_industry_exposure()`：行业暴露趋势可视化

## 使用示例
### 分析单基金持仓
```python
# 读取已计算的仓位数据
fund_code = "000001.OF"
positions = pd.read_csv(f"results/{fund_code}_positions.csv", 
                       index_col='date', parse_dates=True)

# 分析持仓集中度
concentration = analyze_fund_concentration(positions)
print(concentration.tail())

# 绘制行业暴露图
plot_industry_exposure(positions)
```

## 注意事项
1. 数据路径需严格按照年份目录结构组织
2. 首次运行会计算所有基金，耗时较长，后续可跳过已计算文件
3. 拟合优度（r_squared）越高代表行业仓位拟合效果越好
4. 建议根据CPU核心数调整`max_workers`参数

## 技术原理
采用**最小二乘法二次规划**模型，通过滚动时间窗口求解：
$$\min \|R_{fund} - R_{industry} \cdot w\|^2$$
约束条件：
$$\sum w_i = 1, \quad w_i \geq 0$$
实现基金收益率向行业指数的最优拆解，得到动态行业仓位。

## 许可证
MIT License
