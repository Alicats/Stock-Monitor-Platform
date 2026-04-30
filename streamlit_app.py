import streamlit as st
import pandas as pd
import sqlite3
import extra_streamlit_components as stx
import time
import datetime

def init_db():
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    # 会员表
    cursor.execute("CREATE TABLE IF NOT EXISTS members (email TEXT PRIMARY KEY)")
    # 自选表 (按邮箱区分)
    cursor.execute("CREATE TABLE IF NOT EXISTS favorites (email TEXT, code TEXT, PRIMARY KEY (email, code))")
    conn.commit()
    conn.close()

def check_member(email):
    if not email: return False
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM members WHERE email = ?", (email.strip(),))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_user_favorites(email):
    if not email: return set()
    conn = sqlite3.connect("stock_monitor.db")
    try:
        df = pd.read_sql("SELECT code FROM favorites WHERE email = ?", conn, params=(email,))
        return set(df['code'].tolist())
    except:
        return set()
    finally:
        conn.close()

def toggle_favorite(email, code):
    if not email: return
    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    current_favs = get_user_favorites(email)
    if code in current_favs:
        cursor.execute("DELETE FROM favorites WHERE email = ? AND code = ?", (email, code))
    else:
        cursor.execute("INSERT OR REPLACE INTO favorites (email, code) VALUES (?, ?)", (email, code))
    conn.commit()
    conn.close()


