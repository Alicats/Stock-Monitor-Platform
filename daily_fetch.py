import os
import pandas as pd
import time
import datetime
from concurrent.futures import ThreadPoolExecutor

from quant_logic import get_full_analysis, calculate_stock_dividend, calculate_etf_dividend

STOCK_POOL = {
    "601988.SH": {"name": "中国银行", "type": "stock", "calc_dy": True},
    "513530.SH": {"name": "港股红利ETF", "type": "etf", "calc_dy": True},
    # "159941.SZ": {"name": "纳指ETF", "type": "etf", "calc_dy": False},
    # "600900.SH": {"name": "长江电力", "type": "stock", "calc_dy": True},
    # "601066.SH": {"name": "中信建投", "type": "stock", "calc_dy": True},
    # "600886.SH": {"name": "国投电力", "type": "stock", "calc_dy": True},
    # "600750.SH": {"name": "华润江中", "type": "stock", "calc_dy": True},
    # "600795.SH": {"name": "国电电力", "type": "stock", "calc_dy": True},
    # "000651.SZ": {"name": "格力电器", "type": "stock", "calc_dy": True},
    # "600941.SH": {"name": "中国移动", "type": "stock", "calc_dy": True},
    # "601919.SH": {"name": "中远海控", "type": "stock", "calc_dy": True},
    # "000858.SZ": {"name": "五粮液", "type": "stock", "calc_dy": True},
    # "600887.SH": {"name": "伊利股份", "type": "stock", "calc_dy": True},
    # "601985.SH": {"name": "中国核电", "type": "stock", "calc_dy": True},
    # "003816.SZ": {"name": "中国广核", "type": "stock", "calc_dy": True},
    # "601318.SH": {"name": "中国平安", "type": "stock", "calc_dy": True},
    # "000333.SZ": {"name": "美的集团", "type": "stock", "calc_dy": True},
    # "600036.SH": {"name": "招商银行", "type": "stock", "calc_dy": True},
    # "000538.SZ": {"name": "云南白药", "type": "stock", "calc_dy": True},
}



DIVIDEND_CACHE_FILE = "dividend_cache.csv"
RESULT_FILE = "data.csv"


# ==========================================
# 1. 分红预加载逻辑 
# ==========================================
def preload_all_dividends():
    """
    预加载分红数据并缓存。
    """
    if os.path.exists(DIVIDEND_CACHE_FILE):
        mtime = os.path.getmtime(DIVIDEND_CACHE_FILE)
        modify_date = datetime.datetime.fromtimestamp(mtime).date()
        if modify_date == datetime.date.today():
            try:
                df_cache = pd.read_csv(DIVIDEND_CACHE_FILE, encoding="utf-8-sig")
                if not df_cache.empty:
                    print(f"🕒 检测到今日分红缓存 ({modify_date})，直接加载。")
                    return df_cache
            except Exception:
                pass

    print("🚀 正在并行抓取分红数据（今日首次运行）...")
    
    def fetch_unit(item):
        symbol, info = item
        if not info["calc_dy"]: return None
        try:
            if info["type"] == "stock":
                val = calculate_stock_dividend(symbol)
            else:
                val = calculate_etf_dividend(symbol)
            return {"代码": symbol, "股息率": val}
        except Exception as e:
            print(f"  [!] {symbol} 分红抓取失败: {e}")
            return None

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_unit, STOCK_POOL.items()))

    valid_res = [r for r in results if r]
    df_cache = pd.DataFrame(valid_res)
    df_cache.to_csv(DIVIDEND_CACHE_FILE, index=False, encoding="utf-8-sig")
    return df_cache


# ==========================================
# 2. 核心任务运行
# ==========================================
def run_daily_analysis():
    start_all = time.perf_counter()
    print("=== 量化策略扫描启动 ===")
    
    # A. 准备分红数据
    dividend_df = preload_all_dividends()
    
    final_results = []
    
    # B. 串行扫描 (遵循 TickFlow 的 12s 限制)
    for symbol, info in STOCK_POOL.items():
        name = info["name"]
        print(f"🔎 正在处理: {name} ({symbol})...")
        
        try:
            # 匹配该标的分红率
            dy_match = dividend_df[dividend_df["代码"] == symbol]
            current_dy = float(dy_match.iloc[0]["股息率"]) if not dy_match.empty else None
            
            # 获取数据
            analysis_data = get_full_analysis(symbol, info, current_dy)
            
            if analysis_data:
                final_results.append(analysis_data)
                print(f"   ✅ 完成评分: {analysis_data.get('评分', 0)}")
            
        except Exception as e:
            print(f"   ❌ {name} 扫描发生异常: {e}")

        # 严格遵守数据源频率限制
        time.sleep(12)

    # C. 结果持久化
    if final_results:
        df_final = pd.DataFrame(final_results)
            
        df_final.to_csv(RESULT_FILE, index=False, encoding="utf-8-sig")
        print("-" * 30)
        print(df_final)
        print(f"🎉 全部扫描完成！结果已存至: {RESULT_FILE}")
        print(f"📊 总计耗时: {(time.perf_counter() - start_all) / 60:.2f} 分钟")
    else:
        print("⚠️ 未生成任何有效数据。")

if __name__ == "__main__":
    run_daily_analysis()