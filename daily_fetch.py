import os
import pandas as pd
import akshare as ak
import time
import re
import datetime
from tickflow import TickFlow
from concurrent.futures import ThreadPoolExecutor

from quant_logic import calculate_stock_dividend
print("导入成功！")

STOCK_POOL = {
    "601988.SH": {"name": "中国银行", "type": "stock", "calc_dy": True},
    "513530.SH": {"name": "港股红利ETF", "type": "etf", "calc_dy": True},
    "159941.SZ": {"name": "纳指ETF", "type": "etf", "calc_dy": False},
    "600900.SH": {"name": "长江电力", "type": "stock", "calc_dy": True},
    "601066.SH": {"name": "中信建投", "type": "stock", "calc_dy": True},
    "600886.SH": {"name": "国投电力", "type": "stock", "calc_dy": True},
    "600750.SH": {"name": "华润江中", "type": "stock", "calc_dy": True},
    "600795.SH": {"name": "国电电力", "type": "stock", "calc_dy": True},
    "000651.SZ": {"name": "格力电器", "type": "stock", "calc_dy": True},
    "600941.SH": {"name": "中国移动", "type": "stock", "calc_dy": True},
    "601919.SH": {"name": "中远海控", "type": "stock", "calc_dy": True},
    "000858.SZ": {"name": "五粮液", "type": "stock", "calc_dy": True},
    "600887.SH": {"name": "伊利股份", "type": "stock", "calc_dy": True},
    "601985.SH": {"name": "中国核电", "type": "stock", "calc_dy": True},
    "003816.SZ": {"name": "中国广核", "type": "stock", "calc_dy": True},
    "601318.SH": {"name": "中国平安", "type": "stock", "calc_dy": True},
    "000333.SZ": {"name": "美的集团", "type": "stock", "calc_dy": True},
    "600036.SH": {"name": "招商银行", "type": "stock", "calc_dy": True},
    "000538.SZ": {"name": "云南白药", "type": "stock", "calc_dy": True},
}


# api_key = os.getenv("TICKFLOW_API_KEY")
api_key = "tk_81a9c96173cd4a1c889595fdc2822520"
tf = TickFlow(api_key=api_key)

# 分红缓存文件
DIVIDEND_CACHE_FILE = "dividend_cache.csv"

# ==========================================
# 1. 新增：分红前置并行计算逻辑
# ==========================================
def preload_all_dividends():
    """
    预加载分红数据：
    1. 检查缓存文件是否存在。
    2. 检查缓存文件的修改日期是否为今天。
    3. 如果是今天，则直接读取，不再请求接口，节省时间。
    """
    start_time = time.perf_counter()
    
    # --- 1. 检查缓存是否有效 (一天只跑一次) ---
    if os.path.exists(DIVIDEND_CACHE_FILE):
        # 获取文件最后修改时间
        mtime = os.path.getmtime(DIVIDEND_CACHE_FILE)
        print(f"      缓存文件最后修改时间: {datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')}")
        modify_date = datetime.datetime.fromtimestamp(mtime).date()
        today = datetime.date.today()
        
        if modify_date == today:
            try:
                df_cache = pd.read_csv(DIVIDEND_CACHE_FILE, encoding="utf-8-sig")
                # 检查缓存是否为空（防止上次运行出错生成了空文件）
                if not df_cache.empty:
                    print(f"      🕒 检测到今日缓存已存在 ({modify_date})，直接加载。")
                    return df_cache
            except Exception as e:
                print(f"      [!] 读取缓存失败，将重新计算: {e}")

    # --- 2. 缓存无效或不存在，执行并行计算 ---
    print("      正在预加载分红数据（并行模式/今日首次运行）...")
    
    def get_single_dividend(item):
        # 获取当前工作的线程名称
        symbol, info = item
        if not info["calc_dy"]: return None
        try:
            if info["type"] == "stock":
                dy_val = calculate_stock_dividend(symbol)
            else:
                dy_val = calculate_etf_dividend(symbol)
            return {"代码": symbol, "股息率": dy_val}
        except Exception as e:
            print(f"      [!] 预加载 {symbol} 失败: {e}")
            return None

    # 开启线程池（建议 5-10 个线程，不要太激进以免被封）
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(get_single_dividend, STOCK_POOL.items()))

    # --- 3. 保存计算结果 ---
    valid_results = [r for r in results if r]
    if valid_results:
        df_cache = pd.DataFrame(valid_results)
        df_cache.to_csv(DIVIDEND_CACHE_FILE, index=False, encoding="utf-8-sig")
        print(f"      ✅ 分红数据已更新并缓存，耗时: {time.perf_counter() - start_time:.2f}s")
        return df_cache
    else:
        print("      ⚠️ 未获取到任何有效分红数据")
        return pd.DataFrame()

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
    
    res = None
    if is_underwater and is_gold_cross:
        res = f"✔✔ ({hist:.3f} 水下金叉)", 15
    elif is_underwater and is_shortening:
        res = f"✔ ({hist:.3f} 绿色柱缩短)", 10
    elif hist > 0:
        res = f"✘ ({hist:.3f} 多头)", 5
    else:
        res = f"✘ ({hist:.3f} 寻底)", 0
    return res


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



