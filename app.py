"""
A股小市值异动监控 - Streamlit Cloud 优化版
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
import warnings
import time

warnings.filterwarnings('ignore')

# ============== 配置 ==============
class Config:
    MARKET_CAP_MAX = 100
    CONSECUTIVE_DAYS = 3
    VOLUME_THRESHOLD = 2.0

# ============== 数据模块 ==============
class DataFetcher:
    @staticmethod
    @st.cache_data(ttl=3600)  # 缓存1小时
    def get_all_stocks_list():
        try:
            with st.spinner("正在获取全市场股票列表..."):
                df = ak.stock_zh_a_spot_em()
            return df
        except Exception as e:
            st.error(f"❌ 获取股票列表失败: {e}\n\n可能是网络波动或接口限流，请稍后重试。")
            return pd.DataFrame()

    @staticmethod
    def filter_stocks(df):
        if df.empty:
            return df
        # 排除北交所和科创板
        exclude = ['8', '688', '689', '430', '830', '87', '88']
        df = df[~df['代码'].astype(str).str.startswith(tuple(exclude))]
        
        df['总市值'] = pd.to_numeric(df.get('总市值', 0), errors='coerce')
        df = df[(df['总市值'] > 0) & (df['总市值'] < Config.MARKET_CAP_MAX * 1e8)]
        return df

    @staticmethod
    @st.cache_data(ttl=1800)  # 缓存30分钟
    def get_stock_kline(_code, days=40):
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(
                symbol=_code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            return df.sort_values('日期') if not df.empty else pd.DataFrame()
        except:
            return pd.DataFrame()

# ============== 分析模块 ==============
class AlertAnalyzer:
    @staticmethod
    def analyze_stock(code, name):
        try:
            kline = DataFetcher.get_stock_kline(code)
            if len(kline) < Config.CONSECUTIVE_DAYS + 10:
                return None

            # 连续上涨检查
            recent = kline.tail(Config.CONSECUTIVE_DAYS)['收盘']
            is_consecutive = all(recent.iloc[i] > recent.iloc[i-1] for i in range(1, len(recent)))

            # 量比检查
            if len(kline) >= 20:
                recent_vol = kline.iloc[-1]['成交量']
                avg_vol = kline.tail(20)['成交量'].mean()
                is_volume_surge = recent_vol > avg_vol * Config.VOLUME_THRESHOLD
            else:
                is_volume_surge = False

            if not (is_consecutive and is_volume_surge):
                return None

            latest = kline.iloc[-1]
            prev = kline.iloc[-2]
            price_change = (latest['收盘'] - prev['收盘']) / prev['收盘'] * 100

            if price_change <= 0:
                return None

            return {
                'code': code,
                'name': name,
                'alert_time': datetime.now().strftime("%Y-%m-%d %H:%M"),
                'consecutive_days': Config.CONSECUTIVE_DAYS,
                'price_change': round(price_change, 2),
                'volume_ratio': round(latest['成交量'] / kline.tail(20)['成交量'].mean(), 2),
                'turnover': round(latest.get('换手率', 0), 2),
                'amplitude': round((latest['最高'] - latest['最低']) / prev['收盘'] * 100, 2),
                'current_price': round(latest['收盘'], 2),
                'total_volume': int(latest['成交量']),
            }
        except:
            return None

    def scan_market(self):
        all_df = DataFetcher.get_all_stocks_list()
        filtered = DataFetcher.filter_stocks(all_df)
        
        if filtered.empty:
            st.error("未找到符合市值条件的股票")
            return []

        alerts = []
        total = len(filtered)
        progress_bar = st.progress(0)
        status_text = st.empty()

        with ThreadPoolExecutor(max_workers=6) as executor:   # Cloud版降低并发
            futures = {executor.submit(AlertAnalyzer.analyze_stock, row['代码'], row['名称']): row 
                      for _, row in filtered.iterrows()}
            
            for i, future in enumerate(as_completed(futures)):
                progress = (i + 1) / total
                progress_bar.progress(min(int(progress * 100), 100))
                status_text.text(f"扫描进度: {i+1}/{total} ({int(progress*100)}%)")
                
                result = future.result()
                if result:
                    alerts.append(result)
                    if len(alerts) > 0 and len(alerts) % 5 == 0:
                        status_text.text(f"已发现 {len(alerts)} 个预警...")

        progress_bar.empty()
        status_text.empty()
        
        alerts.sort(key=lambda x: x['price_change'], reverse=True)
        return alerts

# ============== 主界面 ==============
def main():
    st.set_page_config(page_title="A股小市值异动", page_icon="📈", layout="wide")
    st.title("📊 A股小市值异动监控（Streamlit Cloud）")

    # 侧边栏设置
    with st.sidebar:
        st.header("⚙️ 参数设置")
        Config.MARKET_CAP_MAX = st.slider("最大市值 (亿)", 10, 200, 100)
        Config.CONSECUTIVE_DAYS = st.slider("连续上涨天数", 2, 7, 3)
        Config.VOLUME_THRESHOLD = st.slider("成交量异动倍数", 1.0, 5.0, 2.0)
        
        st.divider()
        if st.button("🚀 开始全市场扫描", type="primary", use_container_width=True):
            st.session_state.run_scan = True

        st.caption("⚠️ 在线版单次扫描可能需要 1-4 分钟")

    # 执行扫描
    if st.session_state.get('run_scan', False):
        with st.spinner("正在扫描全市场小市值股票..."):
            analyzer = AlertAnalyzer()
            alerts = analyzer.scan_market()
            
            st.session_state.alerts = alerts
            st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.run_scan = False
            st.rerun()

    # 展示结果
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("当前预警", len(st.session_state.get('alerts', [])))
    with col2:
        alerts = st.session_state.get('alerts', [])
        avg_change = np.mean([a['price_change'] for a in alerts]) if alerts else 0
        st.metric("平均涨幅", f"{avg_change:.2f}%")
    with col3:
        st.metric("上次扫描", st.session_state.get('last_scan', '从未'))

    st.divider()

    if alerts := st.session_state.get('alerts', []):
        df = pd.DataFrame(alerts)
        display_df = df.copy()
        display_df.columns = ['代码','名称','预警时间','连涨天数','涨幅%','量比','换手率%','振幅%','现价','成交量']
        
        # 高亮
        def color(val):
            if isinstance(val, (int,float)) and val > 5:
                return 'background-color: #ff4d4d; color:white'
            elif isinstance(val, (int,float)) and val > 3:
                return 'background-color: #ffaa00; color:white'
            return ''
        
        styled = display_df.style.map(color, subset=['涨幅%'])
        st.dataframe(styled, use_container_width=True, height=500)

        # 详情
        if st.button("查看选中股票K线"):
            code = st.selectbox("选择股票", df['code'].tolist(), 
                              format_func=lambda x: f"{x} - {df[df['code']==x]['name'].iloc[0]}")
            if code:
                kline = DataFetcher.get_stock_kline(code)
                if not kline.empty:
                    st.line_chart(kline.set_index('日期')[['收盘', '成交量']])
    else:
        st.info("👈 点击左侧按钮开始扫描")

if __name__ == "__main__":
    # 初始化 session_state
    if 'alerts' not in st.session_state:
        st.session_state.alerts = []
    if 'last_scan' not in st.session_state:
        st.session_state.last_scan = None
    if 'run_scan' not in st.session_state:
        st.session_state.run_scan = False
    
    main()
