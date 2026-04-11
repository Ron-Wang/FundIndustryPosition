import pandas as pd
import numpy as np
import os
from scipy.optimize import minimize
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

# ====================== 数据加载模块 ======================

def load_fund_data(base_path, start_year=2020, end_year=2026):
    """
    加载所有基金的净值数据
    """
    all_funds = {}
    fund_types = ['净值_灵活配置型.csv', '净值_偏股混合型.csv', '净值_普通股票型.csv']
    
    for year in range(start_year, end_year + 1):
        year_path = os.path.join(base_path, str(year))
        if not os.path.exists(year_path):
            continue
            
        for fund_type in fund_types:
            file_path = os.path.join(year_path, fund_type)
            if not os.path.exists(file_path):
                continue
                
            try:
                df = pd.read_csv(file_path, encoding='gbk', low_memory=False)
                # 转换日期格式
                df['date'] = pd.to_datetime(df['day'])
                df = df.sort_values('date')
                
                # 计算日收益率（使用复权净值refactor_net_value）
                df = df.copy()
                df['return'] = df.groupby('code')['refactor_net_value'].pct_change()
                
                # 存储到字典
                for code, group in df.groupby('code'):
                    group = group[['date', 'return', 'refactor_net_value']].copy()
                    group = group.dropna(subset=['return'])
                    
                    if code not in all_funds:
                        all_funds[code] = group
                    else:
                        # 合并不同年份的数据
                        all_funds[code] = pd.concat([all_funds[code], group])
                        all_funds[code] = all_funds[code].drop_duplicates(subset=['date']).sort_values('date')
                
            except Exception as e:
                print(f"加载文件失败: {file_path}, 错误: {e}")
    
    return all_funds

def load_industry_data(industry_path, start_year=2025, end_year=2026):
    """
    加载申万一级行业指数数据
    """
    all_industries = {}
    
    for year in range(start_year, end_year + 1):
        year_path = os.path.join(industry_path, str(year))
        if not os.path.exists(year_path):
            continue
            
        for file_name in os.listdir(year_path):
            if file_name.endswith('.xls') or file_name.endswith('.xlsx'):
                try:
                    # 提取行业代码（如801010）
                    industry_code = file_name.split('.')[0]
                    file_path = os.path.join(year_path, file_name)
                    
                    # 读取Excel文件
                    df = pd.read_excel(file_path, skipfooter=1) 
                    
                    # 标准化列名
                    df.columns = [col.strip() for col in df.columns]
                    
                    # 转换日期格式
                    if '交易日期' in df.columns:
                        df['date'] = pd.to_datetime(df['交易日期'])
                    elif '日期' in df.columns:
                        df['date'] = pd.to_datetime(df['日期'])
                    
                    # 获取收盘价列
                    price_col = None
                    for col in ['收盘价', 'close', 'CLOSE']:
                        if col in df.columns:
                            price_col = col
                            break
                    
                    if price_col is None and len(df.columns) > 1:
                        price_col = df.columns[4]  # 通常第5列是收盘价
                    
                    if price_col:
                        # 转换价格格式（处理逗号分隔）
                        if df[price_col].dtype == object:
                            df[price_col] = df[price_col].astype(str).str.replace(',', '').astype(float)
                        
                        df = df.sort_values('date')
                        df[f'return_{industry_code}'] = df[price_col].pct_change()
                        
                        # 只保留需要的列
                        result = df[['date', f'return_{industry_code}']].dropna().copy()
                        
                        if industry_code not in all_industries:
                            all_industries[industry_code] = result
                        else:
                            all_industries[industry_code] = pd.concat([
                                all_industries[industry_code], result
                            ]).drop_duplicates(subset=['date']).sort_values('date')
                            
                except Exception as e:
                    print(f"加载行业数据失败: {file_path}, 错误: {e}")
    
    return all_industries

# ====================== 仓位计算模块 ======================

def _sum_constraint(weights):
    """权重和为1的约束函数（用于quadratic_programming）"""
    return np.sum(weights) - 1

