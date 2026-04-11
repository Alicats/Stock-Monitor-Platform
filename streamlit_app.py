import streamlit as st
import pandas as pd
import akshare as ak
from tickflow import TickFlow
import time

# 页面配置
st.set_page_config(page_title="多因子安全边际监控", layout="wide")

# --- 1. 样式处理工具函数 ---
def format_indicator(val):
    """指标分行：大图标(变色) + 小字描述"""
    if not isinstance(val, str) or '(' not in val:
        return f"<div style='text-align:center; font-size: 18px;'>{val}</div>"
    
    symbol = val.split('(')[0].strip()
    description = val.split('(')[1].replace(')', '').strip()
    color = "#ff4b4b" if "✘" in symbol else "#29b09d"
    
    return f"""
    <div style="text-align: center; line-height: 1.2;">
        <div style="color: {color}; font-size: 22px; font-weight: bold;">{symbol}</div>
        <div style="color: #808495; font-size: 12px; font-family: sans-serif;">{description}</div>
    </div>
    """

def format_single_value(val, color="#31333F", is_bold=True):
    """用于渲染普通的独立数值列（现价、股息率等）"""
    weight = "bold" if is_bold else "normal"
    return f"""
    <div style="text-align: center; color: {color}; font-size: 18px; font-weight: {weight};">
        {val}
    </div>
    """

# --- 2. 逻辑函数 ---
def chan_analysis(symbol):
    time.sleep(1) 
    print({symbol})
    return f"【缠论分析报告 - {symbol}】\n级别：日线\n结构：走势中枢形成中...\n建议：关注三买机会。"

@st.cache_data(ttl=3600)
def load_csv_data():
    try:
        df = pd.read_csv("data.csv")
        return df
    except:
        return pd.DataFrame()

def fetch_realtime_data(symbol):
    st.info(f"正在实时抓取 {symbol} 数据...")
    return {
        "代码": symbol, "名称": "实时查询", "评分": 88, "收盘价": "10.24", "股息率": "5.21%",
        "120日线": "✔ (9.50)", "250日线": "✘ (11.20)", "日中下轨": "✔ (10.10)",
        "周中下轨": "✔ (9.80)", "12日RSI": "✔ (32.5)", "6周RSI": "✘ (55.0)",
        "日MACD": "✔ (金叉)", "周MACD": "✘ (寻底)"
    }

# --- 3. UI 布局 ---
st.title("📊 股票多因子安全边际监控")

DEFAULT_SHOW = ["601988.SH", "513530.SH", "159941.SZ", "600900.SH", "601318.SH", "600036.SH"]  
FIXED_POOL = ["601066.SH", "600866.SH", "600750.SH", "600795.SH", "000651.SZ", "600941.SH", "601919.SH", "000858.SH", "600887.SH", "601985.SH", "003816.SZ", "000333.SZ", "000538.SZ"]    

col_select, col_search = st.columns([2, 1])
with col_select:
    selected_stock = st.selectbox("🎯 快速选择池内标的", ["请选择..."] + FIXED_POOL)
with col_search:
    search_stock = st.text_input("🔍 搜索新代码", placeholder="例如: 000001.SZ")

# --- 4. 数据处理 ---
raw_df = load_csv_data()
show_list = DEFAULT_SHOW.copy()
if selected_stock != "请选择...":
    show_list.append(selected_stock)
show_list = list(dict.fromkeys(show_list))

if not raw_df.empty:
    display_df = raw_df[raw_df['代码'].isin(show_list)].copy()
else:
    display_df = pd.DataFrame()

# --- 5. 表格渲染 ---
if not display_df.empty:
    st.subheader("📋 因子监控清单")
    
    # 定义表头：将代码、名称、现价、股息率全部独立
    headers = [
        "代码", "名称", "评分", "现价", "股息率", 
        "120日", "250日", "日布林", "周布林", 
        "12D-RSI", "6W-RSI", "日MACD", "周MACD", "分析"
    ]
    # 重新分配14列的比例 (总和需平衡，避免单列过窄)
    col_ratios = [1.2, 1.2, 0.7, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 1.1, 1.1, 1.1, 0.7]
    
    # 渲染表头
    h_cols = st.columns(col_ratios)
    for col, h in zip(h_cols, headers):
        col.markdown(f"<p class='header-text'>{h}</p>", unsafe_allow_html=True)

    st.divider()

    if "评分" in display_df.columns:
        display_df = display_df.sort_values("评分", ascending=False)

    for idx, row in display_df.iterrows():
        r_cols = st.columns(col_ratios)
        
        # 1. 代码
        r_cols[0].markdown(format_single_value(row['代码']), unsafe_allow_html=True)
        # 2. 名称
        r_cols[1].markdown(format_single_value(row['名称'], color="gray", is_bold=False), unsafe_allow_html=True)
        # 3. 评分
        r_cols[2].markdown(f"<h3 style='text-align: center; margin:0; color:#1E88E5;'>{row['评分']}</h3>", unsafe_allow_html=True)
        # 4. 现价
        r_cols[3].markdown(format_single_value(row.get('收盘价', '-')), unsafe_allow_html=True)
        # 5. 股息率
        r_cols[4].markdown(format_single_value(row.get('股息率', '-'), color="#f39c12"), unsafe_allow_html=True)
        
        # 6-13. 核心指标 (从索引5开始)
        indicator_fields = ['120日线', '250日线', '日中下轨', '周中下轨', '12日RSI', '6周RSI', '日MACD', '周MACD']
        for i, field in enumerate(indicator_fields):
            val = str(row[field]) if field in row else "-"
            r_cols[i+5].markdown(format_indicator(val), unsafe_allow_html=True)
        
        # 14. 分析按钮
        if r_cols[13].button("📝", key=f"btn_{row['代码']}"):
            with st.expander(f"📖 {row['名称']} 深度分析", expanded=True):
                st.info(chan_analysis(row['代码']))

    # 注入 CSS
    st.markdown("""
        <style>
        .header-text {
            color: #808495;
            font-weight: bold;
            text-align: center;
            font-size: 15px !important;
        }
        div[data-testid="stHorizontalBlock"] {
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #f0f2f6;
        }
        /* 确保单元格文字不换行，保持整齐 */
        div[data-testid="stMarkdownContainer"] p {
            font-size: 16px !important;
            margin-bottom: 0;
            white-space: nowrap;
            text-align: center;
        }
        .stButton>button {
            font-size: 18px !important;
            height: 40px;
            width: 100%;
        }
        </style>
    """, unsafe_allow_html=True)

else:
    st.warning("⚠️ data.csv 数据为空或未匹配到默认股票。")