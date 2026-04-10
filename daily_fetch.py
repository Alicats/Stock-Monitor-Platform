import os
import pandas as pd
import akshare as ak
import time
import re
from tickflow import TickFlow
# 导入你原始代码中的计算逻辑 (calculate_rsi, get_macd_status_left, get_stock_data 等)
# 此处省略重复逻辑，建议将 get_stock_data 里的 API Key 设为环境变量


STOCK_POOL = {
    "601988.SH": {"name": "中国银行", "type": "stock", "calc_dy": True},
    "513530.SH": {"name": "港股红利ETF", "type": "etf", "calc_dy": True},
    # "601318.SH": {"name": "中国平安", "type": "stock", "calc_dy": True},
    # "159941.SZ": {"name": "纳指ETF", "type": "etf", "calc_dy": False},
    # "600900.SH": {"name": "长江电力", "type": "stock", "calc_dy": True},
    # "600036.SH": {"name": "招商银行", "type": "stock", "calc_dy": True},
}

# api_key = os.getenv("TICKFLOW_API_KEY")
api_key = "tk_81a9c96173cd4a1c889595fdc2822520"
tf = TickFlow(api_key=api_key)


def get_macd_status_left(dif, dea, hist, prev_hist):
    """
    左侧交易 MACD 判定：
    1. 水下金叉 (DIF<0, hist由负转正) -> 强力买入 ✔✔
    2. 水下绿柱缩短 (DIF<0, hist<0 但 hist > prev_hist) -> 动能衰减 ✔
    3. 其他情况 -> ✘
    """
    is_underwater = dif < 0
    is_gold_cross = prev_hist <= 0 and hist > 0
    is_shortening = hist < 0 and hist > prev_hist
    
    if is_underwater and is_gold_cross:
        return f"✔✔ ({hist:.3f} 水下金叉)", 15  # 评分权重 15
    elif is_underwater and is_shortening:
        return f"✔ ({hist:.3f} 绿色柱缩短)", 10  # 评分权重 10
    elif hist > 0:
        return f"✘ ({hist:.3f} 多头)", 5
    else:
        return f"✘ ({hist:.3f} 寻底)", 0


def calculate_score(data_dict):
    """
    根据打勾情况计算总分 (0-100)
    """
    score = 0
    # 均线 (权重各10)
    if '✔' in data_dict["120日线"]: score += 10
    if '✔' in data_dict["250日线"]: score += 10
    # 布林带 (左侧核心：权重15)
    if '✔' in data_dict["日中下轨"]: score += 15
    if '✔' in data_dict["周中下轨"]: score += 15
    # RSI (权重15)
    if '✔' in data_dict["12日RSI"]: score += 15
    if '✔' in data_dict["6周RSI"]: score += 15
    # MACD (由 status 函数提供分值)
    score += data_dict.get("_day_macd_score", 0)
    score += data_dict.get("_week_macd_score", 0)
    return score


def extract_dividend_per_share(text):
    if not isinstance(text, str) or text == 'nan': return 0.0
    match = re.search(r'10派([\d\.]+)元', text)
    if match: return float(match.group(1)) / 10.0
    return 0.0

def calculate_stock_dividend(symbol: str, close_price: float) -> float:
    try:
        clean_symbol = symbol.split('.')[0]
        df = ak.stock_fhps_detail_em(symbol=clean_symbol)
        if df.empty: return 0.0
        df['现金分红-现金分红比例描述'] = df['现金分红-现金分红比例描述'].astype(str)
        df['最新公告日期'] = df['最新公告日期'].astype(str)
        valid_df = df[df['现金分红-现金分红比例描述'].str.contains('10派', na=False)].copy()
        if valid_df.empty: return 0.0
        if '报告期' in valid_df.columns:
            valid_df = valid_df.sort_values('最新公告日期', ascending=True)
            valid_df = valid_df.drop_duplicates(subset=['报告期'], keep='last')
        recent_df = valid_df.tail(2).copy()
        recent_df['每股分红'] = recent_df['现金分红-现金分红比例描述'].apply(extract_dividend_per_share)
        total_dividend = recent_df['每股分红'].sum()
        return round((total_dividend / close_price) * 100, 4)   
    except: return 0.0

def extract_dividend(value):
    match = re.search(r"(\d+\.?\d*)", value)
    return float(match.group(1)) if match else 0.0