def quadratic_programming(portfolio_returns, asset_returns):
    """
    二次规划求解仓位
    优化目标: min ||portfolio_returns - asset_returns * weights||^2
    约束条件: weights >= 0, sum(weights) = 1
    """
    n_assets = asset_returns.shape[1]
    
    # 定义目标函数
    def objective(weights):
        predicted = np.dot(asset_returns, weights)
        error = portfolio_returns - predicted
        return np.sum(error ** 2)
    
    # 约束条件
    constraints = [
        {'type': 'eq', 'fun': _sum_constraint},  # 权重和为1
    ]
    bounds = [(0, 1) for _ in range(n_assets)]  # 权重在0-1之间
    
    # 初始猜测（均匀分配）
    x0 = np.ones(n_assets) / n_assets
    
    # 优化求解
    result = minimize(objective, x0, method='SLSQP', 
                      bounds=bounds, constraints=constraints)
    
    if result.success:
        return result.x
    else:
        # 如果优化失败，返回均匀权重
        return np.ones(n_assets) / n_assets

def calculate_rolling_positions(fund_returns, industry_returns, 
                               window_size=126, min_periods=63):
    """
    滚动计算基金在各行业的仓位
    """
    # 对齐基金和行业数据
    merged_data = fund_returns.merge(industry_returns, on='date', how='inner')
    merged_data = merged_data.sort_values('date').reset_index(drop=True)
    
    if len(merged_data) < min_periods:
        return pd.DataFrame()
    
    # 准备收益率矩阵
    fund_return_series = merged_data['fund_return'].values
    industry_return_matrix = merged_data[[col for col in merged_data.columns 
                                         if col.startswith('return_')]].values
    
    dates = merged_data['date'].values
    industry_codes = [col.replace('return_', '') for col in merged_data.columns 
                      if col.startswith('return_')]
    
    # 滚动计算
    positions = []
    position_dates = []
    
    for i in range(window_size - 1, len(merged_data)):
        start_idx = i - window_size + 1
        end_idx = i + 1
        
        window_fund_returns = fund_return_series[start_idx:end_idx]
        window_industry_returns = industry_return_matrix[start_idx:end_idx, :]
        
        # 确保有足够的数据
        if np.sum(~np.isnan(window_fund_returns)) < min_periods:
            continue
        
        # 清理NaN值
        valid_mask = ~np.isnan(window_fund_returns)
        for j in range(industry_return_matrix.shape[1]):
            valid_mask = valid_mask & ~np.isnan(window_industry_returns[:, j])
        
        if np.sum(valid_mask) < min_periods:
            continue
        
        valid_fund_returns = window_fund_returns[valid_mask]
        valid_industry_returns = window_industry_returns[valid_mask, :]
        
        # 计算仓位
        try:
            weights = quadratic_programming(valid_fund_returns, valid_industry_returns)
            positions.append(weights)
            position_dates.append(dates[i])
        except:
            continue
    
    if not positions:
        return pd.DataFrame()
    
    # 创建结果DataFrame
    positions_df = pd.DataFrame(positions, columns=industry_codes)
    positions_df['date'] = position_dates
    positions_df.set_index('date', inplace=True)
    
    # 计算R-squared
    positions_df['r_squared'] = 0
    for i, (date, row) in enumerate(positions_df.iterrows()):
        if i < len(position_dates):
            date_idx = np.where(dates == date)[0][0]
            window_start = max(0, date_idx - window_size + 1)
            
            fund_ret_window = fund_return_series[window_start:date_idx+1]
            industry_ret_window = industry_return_matrix[window_start:date_idx+1, :]
            
            # 清理NaN
            valid_mask = ~np.isnan(fund_ret_window)
            for j in range(industry_ret_window.shape[1]):
                valid_mask = valid_mask & ~np.isnan(industry_ret_window[:, j])
            
            if np.sum(valid_mask) > min_periods:
                valid_fund = fund_ret_window[valid_mask]
                valid_industry = industry_ret_window[valid_mask, :]
                
                predicted = np.dot(valid_industry, row[industry_codes].values)
                ss_res = np.sum((valid_fund - predicted) ** 2)
                ss_tot = np.sum((valid_fund - np.mean(valid_fund)) ** 2)
                
                if ss_tot > 0:
                    positions_df.loc[date, 'r_squared'] = 1 - ss_res / ss_tot
    
    return positions_df

# ====================== 并行处理单基金函数 ======================