# 持久化登录逻辑（Cookie 读写）
def manage_login():
    cookie_manager = stx.CookieManager(key="mymanager")
    
    # 1. 初始化变量
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_email' not in st.session_state:
        st.session_state.user_email = None
    if 'fav_set' not in st.session_state:
        st.session_state.fav_set = set()
    # 关键：退出锁定状态，直到 Cookie 彻底变成空字符串为止
    if 'logout_in_progress' not in st.session_state:
        st.session_state.logout_in_progress = False

    # 2. 读取 Cookie
    saved_email = cookie_manager.get(cookie="user_email_token")
    # print(f"DEBUG - Cookie: {saved_email}")

    # 3. 【核心拦截逻辑】
    # 如果处于注销过程中，且读到了旧数据，强行重置为空
    if st.session_state.logout_in_progress:
        if saved_email == "" or saved_email is None:
            # 只有当 Cookie 确实变为空了，才解除注销锁定
            st.session_state.logout_in_progress = False
        else:
            # 否则，继续强行覆盖 Cookie 为空，并忽略本次读取的值
            cookie_manager.set("user_email_token", "", key=f"retry_clear_{time.time()}")
            saved_email = None 

    # 4. 自动回填逻辑（增加 logout_in_progress 拦截）
    if saved_email and not st.session_state.logged_in and not st.session_state.logout_in_progress:
        if check_member(saved_email):
            st.session_state.logged_in = True
            st.session_state.user_email = saved_email
            st.session_state.fav_set = get_user_favorites(saved_email)
            st.rerun()
      

    with st.sidebar:
        st.title("👤 用户中心")
        
        if not st.session_state.logged_in:
            email_input = st.text_input("请输入授权邮箱登录", key="login_input")
            if st.button("登录", use_container_width=True, key="do_login_btn"):
                if check_member(email_input):
                    st.session_state.logged_in = True
                    st.session_state.user_email = email_input
                    st.session_state.fav_set = get_user_favorites(email_input)
                    st.session_state.logout_in_progress = False # 登录时确保锁是开的
                    
                    expires = datetime.datetime.now() + datetime.timedelta(days=7)
                    cookie_manager.set("user_email_token", email_input, expires_at=expires, key="js_set_login")
                    st.success("登录成功！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("邮箱不存在，请联系管理员。")
        else:
            st.write(f"当前账号: **{st.session_state.user_email}**")
            
            if st.button("退出登录", key="do_logout_btn", use_container_width=True):
                # 标记正在注销
                st.session_state.logout_in_progress = True
                
                # 立即清理内存
                st.session_state.logged_in = False
                st.session_state.user_email = None
                st.session_state.fav_set = set()
                
                # 清除 Cookie
                cookie_manager.set("user_email_token", "", key=f"js_logout_{time.time()}")
                
                st.warning("正在退出...")
                time.sleep(0.5) 
                st.rerun()


# --- 2. 样式处理工具 ---
def wrap_cell(content, color="#31333F", bold=False, font_size="13px", is_header=False):
    weight = "600" if (bold or is_header) else "normal"
    extra_class = "static-header" if is_header else ""
    return f'<div class="cell-container {extra_class}" style="color:{color}; font-weight:{weight}; font-size:{font_size};">{content}</div>'

def format_indicator(val):
    if not isinstance(val, str) or '(' not in val:
        return wrap_cell(val)
    parts = val.split('(')
    symbol, description = parts[0].strip(), parts[1].replace(')', '').strip()
    color = "#ff4b4b" if "✘" in symbol else "#29b09d"
    content = f'<div style="line-height: 1.1;"><div style="color: {color}; font-size: 16px; font-weight: bold;">{symbol}</div><div style="color: #808495; font-size: 9px; white-space: nowrap;">{description}</div></div>'
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
        return pd.DataFrame(columns=['代码', '名称', '评分', '收盘价', '股息率', '120日线', '250日线', '日中下轨', '周中下轨', '月中下轨', '日MACD', '周MACD', '类型'])

def process_sorting(df):
    col = st.session_state.sort_col
    order = st.session_state.sort_order
    if order == 0 or col is None or df.empty:
        return df
    
    temp_df = df.copy()
    if col == "股息率":
        temp_df['_v'] = temp_df['股息率'].astype(str).str.replace('%', '').replace('-', '-1').replace('nan', '-1').astype(float)
        temp_df = temp_df.sort_values('_v', ascending=(order == 2))
        temp_df = temp_df.drop(columns=['_v'])
    elif col == "评分":
        temp_df = temp_df.sort_values("评分", ascending=(order == 2))
    return temp_df

def render_modern_header(label, prefix, is_sortable=True):
    if is_sortable:
        icon = ""
        if st.session_state.sort_col == label:
            icon = " 🔽" if st.session_state.sort_order == 1 else " 🔼"
        
        if st.button(f"{label}{icon}", key=f"{prefix}_h_{label}", use_container_width=True):
            if st.session_state.sort_col == label:
                st.session_state.sort_order = (st.session_state.sort_order + 1) % 3
                if st.session_state.sort_order == 0: st.session_state.sort_col = None
            else:
                st.session_state.sort_col = label
                st.session_state.sort_order = 1
            st.rerun()
    else:
        st.markdown(wrap_cell(label, color="#94a3b8", font_size="12px", is_header=True), unsafe_allow_html=True)

# 数据隔离渲染（未登录 vs 已登录）
def render_modern_table(all_data, prefix="market"):
    is_login = st.session_state.get('logged_in', False)
    
    # 权限分流
    if not is_login:
        df_to_show = all_data[all_data['代码'].isin(['601988.SH', '513530.SH'])]
        st.info("💡 当前为预览模式，仅展示 2 条示例。登录后查看全部。")
    else:
        df_to_show = all_data

    if df_to_show.empty:
        st.info("💡 暂无匹配数据")
        return

    col_ratios = [0.5, 0.9, 1.1, 0.7, 0.7, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.5]
    h_cols = st.columns(col_ratios)
    header_config = {
        0: ("自选", False), 1: ("代码", False), 2: ("名称", False), 3: ("评分", True),  
        4: ("现价", False), 5: ("股息率", True), 6: ("120日", False), 7: ("250日", False), 
        8: ("日中轨", False), 9: ("周中轨", False), 10: ("月中轨", False), 11: ("日MACD", False), 
        12: ("周MACD", False), 13: ("分析", False)
    }

    # 表头渲染 (使用你之前的 render_modern_header 函数，此处略，需保持代码完整)
    for idx, (label, sortable) in header_config.items():
        with h_cols[idx]:
            # 注意：需确保 render_modern_header 在当前作用域可用
            render_modern_header(label, prefix, is_sortable=sortable)
    
    for index, row in df_to_show.iterrows():
        r = st.columns(col_ratios)
        code = row['代码']
        
        with r[0]:
            if not is_login:
                st.button("☆", key=f"no_login_{code}_{prefix}", disabled=True)
            else:
                is_fav = code in st.session_state.fav_set
                star_icon = "★" if is_fav else "☆"
                if st.button(star_icon, key=f"{prefix}_fav_{code}_{index}"):
                    # print(f"DEBUG - 点击了 {st.session_state.user_email} {code}")
                    toggle_favorite(st.session_state.user_email, code)
                    st.session_state.fav_set = get_user_favorites(st.session_state.user_email)
                    st.rerun()

        r[1].markdown(wrap_cell(code, bold=True, font_size="12px"), unsafe_allow_html=True)
        r[2].markdown(wrap_cell(row['名称'], color="#64748b", font_size="12px"), unsafe_allow_html=True)
        r[3].markdown(wrap_cell(f"<span class='score-pill'>{row['评分']}</span>"), unsafe_allow_html=True)
        r[4].markdown(wrap_cell(row.get('收盘价', '-')), unsafe_allow_html=True)
        r[5].markdown(wrap_cell(row.get('股息率', '-'), color="#f59e0b", bold=True), unsafe_allow_html=True)
        
        indicators = ['120日线', '250日线', '日中下轨', '周中下轨', '月中下轨', '日MACD', '周MACD']
        for i, field in enumerate(indicators):
            val = str(row[field]) if field in row else "-"
            r[i+6].markdown(format_indicator(val), unsafe_allow_html=True)
        
        with r[13]:
            if st.button("📝", key=f"{prefix}_ana_{code}_{index}", use_container_width=True):
                st.toast(f"加载 {code} 的分析报告...")

def inject_modern_css():
    st.markdown("""
        <style>
        /* 1. 强制缩小按钮高度和文字，防止溢出换行 */
        div[data-testid="stColumn"] button {
            border: 1px solid #e2e8f0 !important;
            background-color: transparent !important;
            height: 32px !important;  /* 缩小高度 */
            min-height: 32px !important;
            padding: 0 !important;
            font-size: 12px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        
        /* 针对表头排序按钮的特殊处理 */
        div[data-testid="stColumn"] button[key*="_h_"] {
            border: none !important;
            font-weight: 700 !important;
            background: #f8fafc !important;
        }

        /* 2. 核心：禁止单元格内容换行，防止撑开高度 */
        .cell-container {
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            border-bottom: 1px solid #f1f5f9;
            width: 100%;
            white-space: nowrap; 
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .score-pill {
            background: #f1f5f9;
            padding: 1px 4px;
            border-radius: 4px;
            font-size: 11px;
            color: #475569;
        }

        /* 隐藏 Streamlit 默认的列间距，让布局更紧凑 */
        div[data-testid="column"] {
            padding: 0 2px !important;
        }
        </style>
    """, unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="多因子监控", layout="wide")
    
    inject_modern_css()
    
    # 1. 核心：首先处理登录和 Cookie
    manage_login()

    # 剩下的逻辑要根据 session_state 来展示
    if not st.session_state.get('logged_in'):
        st.info("👋 请在左侧菜单登录后查看完整监控数据")
    #     # render_modern_table(...)
    # else:
    #     st.info("👋 请在左侧菜单登录后查看完整监控数据")

    # 2. 初始化排序状态
    if 'sort_order' not in st.session_state: st.session_state.sort_order = 0
    if 'sort_col' not in st.session_state: st.session_state.sort_col = None

    st.title("📊 多因子安全边际监控系统")
    all_data = load_and_preprocess_data()
    
    # 过滤器
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
        if st.session_state.logged_in:
            fav_df = display_df[display_df['代码'].isin(st.session_state.fav_set)]
            render_modern_table(fav_df, prefix="f")
        else:
            st.warning("请登录后查看自选池")


def add_authorized_member(email):
    """
    手动往数据库录入授权邮箱账号
    """
    email = email.strip()
    if not email:
        print("❌ 邮箱不能为空")
        return

    conn = sqlite3.connect("stock_monitor.db")
    cursor = conn.cursor()
    try:
        # 使用 INSERT OR IGNORE 防止重复录入报错
        cursor.execute("INSERT OR IGNORE INTO members (email) VALUES (?)", (email,))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"✅ 成功录入授权邮箱: {email}")
        else:
            print(f"ℹ️ 邮箱 {email} 已存在，无需重复录入")
    except Exception as e:
        print(f"❌ 录入失败: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    
    # 【手动录入区】
    # 每次有新付费用户时，在这里写下邮箱运行一次，然后就可以删掉或注释掉这行
    # add_authorized_member("778988525@qq.com")

    main()