def calculate_etf_dividend(symbol: str):
    try:
        clean_symbol = symbol.split('.')[0]
        hongli_jing_em_df = ak.fund_open_fund_info_em(symbol=clean_symbol, indicator="单位净值走势")
        latest_net_value = hongli_jing_em_df.tail(1)['单位净值'].values[0]
        hongli_fenhong_em_df = ak.fund_open_fund_info_em(symbol=clean_symbol, indicator="分红送配详情")
        total_dividend = hongli_fenhong_em_df.head(12)["每份分红"].apply(extract_dividend).sum()
        return round((total_dividend / latest_net_value) * 100, 4)
    except: return 0.0

def calculate_rsi(series, period=12):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))

def get_rsi_status(val):
    val = float(val)
    symbol = '✔' if val <= 35 else '✘'
    if val <= 20: status = "极度超卖"
    elif val <= 35: status = "超卖"
    elif val >= 70: status = "超买"
    else: status = "中性"
    return f"{symbol} ({val:.2f} {status})"

# ==========================================
# 2. 核心数据获取
# ==========================================
def get_stock_data(symbol, info):
    name = info["name"]
    asset_type = info["type"]
    should_calc_dy = info["calc_dy"]
    try:
        # 日线数据
        df_daily = tf.klines.get(symbol, period="1d", count=300, adjust="forward_additive", as_dataframe=True)
        # 周线数据
        df_weekly = tf.klines.get(symbol, period="1w", count=300, adjust="forward_additive", as_dataframe=True)
        
        for df in [df_daily, df_weekly]:
            df["MA120"] = df["close"].rolling(120).mean()
            df["MA250"] = df["close"].rolling(250).mean()
            df["boll_mid"] = df["close"].rolling(20).mean()
            df["boll_low"] = df["boll_mid"] - (2 * df["close"].rolling(20).std())
            ema12 = df['close'].ewm(span=12, adjust=False).mean()
            ema26 = df['close'].ewm(span=26, adjust=False).mean()
            df['dif'] = ema12 - ema26
            df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
            df['macd_hist'] = (df['dif'] - df['dea']) * 2

        last_d = df_daily.iloc[-1]
        prev_d = df_daily.iloc[-2]
        last_w = df_weekly.iloc[-1]
        prev_w = df_weekly.iloc[-2]
        cp = last_d['close']

        # 获取左侧 MACD 状态
        day_macd_text, day_macd_pts = get_macd_status_left(last_d['dif'], last_d['dea'], last_d['macd_hist'], prev_d['macd_hist'])
        week_macd_text, week_macd_pts = get_macd_status_left(last_w['dif'], last_w['dea'], last_w['macd_hist'], prev_w['macd_hist'])

        # 股息率指标
        dy_display = "N/A"
        if should_calc_dy:
            if asset_type == "stock":
                close_price = last_d['close']
                dy_val = calculate_stock_dividend(symbol, close_price)
            else: # etf
                dy_val = calculate_etf_dividend(symbol)
            dy_display = f"{dy_val:.2f}%"

        res = {
            "代码": symbol, "名称": name, "收盘价": f"{cp:.3f}",
            "股息率": dy_display,
            "120日线": f"{'✔' if cp < last_d['MA120'] else '✘'} ({last_d['MA120']:.2f})",
            "250日线": f"{'✔' if cp < last_d['MA250'] else '✘'} ({last_d['MA250']:.2f})",
            "日中下轨": f"{'✔' if cp < last_d['boll_mid'] else '✘'} ({last_d['boll_mid']:.2f}-{last_d['boll_low']:.2f})",
            "周中下轨": f"{'✔' if cp < last_w['boll_mid'] else '✘'} ({last_w['boll_mid']:.2f}-{last_w['boll_low']:.2f})",
            "12日RSI": get_rsi_status(calculate_rsi(df_daily['close'], 12).iloc[-1]),
            "6周RSI": get_rsi_status(calculate_rsi(df_weekly['close'], 6).iloc[-1]),
            "日MACD": day_macd_text,
            "周MACD": week_macd_text,
            "_day_macd_score": day_macd_pts,
            "_week_macd_score": week_macd_pts
        }
        res["评分"] = calculate_score(res)
        return res
    except Exception as e:
        print(f"Error {name}: {e}"); return None


def run_daily_task():
    # STOCK_POOL 定义...
    results = []
    for symbol, info in STOCK_POOL.items():
        data = get_stock_data(symbol, info) # 使用你原始的计算函数
        if data: results.append(data)
        time.sleep(12)
    
    print(results)

    df = pd.DataFrame(results)
    df.to_csv("data.csv", index=False, encoding="utf-8-sig")
    print("Data saved to data.csv")

if __name__ == "__main__":
    run_daily_task()