def process_single_fund(fund_code, fund_data, industry_df, output_path,
                        window_size, min_periods, skip_existing):
    """
    处理一只基金的行业仓位测算
    """
    output_file = os.path.join(output_path, f'{fund_code}_positions.csv')
    
    # 跳过已存在的文件
    if skip_existing and os.path.exists(output_file):
        return {'fund_code': fund_code, 'status': 'skipped', 'message': '文件已存在'}
    
    try:
        # 准备基金收益率数据
        fund_returns = fund_data[['date', 'return']].copy()
        fund_returns.columns = ['date', 'fund_return']
        
        # 合并基金和行业数据
        merged = fund_returns.merge(industry_df, on='date', how='inner')
        if len(merged) < min_periods:
            return {'fund_code': fund_code, 'status': 'failed', 'message': '数据不足'}
        
        # 计算滚动仓位
        positions = calculate_rolling_positions(
            fund_returns, industry_df, window_size, min_periods
        )
        if positions.empty:
            return {'fund_code': fund_code, 'status': 'failed', 'message': '仓位计算失败'}
        
        # 保存结果
        positions.to_csv(output_file, encoding='utf-8-sig')
        
        # 提取汇总信息
        last_date = positions.index[-1]
        r_squared_last = positions.iloc[-1]['r_squared']
        # 前5大行业（去掉r_squared列）
        weights_last = positions.iloc[-1].drop('r_squared')
        top_industries = weights_last.sort_values(ascending=False).head(5)
        
        summary = {
            'fund_code': fund_code,
            'last_date': last_date,
            'r_squared': r_squared_last,
            'top_industry_1': top_industries.index[0] if len(top_industries) > 0 else None,
            'weight_1': top_industries.iloc[0] if len(top_industries) > 0 else 0,
            'top_industry_2': top_industries.index[1] if len(top_industries) > 1 else None,
            'weight_2': top_industries.iloc[1] if len(top_industries) > 1 else 0,
            'total_periods': len(positions),
            'avg_r_squared': positions['r_squared'].mean(),
            'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'success'
        }
        return summary
    except Exception as e:
        return {'fund_code': fund_code, 'status': 'error', 'message': str(e)}

# ====================== 主处理函数（并行版） ======================

def process_fund_industry_positions_parallel(
        fund_data_path, industry_data_path, output_path='./results/',
        window_size=126, min_periods=63,
        start_year=2020, end_year=2026,
        skip_existing=True, max_workers=None):
    """
    主函数：并行处理所有基金的行业仓位
    """
    # 创建输出目录
    os.makedirs(output_path, exist_ok=True)
    
    print("开始加载行业数据...")
    # 行业数据只加载2025-2026年（根据原代码设定）
    industry_data = load_industry_data(industry_data_path, 2025, 2026)
    if not industry_data:
        print("未找到行业数据！")
        return
    
    # 合并所有行业数据为一个DataFrame
    print("合并行业数据...")
    industry_df = None
    for code, data in industry_data.items():
        if industry_df is None:
            industry_df = data.copy()
        else:
            industry_df = industry_df.merge(data, on='date', how='outer')
    industry_df = industry_df.sort_values('date').reset_index(drop=True)
    print(f"行业数据合并完成，日期范围：{industry_df['date'].min()} ~ {industry_df['date'].max()}")
    
    print("开始加载基金数据...")
    all_funds = load_fund_data(fund_data_path, start_year, end_year)
    print(f"共加载 {len(all_funds)} 只基金")
    
    # 准备任务列表
    fund_items = list(all_funds.items())
    total = len(fund_items)
    
    # 设置默认进程数
    if max_workers is None:
        max_workers = multiprocessing.cpu_count()
    print(f"启动并行处理，使用 {max_workers} 个进程...")
    
    results = []
    processed_count = 0
    skipped_count = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_code = {}
        for fund_code, fund_data in fund_items:
            future = executor.submit(
                process_single_fund,
                fund_code, fund_data, industry_df, output_path,
                window_size, min_periods, skip_existing
            )
            future_to_code[future] = fund_code
        
        # 按完成顺序收集结果
        for i, future in enumerate(as_completed(future_to_code), 1):
            fund_code = future_to_code[future]
            try:
                result = future.result()
                if result.get('status') == 'success':
                    results.append(result)
                    processed_count += 1
                    print(f"✓ 完成 {i}/{total}: {fund_code} (成功)")
                elif result.get('status') == 'skipped':
                    skipped_count += 1
                    print(f"- 跳过 {i}/{total}: {fund_code} (文件已存在)")
                else:
                    print(f"✗ 失败 {i}/{total}: {fund_code} - {result.get('message', '未知错误')}")
            except Exception as e:
                print(f"✗ 异常 {i}/{total}: {fund_code} - {str(e)}")
    
    # 保存汇总结果
    if results:
        summary_df = pd.DataFrame(results)
        summary_file = os.path.join(output_path, 'summary_statistics.csv')
        
        # 如果汇总文件已存在，则追加新结果（并去重）
        if os.path.exists(summary_file):
            existing = pd.read_csv(summary_file)
            existing = existing[~existing['fund_code'].isin(summary_df['fund_code'])]
            summary_df = pd.concat([existing, summary_df], ignore_index=True)
        
        summary_df.to_csv(summary_file, encoding='utf-8-sig', index=False)
        print(f"汇总结果已保存到 {summary_file}")
    
    print(f"处理完成！成功: {processed_count}，跳过: {skipped_count}，失败: {total - processed_count - skipped_count}")

