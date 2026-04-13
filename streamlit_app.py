import streamlit as st
import pandas as pd
import sqlite3
import time

# --- 1. 数据库基础操作 ---
def init_db():
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS favorites (code TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

def get_favorites():
    conn = sqlite3.connect("stock_monitor.db")
    df = pd.read_sql("SELECT code FROM favorites", conn)
    conn.close()
    return set(df['code'].tolist())



def toggle_favorite_and_refresh(code):
    """点击星星时的切换逻辑"""
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    
    if code in st.session_state.fav_set:
        cursor.execute("DELETE FROM favorites WHERE code = ?", (code,))
        st.session_state.fav_set.remove(code)
    else:
        cursor.execute("INSERT OR REPLACE INTO favorites (code) VALUES (?)", (code,))
        st.session_state.fav_set.add(code)
            
    conn.commit()
    conn.close()
    st.rerun() # 立即刷新界面

# --- 2. 样式处理工具 ---
def format_indicator(val):
    if not isinstance(val, str) or '(' not in val:
        return f"<div style='text-align:center; font-size: 16px;'>{val}</div>"
    
    symbol = val.split('(')[0].strip()
    description = val.split('(')[1].replace(')', '').strip()
    color = "#ff4b4b" if "✘" in symbol else "#29b09d"
    
    return f"""
    <div style="text-align: center; line-height: 1.1;">
        <div style="color: {color}; font-size: 20px; font-weight: bold;">{symbol}</div>
        <div style="color: #808495; font-size: 11px;">{description}</div>
    </div>
    """

def format_single_value(val, color="#31333F", is_bold=True):
    weight = "bold" if is_bold else "normal"
    return f"<div style='text-align:center; color:{color}; font-size:16px; font-weight:{weight};'>{val}</div>"

# --- 3. 核心逻辑与数据加载 ---
@st.cache_data(ttl=600)
def load_and_preprocess_data():
    try:
        df = pd.read_csv("data.csv")
        # 如果没有“类型”字段，可以根据代码简单模拟（实际会从CSV读）
        if '类型' not in df.columns:
            df['类型'] = df['代码'].apply(lambda x: "ETF" if x.startswith(('5', '1')) else "股票")
        return df
    except:
        return pd.DataFrame()


def process_sorting(df):
    state = st.session_state.sort_state
    if state == 0 or df.empty:
        return df
    
    # 深度拷贝防止警告
    temp_df = df.copy()
    # 提取数值逻辑：处理 % 和 -
    temp_df['_v'] = temp_df['股息率'].astype(str).str.replace('%', '').replace('-', '-1').astype(float)
    
    # 1: 降序, 2: 升序
    temp_df = temp_df.sort_values('_v', ascending=(state == 2))
    return temp_df.drop(columns=['_v'])

def render_stock_table(df_to_show, prefix="market"):
    if df_to_show.empty:
        st.info("暂无匹配数据")
        return

    # 表头定义 (保持不变...)
    col_ratios = [0.6, 1.2, 1.2, 0.7, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.1, 0.7]
    h_cols = st.columns(col_ratios)
    # 固定的表头文字
    headers = {
        0: "自选", 1: "代码", 2: "名称", 3: "评分", 
        4: "现价", 6: "120日", 7: "250日", 
        8: "日布林", 9: "周布林", 10: "日MACD", 11: "分析"
    }

    for i, label in headers.items():
        h_cols[i].markdown(f"<p style='color:#808495; font-weight:bold; text-align:center; margin-bottom:0;'>{label}</p>", unsafe_allow_html=True)

    # 特殊处理：股息率表头 (Index 5)
    with h_cols[5]:
        render_sort_header("股息率", prefix)
    
    st.divider()

    for _, row in df_to_show.iterrows():
        r_cols = st.columns(col_ratios)
        code = row['代码']
        
        # --- 核心修改：用按钮模拟星星 ---
        is_fav = code in st.session_state.fav_set
        star_icon = "★" if is_fav else "☆"

        # 渲染星星按钮
        with r_cols[0]:
            # 使用 container 包装以便应用局部样式（如果需要）
            star_type = "favstar" if is_fav else "normalstar"
            if st.button(star_icon, key=f"{prefix}_{star_type}_{code}"):
                toggle_favorite_and_refresh(code)

       
        # ------------------------------

        # 后续单元格渲染 (保持不变)
        r_cols[1].markdown(format_single_value(code), unsafe_allow_html=True)
        r_cols[2].markdown(format_single_value(row['名称'], color="gray", is_bold=False), unsafe_allow_html=True)
        r_cols[3].markdown(f"<h4 style='text-align:center;color:#1E88E5;margin:0;'>{row['评分']}</h4>", unsafe_allow_html=True)
        r_cols[4].markdown(format_single_value(row.get('收盘价', '-')), unsafe_allow_html=True)
        r_cols[5].markdown(format_single_value(row.get('股息率', '-'), color="#f39c12"), unsafe_allow_html=True)
        
        indicators = ['120日线', '250日线', '日中下轨', '周中下轨', '日MACD']
        for i, field in enumerate(indicators):
            val = str(row[field]) if field in row else "-"
            r_cols[i+6].markdown(format_indicator(val), unsafe_allow_html=True)
        
        if r_cols[11].button("📝", key=f"{prefix}_btn_{code}"):
            st.info(f"分析报告：{code} 目前处于安全边际内。")


def toggle_div_sort():
    # 状态循环：0 -> 1 -> 2 -> 0
    st.session_state.sort_state = (st.session_state.sort_state + 1) % 3


def render_sort_header(label, prefix):
    """渲染一个干净、像文本一样的排序按钮"""
    sort_icons = {0: "↕️", 1: "🔽", 2: "🔼"}
    current_icon = sort_icons[st.session_state.sort_state]
    
    # 使用 streamlit 容器来容纳按钮，方便应用样式
    if st.button(f"{label} {current_icon}", key=f"{prefix}_sort_btn"):
        st.session_state.sort_state = (st.session_state.sort_state + 1) % 3
        st.rerun()

# --- 4. 主程序界面 ---
def main():
    st.set_page_config(page_title="多因子安全边际监控", layout="wide")
    init_db()
    
    # 初始化 Session State
    if 'fav_set' not in st.session_state:
        st.session_state.fav_set = get_favorites()

    if 'sort_state' not in st.session_state:
        st.session_state.sort_state = 0  # 0:默认, 1:降序, 2:升序

    st.title("📊 多因子安全边际监控系统")

    # A. 顶层过滤器
    all_data = load_and_preprocess_data()
    
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        asset_filter = st.selectbox("🎯 资产类别", ["全部", "股票", "ETF"])
    with col_f2:
        search_query = st.text_input("🔍 搜索代码或名称", "").upper()

    # 数据过滤逻辑
    display_df = all_data.copy()
    if asset_filter != "全部":
        display_df = display_df[display_df['类型'] == asset_filter]
    if search_query:
        display_df = display_df[display_df['代码'].str.contains(search_query) | display_df['名称'].str.contains(search_query)]

    # 应用排序逻辑 (在此处调用)
    display_df = process_sorting(display_df)

    # B. Tab 分页
    tab_market, tab_fav = st.tabs(["📋 市场大池", "⭐ 我的自选池"])

    with tab_market:
        # --- 修改点：不再硬编码列表，直接从 CSV 数据中获取所有唯一代码 ---
        if not all_data.empty:
            pool_list = all_data['代码'].unique().tolist()
            market_df = display_df[display_df['代码'].isin(pool_list)]
            render_stock_table(market_df, prefix="m")
        else:
            st.warning("数据源为空，请检查 data.csv")

    with tab_fav:
        fav_df = display_df[display_df['代码'].isin(st.session_state.fav_set)]
        render_stock_table(fav_df, prefix="f")

    # 注入 CSS
    # 注入 CSS (终极修正版)
    st.markdown("""
        <style>
        /* 1. 统一按钮基础外观 */
        div[data-testid="stColumn"] button {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: 40px !important;
            width: 100% !important;
        }

        /* 2. 针对已选中(favstar)的文字颜色：强制穿透到最底层标签 */
        div[data-testid="stColumn"] button[key*="favstar"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stColumn"] button[key*="favstar"] p,
        div[data-testid="stColumn"] button[key*="favstar"] {
            color: #FF4B4B !important; 
            -webkit-text-fill-color: #FF4B4B !important; /* 针对某些浏览器的强制填色 */
            font-size: 24px !important;
            font-weight: bold !important;
        }

        /* 3. 针对未选中(normalstar)的文字颜色 */
        div[data-testid="stColumn"] button[key*="normalstar"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stColumn"] button[key*="normalstar"] p,
        div[data-testid="stColumn"] button[key*="normalstar"] {
            color: #BDC3C7 !important;
            -webkit-text-fill-color: #BDC3C7 !important;
            font-size: 24px !important;
        }

        /* 4. 鼠标悬停逻辑 */
        div[data-testid="stColumn"] button[key*="star"]:hover p {
            color: #FF4B4B !important;
            -webkit-text-fill-color: #FF4B4B !important;
        }

        /* 5. 排序按钮样式 (股息率文字) */
        div[data-testid="stColumn"] button[key*="sort"] p {
            color: #808495 !important;
            font-size: 15px !important;
            font-weight: bold !important;
        }
        
        /* 移除点击后的蓝色边框和焦点框 */
        button:focus, button:active, button:focus-visible {
            outline: none !important;
            box-shadow: none !important;
            background: transparent !important;
        }
        </style>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()