def calculate_stock_dividend(symbol: str):
    try:
        print(f"  开始计算 {symbol} 股息率(TTM)...")
        # SH601988
        target_symbol = symbol.split('.')[1] + symbol.split('.')[0]  
        stock_individual_spot_xq_df = ak.stock_individual_spot_xq(symbol=target_symbol)
        dividend = stock_individual_spot_xq_df.loc[stock_individual_spot_xq_df['item'] == '股息率(TTM)', 'value'].values[0]
        print(f"  股票 {symbol} 股息率(TTM): {dividend}")
        return dividend
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
        dividend = round((total_dividend / latest_net_value) * 100, 4)
        print(f"  ETF {symbol} 股息率(TTM): {dividend}")
        return dividend
    except Exception as e:
        print(f"Error {symbol}: {e}"); return None

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
def get_stock_data(symbol, info, dividend_df=None):
    name = info["name"]
    asset_type = info["type"]
    should_calc_dy = info["calc_dy"]
    total_start = time.perf_counter()

    try:
        kf_start = time.perf_counter()
        # 1. TickFlow K线获取耗时
        # 日线数据
        df_daily = tf.klines.get(symbol, period="1d", count=300, adjust="forward_additive", as_dataframe=True)
        # 周线数据
        df_weekly = tf.klines.get(symbol, period="1w", count=300, adjust="forward_additive", as_dataframe=True)
        print(f"  [Timer] TickFlow K线下载耗时: {time.perf_counter() - kf_start:.2f}s")

        # 2. 技术指标计算耗时 (MA/BOLL/MACD/RSI)
        calc_start = time.perf_counter()
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
        print(f"  [Timer] Pandas 技术指标计算耗时: {time.perf_counter() - calc_start:.4f}s")

        last_d = df_daily.iloc[-1]
        prev_d = df_daily.iloc[-2]
        last_w = df_weekly.iloc[-1]
        prev_w = df_weekly.iloc[-2]
        close_price = last_d['close']


        # 获取左侧 MACD 状态
        day_macd_text, day_macd_pts = get_macd_status_left(last_d['dif'], last_d['dea'], last_d['macd_hist'], prev_d['macd_hist'])
        week_macd_text, week_macd_pts = get_macd_status_left(last_w['dif'], last_w['dea'], last_w['macd_hist'], prev_w['macd_hist'])

        # 3. 股息率指标
        dy_display = "N/A"
        if should_calc_dy:
            found_in_cache = False
            if dividend_df is not None:
                # 从预加载的 DataFrame 中匹配
                match = dividend_df[dividend_df["代码"] == symbol]
                if not match.empty:
                    row = match.iloc[0]
                    # 从缓存中取出纯数字
                    dy_val = float(row["股息率"])
                    dy_display = f"{dy_val:.2f}%"
                    found_in_cache = True
            
            if not found_in_cache:
                # 兜底方案：实时查询
                print(f"      [!] {name} 缓存失效，正在实时查询...")
                if asset_type == "stock":
                    dy_val = calculate_stock_dividend(symbol)
                else:
                    dy_val = calculate_etf_dividend(symbol)
                dy_display = f"{dy_val:.2f}%"


        res = {
            "代码": symbol, "名称": name, 
            "收盘价": f"{close_price:.3f}",
            "股息率": dy_display,
            "120日线": f"{'✔' if close_price < last_d['MA120'] else '✘'} ({last_d['MA120']:.2f})",
            "250日线": f"{'✔' if close_price < last_d['MA250'] else '✘'} ({last_d['MA250']:.2f})",
            "日中下轨": f"{'✔' if close_price < last_d['boll_mid'] else '✘'} ({last_d['boll_mid']:.2f}-{last_d['boll_low']:.2f})",
            "周中下轨": f"{'✔' if close_price < last_w['boll_mid'] else '✘'} ({last_w['boll_mid']:.2f}-{last_w['boll_low']:.2f})",
            "12日RSI": get_rsi_status(calculate_rsi(df_daily['close'], 12).iloc[-1]),
            "6周RSI": get_rsi_status(calculate_rsi(df_weekly['close'], 6).iloc[-1]),
            "日MACD": day_macd_text,
            "周MACD": week_macd_text,
            "_day_macd_score": day_macd_pts,
            "_week_macd_score": week_macd_pts
        }
        res["评分"] = calculate_score(res)
        print(f"  ✅ {name} 处理完成，总耗时: {time.perf_counter() - total_start:.2f}s")
        return res
    except Exception as e:
        print(f"Error {name}: {e}"); return None


def run_daily_task():
    # STOCK_POOL 定义...
    start = time.perf_counter()

    # A. 并行预加载分红数据（这一步由于使用了多线程，20只票可能只需几秒）
    dividend_df = preload_all_dividends()

    # B. 串行处理 K 线数据（受 12 秒限制）
    results = []
    # for symbol, info in STOCK_POOL.items():
    #     data = get_stock_data(symbol, info, dividend_df) # 使用你原始的计算函数
    #     if data: results.append(data)
    #     # 这里的 12 秒只针对 TickFlow 接口，由于分红已读缓存，循环变得非常清爽
    #     time.sleep(12)
    
    print(f"  股票分析完成耗时: {time.perf_counter() - start:.4f}s")

    df = pd.DataFrame(results)
    df.to_csv("data.csv", index=False, encoding="utf-8-sig")
    print("Data saved to data.csv")

if __name__ == "__main__":
    run_daily_task()