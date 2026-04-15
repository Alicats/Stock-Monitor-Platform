import streamlit as st
import pandas as pd
import sqlite3

# --- 1. 数据库基础操作 ---
def init_db():
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS favorites (code TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

def get_favorites():
    conn = sqlite3.connect("stock_monitor.db")
    try:
        df = pd.read_sql("SELECT code FROM favorites", conn)
        return set(df['code'].tolist())
    except:
        return set()
    finally:
        conn.close()

def toggle_favorite_and_refresh(code):
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
    st.rerun()

# --- 2. 样式处理工具 ---
def wrap_cell(content, color="#31333F", bold=False, font_size="14px", is_header=False):
    """统一单元格容器。is_header 用于处理静态表头的特殊样式"""
    weight = "600" if (bold or is_header) else "normal"
    extra_class = "static-header" if is_header else ""
    return f"""
    <div class="cell-container {extra_class}" style="color:{color}; font-weight:{weight}; font-size:{font_size};">
        {content}
    </div>
    """

def format_indicator(val):
    if not isinstance(val, str) or '(' not in val:
        return wrap_cell(val)
    
    parts = val.split('(')
    symbol = parts[0].strip()
    description = parts[1].replace(')', '').strip()
    color = "#ff4b4b" if "✘" in symbol else "#29b09d"
    
    content = f"""
    <div style="line-height: 1.2;">
        <div style="color: {color}; font-size: 18px; font-weight: bold;">{symbol}</div>
        <div style="color: #808495; font-size: 10px;">{description}</div>
    </div>
    """
    return wrap_cell(content)

# --- 3. 核心逻辑 ---
@st.cache_data(ttl=600)
def load_and_preprocess_data():
    try:
        df = pd.read_csv("data.csv")
        if '类型' not in df.columns:
            df['类型'] = df['代码'].apply(lambda x: "ETF" if str(x).startswith(('5', '1')) else "股票")
        return df
    except:
        return pd.DataFrame(columns=['代码', '名称', '评分', '收盘价', '股息率', '120日线', '250日线', '日中下轨', '周中下轨', '日MACD', '周MACD', '类型'])

def process_sorting(df):
    col = st.session_state.sort_col
    order = st.session_state.sort_order
    if order == 0 or col is None or df.empty:
        return df
    
    temp_df = df.copy()
    if col == "股息率":
        temp_df['_v'] = temp_df['股息率'].astype(str).str.replace('%', '').replace('-', '-1').astype(float)
        temp_df = temp_df.sort_values('_v', ascending=(order == 2))
        temp_df = temp_df.drop(columns=['_v'])
    elif col == "评分":
        temp_df = temp_df.sort_values("评分", ascending=(order == 2))
    return temp_df

def render_modern_header(label, prefix, is_sortable=True):
    """
    重写表头渲染：
    只有指定的字段（is_sortable=True）才渲染为按钮，否则渲染为静态 Markdown 容器
    """
    if is_sortable:
        icon = ""
        if st.session_state.sort_col == label:
            icon = " 🔽" if st.session_state.sort_order == 1 else " 🔼"
        
        # 仅针对 评分 和 股息率 保留按钮，点击会触发 st.rerun
        if st.button(f"{label}{icon}", key=f"{prefix}_h_{label}", use_container_width=True):
            if st.session_state.sort_col == label:
                st.session_state.sort_order = (st.session_state.sort_order + 1) % 3
                if st.session_state.sort_order == 0: st.session_state.sort_col = None
            else:
                st.session_state.sort_col = label
                st.session_state.sort_order = 1
            st.rerun()
    else:
        # 其他表头渲染为静态 HTML，不产生点击交互，不回传服务器
        st.markdown(wrap_cell(label, color="#94a3b8", font_size="13px", is_header=True), unsafe_allow_html=True)

def render_modern_table(df_to_show, prefix="market"):
    if df_to_show.empty:
        st.info("💡 暂无匹配数据")
        return

    col_ratios = [0.6, 1.0, 1.2, 0.7, 0.8, 1.0, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0, 0.6]
    
    # 渲染表头
    h_cols = st.columns(col_ratios)
    header_config = {
        0: ("自选", False), 1: ("代码", False), 2: ("名称", False),
        3: ("评分", True),  4: ("现价", False), 5: ("股息率", True),
        6: ("120日", False), 7: ("250日", False), 8: ("日布林", False),
        9: ("周布林", False), 10: ("日MACD", False), 11: ("周MACD", False),
        12: ("分析", False)
    }

    for idx, (label, sortable) in header_config.items():
        with h_cols[idx]:
            render_modern_header(label, prefix, is_sortable=sortable)
    
    # 数据行渲染
    for _, row in df_to_show.iterrows():
        r = st.columns(col_ratios)
        code = row['代码']
        is_fav = code in st.session_state.fav_set
        
        with r[0]:
            star_icon = "★" if is_fav else "☆"
            if st.button(star_icon, key=f"{prefix}_fav_{code}", use_container_width=True):
                toggle_favorite_and_refresh(code)

        r[1].markdown(wrap_cell(code, bold=True), unsafe_allow_html=True)
        r[2].markdown(wrap_cell(row['名称'], color="#64748b", font_size="13px"), unsafe_allow_html=True)

        r[3].markdown(wrap_cell(f"<span class='score-pill'>{row['评分']}</span>"), unsafe_allow_html=True)
        r[4].markdown(wrap_cell(row.get('收盘价', '-')), unsafe_allow_html=True)
        r[5].markdown(wrap_cell(row.get('股息率', '-'), color="#f59e0b", bold=True), unsafe_allow_html=True)
        
        indicators = ['120日线', '250日线', '日中下轨', '周中下轨', '日MACD', '周MACD']
        for i, field in enumerate(indicators):
            val = str(row[field]) if field in row else "-"
            r[i+6].markdown(format_indicator(val), unsafe_allow_html=True)
        
        with r[12]:
            if st.button("📝", key=f"{prefix}_ana_{code}", use_container_width=True):
                st.toast(f"加载 {code} 的分析报告...")

def inject_modern_css():
    st.markdown("""
        <style>
        /* 1. 按钮基础样式（仅针对需要点击的按钮） */
        div[data-testid="stColumn"] button {
            border: 1px solid #e2e8f0 !important;
            background-color: transparent !important;
            height: 42px !important;
            padding: 0 !important;
            margin: 0 !important;
            display: flex !important;
            justify-content: center !important;
            align-items: center !important;
            transition: all 0.2s;
        }
        
        /* 2. 可点击表头按钮样式 */
        div[data-testid="stColumn"] button[key*="_h_"] {
            border: none !important;
            font-size: 13px !important;
            color: #475569 !important; /* 排序字段颜色深一点提示可点 */
            font-weight: 700 !important;
        }

        div[data-testid="stColumn"] button:hover {
            background-color: #f8fafc !important;
            border-color: #cbd5e1 !important;
        }

        /* 3. 统一对齐容器 */
        .cell-container {
            height: 42px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
            width: 100%;
            overflow: hidden;
        }
        
        /* 4. 静态表头特有样式：去掉下划线防止视觉干扰，设置淡色 */
        .static-header {
            border-bottom: none !important;
            cursor: default; /* 改回普通光标 */
            user-select: none;
        }

        .score-pill {
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            color: #475569;
        }

        .stMarkdown div p { margin-bottom: 0 !important; }
        </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="多因子安全边际监控", layout="wide")
    init_db()
    inject_modern_css()

    if 'fav_set' not in st.session_state: st.session_state.fav_set = get_favorites()
    if 'sort_order' not in st.session_state: st.session_state.sort_order = 0
    if 'sort_col' not in st.session_state: st.session_state.sort_col = None

    st.title("📊 多因子安全边际监控系统")
    all_data = load_and_preprocess_data()
    
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        asset_filter = st.selectbox("🎯 资产类别", ["全部", "股票", "ETF"])
    with col_f2:
        search_query = st.text_input("🔍 搜索代码或名称", "").upper()

    display_df = all_data.copy()
    if asset_filter != "全部":
        display_df = display_df[display_df['类型'] == asset_filter]
    if search_query:
        display_df = display_df[display_df['代码'].astype(str).str.contains(search_query) | 
                                display_df['名称'].str.contains(search_query)]

    display_df = process_sorting(display_df)
    tab_market, tab_fav = st.tabs(["📋 市场大池", "⭐ 我的自选池"])

    with tab_market:
        render_modern_table(display_df, prefix="m")

    with tab_fav:
        fav_df = display_df[display_df['代码'].isin(st.session_state.fav_set)]
        render_modern_table(fav_df, prefix="f")

if __name__ == "__main__":
    main()