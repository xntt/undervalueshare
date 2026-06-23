"""
A股小市值异动监控工具
- 监控市值 < 100亿
- 排除北交所(8..) + 科创板(688..)
- 规则：连续3日上涨 + 成交量异动 (>2x 20日均量)
"""

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
import warnings
warnings.filterwarnings('ignore')

# ============== 配置 ==============
class Config:
    MARKET_CAP_MAX = 100
    CONSECUTIVE_DAYS = 3
    VOLUME_THRESHOLD = 2.0

# ============== 数据获取 ==============
class DataFetcher:
    @staticmethod
    def get_all_stocks_list():
        try:
            df = ak.stock_zh_a_spot_em()
            return df
        except Exception as e:
            st.error(f"获取股票列表失败: {e}. 请检查网络/akshare版本")
            return pd.DataFrame()

    @staticmethod
    def filter_stocks(df):
        if df.empty:
            return df
        
        # 排除板块
        exclude_prefixes = ['8', '688', '689', '430', '830', '87', '88']
        df = df[~df['代码'].astype(str).str.startswith(tuple(exclude_prefixes))]
        
        # 市值过滤 (总市值单位：元)
        df['总市值'] = pd.to_numeric(df['总市值'], errors='coerce')
        df = df[(df['总市值'] > 0) & (df['总市值'] < Config.MARKET_CAP_MAX * 1e8)]
        return df

    @staticmethod
    def get_stock_kline(code, days=30):
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")  # 多取几天防空
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )
            if not df.empty:
                df = df.sort_values('日期')
            return df
        except Exception as e:
            # st.warning(f"{code} K线获取失败: {e}")
            return pd.DataFrame()

# ============== 分析模块 ==============
class AlertAnalyzer:
    @staticmethod
    def check_consecutive_rise(df, days=3):
        if len(df) < days:
            return False
        recent = df.tail(days)['收盘']
        # 严格连续上涨
        return all(recent.iloc[i] > recent.iloc[i-1] for i in range(1, len(recent)))

    @staticmethod
    def check_volume_surge(df, threshold=2.0):
        if len(df) < 20:
            return False
        recent_vol = df.tail(1)['成交量'].iloc[0]
        avg_vol = df.tail(20)['成交量'].mean()
        return recent_vol > avg_vol * threshold

    @staticmethod
    def analyze_stock(code, name):
        try:
            kline = DataFetcher.get_stock_kline(code, days=40)
            if kline.empty or len(kline) < Config.CONSECUTIVE_DAYS + 5:
                return None

            is_consecutive = AlertAnalyzer.check_consecutive_rise(kline, Config.CONSECUTIVE_DAYS)
            is_volume_surge = AlertAnalyzer.check_volume_surge(kline, Config.VOLUME_THRESHOLD)

            if not (is_consecutive and is_volume_surge):
                return None

            latest = kline.iloc[-1]
            prev = kline.iloc[-2]
            price_change = (latest['收盘'] - prev['收盘']) / prev['收盘'] * 100

            if price_change <= 0:
                return None

            vol_ratio = latest['成交量'] / kline.tail(20)['成交量'].mean()

            return {
                'code': code,
                'name': name,
                'alert_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
                'consecutive_days': Config.CONSECUTIVE_DAYS,
                'price_change': round(price_change, 2),
                'volume_ratio': round(vol_ratio, 2),
                'turnover': round(latest.get('换手率', 0), 2),
                'amplitude': round((latest['最高'] - latest['最低']) / prev['收盘'] * 100, 2),
                'current_price': round(latest['收盘'], 2),
                'total_volume': int(latest['成交量']),
                'trend': 'up'
            }
        except Exception:
            return None

    def scan_market(self, progress_callback=None):
        all_stocks = DataFetcher.get_all_stocks_list()
        filtered = DataFetcher.filter_stocks(all_stocks)
        
        if filtered.empty:
            return []
        
        alerts = []
        total = len(filtered)
        
        with ThreadPoolExecutor(max_workers=8) as executor:  # 降低并发防限流
            future_to_stock = {
                executor.submit(AlertAnalyzer.analyze_stock, row['代码'], row['名称']): row 
                for _, row in filtered.iterrows()
            }
            for i, future in enumerate(as_completed(future_to_stock)):
                if progress_callback:
                    progress_callback((i + 1) / total)
                result = future.result()
                if result:
                    alerts.append(result)
        
        alerts.sort(key=lambda x: x['price_change'], reverse=True)
        return alerts

