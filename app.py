import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import akshare as ak
import warnings
import time

warnings.filterwarnings('ignore')

st.set_page_config(page_title="A股小市值监控", layout="wide")

class Config:
    MARKET_CAP_MAX = 100
    CONSECUTIVE_DAYS = 3
    VOLUME_THRESHOLD = 2.0

@st.cache_data(ttl=3600)
def get_stock_list():
    try:
        # 优先尝试腾讯财经
        df = ak.stock_zh_a_spot_tx()
        st.success(f"✅ 使用腾讯财经获取到 {len(df)} 只股票")
        return df
    except:
        try:
            df = ak.stock_zh_a_spot_em()
            st.info("使用东财接口")
            return df
        except Exception as e:
            st.error(f"❌ 所有数据源都失败: {e}")
            return pd.DataFrame()

def filter_stocks(df):
    if df.empty:
        return df
    exclude = ['8', '688', '689', '430', '830', '87', '88']
    df = df[~df['代码'].astype(str).str.startswith(tuple(exclude))]
    df['总市值'] = pd.to_numeric(df.get('总市值', df.get('总市值(元)', 0)), errors='coerce')
    df = df[(df['总市值'] > 0) & (df['总市值'] < Config.MARKET_CAP_MAX * 1e8)]
    return df

@st.cache_data(ttl=1800)
def get_kline(code, days=40):
    try:
        return ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq"
        )
    except:
        return pd.DataFrame()

def analyze_one(code, name):
    kline = get_kline(code)
    if len(kline) < 25:
        return None
    
    recent = kline.tail(Config.CONSECUTIVE_DAYS)['收盘']
    is_consec = all(recent.iloc[i] > recent.iloc[i-1] for i in range(1, len(recent)))
    
    if not is_consec:
        return None
    
    recent_vol = kline.iloc[-1]['成交量']
    avg_vol = kline.tail(20)['成交量'].mean()
    if recent_vol <= avg_vol * Config.VOLUME_THRESHOLD:
        return None
    
    latest = kline.iloc[-1]
    prev = kline.iloc[-2]
    chg = (latest['收盘'] - prev['收盘']) / prev['收盘'] * 100
    
    if chg <= 0:
        return None
    
    return {
        'code': code, 'name': name, 'alert_time': datetime.now().strftime("%H:%M"),
        'price_change': round(chg, 2),
        'volume_ratio': round(recent_vol / avg_vol, 2),
        'current_price': round(latest['收盘'], 2),
        'amplitude': round((latest['最高'] - latest['最低']) / prev['收盘'] * 100, 2),
    }

# ============== 主界面 ==============
if 'alerts' not in st.session_state:
    st.session_state.alerts = []
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = None

st.title("📊 A股小市值异动监控（腾讯优先）")

with st.sidebar:
    st.header("设置")
    Config.MARKET_CAP_MAX = st.slider("最大市值(亿)", 10, 200, 100)
    Config.CONSECUTIVE_DAYS = st.slider("连涨天数", 2, 7, 3)
    Config.VOLUME_THRESHOLD = st.slider("量比阈值", 1.0, 5.0, 2.0)
    
    if st.button("🚀 开始扫描", type="primary", use_container_width=True):
        st.session_state.run_scan = True

if st.session_state.get('run_scan', False):
    st.session_state.run_scan = False
    with st.spinner("正在扫描（使用腾讯/东财接口）... 这可能需要 1-3 分钟"):
        df_list = get_stock_list()
        filtered = filter_stocks(df_list)
        
        if filtered.empty:
            st.error("未能获取股票列表")
        else:
            alerts = []
            progress = st.progress(0)
            status = st.empty()
            total = len(filtered)
            
            for i, (_, row) in enumerate(filtered.iterrows()):
                result = analyze_one(row['代码'], row['名称'])
                if result:
                    alerts.append(result)
                progress.progress(min((i+1)/total, 1.0))
                status.text(f"已处理 {i+1}/{total} 只股票，发现 {len(alerts)} 个预警")
                time.sleep(0.05)  # 避免请求过快
            
            st.session_state.alerts = alerts
            st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M")
            st.success(f"扫描完成！发现 {len(alerts)} 个符合条件的股票")
            st.rerun()

# 显示结果
alerts = st.session_state.get('alerts', [])
col1, col2, col3 = st.columns(3)
col1.metric("预警数量", len(alerts))
if alerts:
    avg = np.mean([a['price_change'] for a in alerts])
    col2.metric("平均涨幅", f"{avg:.2f}%")
col3.metric("上次扫描", st.session_state.get('last_scan', '未扫描'))

if alerts:
    df = pd.DataFrame(alerts)
    st.dataframe(df, use_container_width=True)
    
    code = st.selectbox("查看K线", df['code'])
    if code:
        k = get_kline(code)
        if not k.empty:
            st.line_chart(k.set_index('日期')['收盘'])
else:
    st.info("点击左侧「开始扫描」按钮")
