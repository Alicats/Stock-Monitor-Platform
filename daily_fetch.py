import os
import pandas as pd
import time
import datetime
from concurrent.futures import ThreadPoolExecutor

from quant_logic import get_full_analysis

STOCK_POOL = {
    "601988.SH": {"name": "中国银行", "type": "stock", "calc_dy": True},
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


EIP_POOL = {
    "513530.SH": {"name": "港股红利ETF", "type": "etf", "calc_dy": True},
    "159941.SZ": {"name": "纳指ETF", "type": "etf", "calc_dy": False},
}


RESULT_FILE = "data.csv"


# ==========================================
# 2. 核心任务运行
# ==========================================
def run_daily_analysis():
    start_all = time.perf_counter()
    print("=== 量化策略扫描启动 ===")
    
    results = []
    
    # 1. 提交所有任务，不要在提交时立即 get result()
    with ThreadPoolExecutor(max_workers=5) as stock_executor, \
        ThreadPoolExecutor(max_workers=1) as eip_executor:
        
        # 提交股票池任务 (并行)
        stock_futures = [stock_executor.submit(get_full_analysis, s, i) for s, i in STOCK_POOL.items()]

        # 提交 EIP 池任务 (串行提交，带 15s 延迟)
        eip_futures = []
        for symbol, info in EIP_POOL.items():
            f = eip_executor.submit(get_full_analysis, symbol, info)
            eip_futures.append(f)
            # 注意：这里的 sleep(15) 会让主线程停 15s 再提交下一个 EIP 任务
            # 从而实现 EIP 每只股票间隔 15s 的需求
            time.sleep(15) 

        # 2. 统一收集结果
        for f in stock_futures:
            res = f.result()
            if res: results.append(res); print(f"✅ [STOCK] {res['名称']} (评分: {res['评分']})")

        for f in eip_futures:
            res = f.result()
            if res: results.append(res); print(f"✅ [EIP] {res['名称']} (评分: {res['评分']})")


    # C. 结果持久化
    if results:
        df_final = pd.DataFrame(results)
            
        df_final.to_csv(RESULT_FILE, index=False, encoding="utf-8-sig")
        print("-" * 30)
        print(df_final)
        print(f"🎉 全部扫描完成！结果已存至: {RESULT_FILE}")
        print(f"📊 总计耗时: {(time.perf_counter() - start_all) / 60:.2f} 分钟")
    else:
        print("⚠️ 未生成任何有效数据。")

if __name__ == "__main__":
    run_daily_analysis()