# ============== Streamlit UI ==============
def init_session_state():
    if 'alerts' not in st.session_state:
        st.session_state.alerts = []
    if 'last_scan' not in st.session_state:
        st.session_state.last_scan = None
    if 'scanning' not in st.session_state:
        st.session_state.scanning = False

def main():
    init_session_state()
    st.set_page_config(page_title="A股小市值异动监控", page_icon="📈", layout="wide")
    st.title("📊 A股小市值异动监控系统")

    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 设置")
        Config.MARKET_CAP_MAX = st.slider("最大市值(亿)", 10, 200, 100)
        Config.CONSECUTIVE_DAYS = st.slider("连续上涨天数", 2, 7, 3)
        Config.VOLUME_THRESHOLD = st.slider("量比阈值", 1.0, 5.0, 2.0)
        
        st.subheader("操作")
        if st.button("🚀 立即扫描", type="primary", use_container_width=True):
            run_scan()
        
        if st.button("📥 导出CSV", use_container_width=True) and st.session_state.alerts:
            export_results()

        if st.session_state.last_scan:
            st.caption(f"上次扫描: {st.session_state.last_scan}")

    # 主页面
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("预警数量", len(st.session_state.alerts))
    with col2: 
        avg_chg = np.mean([a['price_change'] for a in st.session_state.alerts]) if st.session_state.alerts else 0
        st.metric("平均涨幅", f"{avg_chg:.2f}%")
    with col3: 
        avg_vol = np.mean([a['volume_ratio'] for a in st.session_state.alerts]) if st.session_state.alerts else 0
        st.metric("平均量比", f"{avg_vol:.2f}")
    with col4: st.metric("监控范围", f"<{Config.MARKET_CAP_MAX}亿")

    st.divider()
    st.subheader("🚨 预警列表")

    if st.session_state.alerts:
        df = pd.DataFrame(st.session_state.alerts)
        display_df = df.copy()
        display_df.columns = ['代码', '名称', '预警时间', '连涨天数', '涨幅%', '量比', '换手率%', '振幅%', '现价', '成交量', '趋势']
        
        # 样式
        def highlight(val):
            if isinstance(val, (int, float)):
                if val > 5: return 'background-color: #ff4444; color: white'
                elif val > 3: return 'background-color: #ffaa00; color: white'
            return ''
        
        styled = display_df.style.map(highlight, subset=['涨幅%'])
        st.dataframe(styled, use_container_width=True, height=500)
        
        # 详情
        st.subheader("📈 股票详情")
        selected = st.selectbox("选择查看K线", options=df['code'].tolist(), 
                               format_func=lambda x: f"{x} - {df[df['code']==x]['name'].iloc[0]}")
        if selected:
            render_detail(selected)
    else:
        st.info("点击『立即扫描』开始监控。首次扫描可能需要1-3分钟。")

def run_scan():
    st.session_state.scanning = True
    progress_bar = st.progress(0)
    status = st.empty()
    
    analyzer = AlertAnalyzer()
    
    def update(p):
        progress_bar.progress(int(p * 100))
        status.text(f"扫描进度: {int(p*100)}% ({len(st.session_state.alerts)} 个预警)")
    
    with st.spinner("全市场扫描中..."):
        alerts = analyzer.scan_market(update)
        st.session_state.alerts = alerts
        st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    progress_bar.empty()
    status.empty()
    st.session_state.scanning = False
    st.rerun()

def export_results():
    df = pd.DataFrame(st.session_state.alerts)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("下载CSV", csv, f"alerts_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")

def render_detail(code):
    kline = DataFetcher.get_stock_kline(code, days=30)
    if not kline.empty:
        col1, col2 = st.columns(2)
        with col1:
            st.line_chart(kline.set_index('日期')['收盘'])
        with col2:
            st.bar_chart(kline.set_index('日期')['成交量'])

if __name__ == "__main__":
    main()