# ====================== 分析工具函数 ======================

def analyze_fund_concentration(positions_df, top_n=3):
    """
    分析基金持仓集中度
    """
    analysis_results = []
    
    for date, row in positions_df.iterrows():
        if 'r_squared' in row:
            weights = row.drop('r_squared')
        else:
            weights = row
        
        weights = weights[weights > 0.01]  # 只考虑权重大于1%的行业
        
        if len(weights) > 0:
            # 计算赫芬达尔指数（HHI）
            hhi = np.sum(weights ** 2)
            
            # 前N大行业集中度
            top_weights = weights.sort_values(ascending=False).head(top_n)
            concentration = top_weights.sum()
            
            analysis_results.append({
                'date': date,
                'hhi': hhi,
                f'top_{top_n}_concentration': concentration,
                'num_industries': len(weights),
                'top_industry': top_weights.index[0] if len(top_weights) > 0 else None,
                'top_weight': top_weights.iloc[0] if len(top_weights) > 0 else 0
            })
    
    return pd.DataFrame(analysis_results)

def plot_industry_exposure(positions_df, industry_codes=None):
    """
    绘制基金行业暴露图
    """
    import matplotlib.pyplot as plt
    
    if industry_codes is None:
        # 选择权重最大的几个行业
        avg_weights = positions_df.mean()
        if 'r_squared' in avg_weights:
            avg_weights = avg_weights.drop('r_squared')
        
        industry_codes = avg_weights.nlargest(8).index.tolist()
    
    plt.figure(figsize=(12, 6))
    
    for industry in industry_codes:
        if industry in positions_df.columns:
            plt.plot(positions_df.index, positions_df[industry], 
                    label=industry, linewidth=2)
    
    plt.xlabel('日期')
    plt.ylabel('仓位权重')
    plt.title('基金行业仓位变化')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

# ====================== 使用示例 ======================

if __name__ == "__main__":
    # 设置路径（请根据实际情况修改）
    FUND_DATA_PATH = r"C:\Users\RonWang\Desktop\InvestRonny\StockFund\Fund_data\Fund_value"
    INDUSTRY_DATA_PATH = r"C:\Users\RonWang\Desktop\InvestRonny\StockFund\行业仓位测算"
    OUTPUT_PATH = r"C:\Users\RonWang\Desktop\InvestRonny\StockFund\行业仓位测算\results"
    
    # 运行并行主程序
    process_fund_industry_positions_parallel(
        fund_data_path=FUND_DATA_PATH,
        industry_data_path=INDUSTRY_DATA_PATH,
        output_path=OUTPUT_PATH,
        window_size=126,   # 6个月滚动窗口
        min_periods=63,    # 最小数据要求（3个月）
        start_year=2020,
        end_year=2026,
        skip_existing=True,  # 跳过已测算基金
        max_workers=6       # 并行进程数，可根据CPU核心调整
    )
    
    # 示例：分析特定基金的仓位
    # fund_code = "000001.OF"
    # positions_file = os.path.join(OUTPUT_PATH, f"{fund_code}_positions.csv")
    # if os.path.exists(positions_file):
    #     positions = pd.read_csv(positions_file, index_col='date', parse_dates=True)
    #     concentration_df = analyze_fund_concentration(positions)
    #     print(concentration_df.tail())
    #     plot_industry_exposure(positions)