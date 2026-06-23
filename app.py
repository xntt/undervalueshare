"""
A股小市值异动监控工具
- 监控市值100亿以下企业
- 剔除北交所(8开头)和科创板(688开头)
- 预警规则：大资金异动 + 连续3日K线正向涨幅
- 数据源：新浪财经
- 可视化：Streamlit
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak  # 备用数据源
from apscheduler.schedulers.background import BackgroundScheduler
import warnings
warnings.filterwarnings('ignore')

# ============== 配置 ==============
class Config:
    # 市值阈值（亿元）
    MARKET_CAP_MAX = 100
    
    # 连续上涨天数
    CONSECUTIVE_DAYS = 3
    
    # 成交量异动阈值（相对于20日均量）
    VOLUME_THRESHOLD = 2.0
    
    # 涨幅阈值（%）
    PRICE_CHANGE_THRESHOLD = 2.0
    
    # 排除的板块
    EXCLUDE_PREFIXES = ['8', '688', '689', '430', '830', '87', '88']
    
    # 监控股票池（沪深主板+创业板+中小板）
    MARKETS = ['sh', 'sz']

# ============== 数据获取模块 ==============
class DataFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
            'Referer': 'https://finance.sina.com.cn'
        }
    
    def get_all_stocks_list(self):
        """获取全量股票列表"""
        try:
            # 使用akshare获取股票列表
            stock_df = ak.stock_zh_a_spot_em()
            return stock_df
        except Exception as e:
            st.error(f"获取股票列表失败: {e}")
            return pd.DataFrame()
    
    def filter_stocks(self, df):
        """筛选符合条件的股票"""
        if df.empty:
            return df
            
        # 排除北交所和科创板
        def is_excluded(code):
            code_str = str(code)
            return any(code_str.startswith(prefix) for prefix in Config.EXCLUDE_PREFIXES)
        
        df['is_excluded'] = df['代码'].apply(is_excluded)
        df = df[~df['is_excluded']]
        
        # 筛选市值（总市值 < 100亿）
        # 新浪数据格式转换
        df['总市值'] = pd.to_numeric(df.get('总市值', 0), errors='coerce')
        df = df[df['总市值'] > 0]
        df = df[df['总市值'] < Config.MARKET_CAP_MAX * 1e8]  # 转换为元
        
        return df
    
    def get_stock_kline(self, code, days=10):
        """获取股票K线数据"""
        try:
            # 转换代码格式
            if code.startswith('6'):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"
            
            # 使用akshare获取历史数据
            df = ak.stock_zh_a_hist(
                symbol=code, 
                period="daily",
                start_date=(datetime.now() - timedelta(days=days)).strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
                adjust="qfq"
            )
            return df
        except Exception as e:
            return pd.DataFrame()
    
    def get_realtime_data(self, codes):
        """获取实时数据（批量）"""
        if not codes:
            return pd.DataFrame()
        
        try:
            # 分批获取避免请求过大
            batch_size = 50
            results = []
            
            for i in range(0, len(codes), batch_size):
                batch = codes[i:i+batch_size]
                # 使用akshare实时行情
                df = ak.stock_zh_a_spot_em()
                df = df[df['代码'].isin(batch)]
                results.append(df)
                time.sleep(0.1)
            
            return pd.concat(results, ignore_index=True) if results else pd.DataFrame()
        except Exception as e:
            return pd.DataFrame()

# ============== 预警分析模块 ==============
class AlertAnalyzer:
    def __init__(self):
        self.fetcher = DataFetcher()
    
    def check_consecutive_rise(self, df, days=3):
        """检查连续上涨"""
        if len(df) < days:
            return False
        
        recent = df.tail(days)
        # 检查是否每日收盘价都高于前一日
        rises = (recent['收盘'].diff() > 0).sum()
        return rises >= days - 1
    
    def check_volume_surge(self, df, threshold=2.0):
        """检查成交量异动"""
        if len(df) < 20:
            return False
        
        recent_vol = df.tail(1)['成交量'].values[0]
        avg_vol = df.tail(20)['成交量'].mean()
        
        return recent_vol > avg_vol * threshold
    
    def calculate_indicators(self, df):
        """计算技术指标"""
        if len(df) < 5:
            return {}
        
        latest = df.tail(1).iloc[0]
        prev = df.tail(2).iloc[0]
        
        # 计算涨幅
        price_change = (latest['收盘'] - prev['收盘']) / prev['收盘'] * 100
        
        # 计算成交量比
        vol_ratio = latest['成交量'] / df.tail(20)['成交量'].mean()
        
        return {
            'price_change': price_change,
            'volume_ratio': vol_ratio,
            'turnover': latest.get('换手率', 0),
            'amplitude': (latest['最高'] - latest['最低']) / prev['收盘'] * 100
        }
    
    def analyze_stock(self, code, name):
        """分析单只股票"""
        try:
            # 获取K线数据
            kline = self.fetcher.get_stock_kline(code, days=30)
            if kline.empty or len(kline) < 5:
                return None
            
            # 检查连续上涨
            is_consecutive = self.check_consecutive_rise(kline, Config.CONSECUTIVE_DAYS)
            
            # 检查成交量异动
            is_volume_surge = self.check_volume_surge(kline, Config.VOLUME_THRESHOLD)
            
            # 计算指标
            indicators = self.calculate_indicators(kline)
            
            # 预警条件：连续上涨 + 成交量异动 + 正向涨幅
            if is_consecutive and is_volume_surge and indicators.get('price_change', 0) > 0:
                return {
                    'code': code,
                    'name': name,
                    'alert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'consecutive_days': Config.CONSECUTIVE_DAYS,
                    'price_change': round(indicators['price_change'], 2),
                    'volume_ratio': round(indicators['volume_ratio'], 2),
                    'turnover': round(indicators['turnover'], 2),
                    'amplitude': round(indicators['amplitude'], 2),
                    'current_price': kline.tail(1)['收盘'].values[0],
                    'total_volume': int(kline.tail(1)['成交量'].values[0]),
                    'trend': 'up'
                }
            
            return None
        except Exception as e:
            return None
    
    def scan_market(self, progress_callback=None):
        """全市场扫描"""
        # 获取股票列表
        all_stocks = self.fetcher.get_all_stocks_list()
        filtered = self.fetcher.filter_stocks(all_stocks)
        
        if filtered.empty:
            return []
        
        alerts = []
        total = len(filtered)
        
        # 多线程分析
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_stock = {
                executor.submit(
                    self.analyze_stock, 
                    row['代码'], 
                    row['名称']
                ): (row['代码'], row['名称']) 
                for _, row in filtered.iterrows()
            }
            
            completed = 0
            for future in as_completed(future_to_stock):
                completed += 1
                if progress_callback:
                    progress_callback(completed / total)
                
                result = future.result()
                if result:
                    alerts.append(result)
        
        # 按涨幅排序
        alerts.sort(key=lambda x: x['price_change'], reverse=True)
        return alerts

# ============== Streamlit 界面 ==============
def init_session_state():
    """初始化会话状态"""
    if 'alerts' not in st.session_state:
        st.session_state.alerts = []
    if 'last_scan' not in st.session_state:
        st.session_state.last_scan = None
    if 'watchlist' not in st.session_state:
        st.session_state.watchlist = []
    if 'scanning' not in st.session_state:
        st.session_state.scanning = False

def render_header():
    """渲染页面头部"""
    st.set_page_config(
        page_title="A股小市值异动监控",
        page_icon="📈",
        layout="wide"
    )
    
    st.title("📊 A股小市值异动监控系统")
    st.markdown("""
    **监控规则：**
    - 市值范围：< 100亿元
    - 排除板块：北交所、科创板
    - 预警条件：连续**3日**上涨 + 成交量异动(**>2倍**均量)
    """)

def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.header("⚙️ 监控设置")
        
        st.subheader("筛选条件")
        max_cap = st.slider("最大市值(亿)", 10, 200, 100)
        min_days = st.slider("连续上涨天数", 2, 7, 3)
        vol_threshold = st.slider("成交量异动倍数", 1.0, 5.0, 2.0)
        
        st.subheader("定时任务")
        auto_scan = st.checkbox("启用自动扫描", value=True)
        if auto_scan:
            st.info("⏰ 每日 09:30 和 15:00 自动扫描")
        
        st.subheader("操作")
        if st.button("🚀 立即扫描", type="primary", use_container_width=True):
            run_scan()
        
        if st.button("📥 导出结果", use_container_width=True):
            export_results()
        
        if st.session_state.last_scan:
            st.caption(f"上次扫描: {st.session_state.last_scan}")

def run_scan():
    """执行扫描"""
    st.session_state.scanning = True
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    analyzer = AlertAnalyzer()
    
    def update_progress(p):
        progress_bar.progress(min(int(p * 100), 100))
        status_text.text(f"扫描进度: {int(p * 100)}%")
    
    with st.spinner("正在全市场扫描..."):
        alerts = analyzer.scan_market(update_progress)
        st.session_state.alerts = alerts
        st.session_state.last_scan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    progress_bar.empty()
    status_text.empty()
    st.session_state.scanning = False
    st.rerun()

def export_results():
    """导出结果"""
    if not st.session_state.alerts:
        st.warning("暂无数据可导出")
        return
    
    df = pd.DataFrame(st.session_state.alerts)
    csv = df.to_csv(index=False).encode('utf-8-sig')
    
    st.download_button(
        label="下载CSV",
        data=csv,
        file_name=f"alerts_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

def render_dashboard():
    """渲染主仪表板"""
    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("预警股票数", len(st.session_state.alerts))
    with col2:
        avg_change = np.mean([a['price_change'] for a in st.session_state.alerts]) if st.session_state.alerts else 0
        st.metric("平均涨幅", f"{avg_change:.2f}%")
    with col3:
        avg_vol = np.mean([a['volume_ratio'] for a in st.session_state.alerts]) if st.session_state.alerts else 0
        st.metric("平均量比", f"{avg_vol:.2f}")
    with col4:
        st.metric("监控范围", "<100亿市值")
    
    st.divider()
    
    # 预警列表
    st.subheader("🚨 预警股票列表")
    
    if st.session_state.alerts:
        df = pd.DataFrame(st.session_state.alerts)
        
        # 格式化显示
        display_df = df.copy()
        display_df.columns = ['代码', '名称', '预警时间', '连涨天数', '涨幅%', '量比', '换手率%', '振幅%', '现价', '成交量', '趋势']
        
        # 添加样式
        def color_change(val):
            if isinstance(val, (int, float)):
                if val > 5:
                    return 'background-color: #ff4444; color: white'
                elif val > 3:
                    return 'background-color: #ff8800; color: white'
            return ''
        
        styled_df = display_df.style.applymap(color_change, subset=['涨幅%'])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            height=400
        )
        
        # 详细分析
        st.subheader("📈 详细分析")
        selected_code = st.selectbox(
            "选择股票查看详情",
            options=df['code'].tolist(),
            format_func=lambda x: f"{x} - {df[df['code']==x]['name'].values[0]}"
        )
        
        if selected_code:
            render_stock_detail(selected_code)
    else:
        st.info("暂无预警股票，点击左侧'立即扫描'开始监控")

def render_stock_detail(code):
    """渲染股票详情"""
    fetcher = DataFetcher()
    kline = fetcher.get_stock_kline(code, days=30)
    
    if not kline.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.line_chart(kline.set_index('日期')['收盘'], use_container_width=True)
            st.caption("近30日收盘价走势")
        
        with col2:
            st.bar_chart(kline.set_index('日期')['成交量'], use_container_width=True)
            st.caption("近30日成交量")

# ============== 定时任务 ==============
def setup_scheduler():
    """设置定时任务"""
    scheduler = BackgroundScheduler()
    
    # 开盘扫描
    scheduler.add_job(
        scheduled_scan,
        'cron',
        hour=9,
        minute=30,
        id='market_open_scan'
    )
    
    # 收盘扫描
    scheduler.add_job(
        scheduled_scan,
        'cron',
        hour=15,
        minute=0,
        id='market_close_scan'
    )
    
    scheduler.start()
    return scheduler

def scheduled_scan():
    """定时扫描任务"""
    print(f"[{datetime.now()}] 执行定时扫描...")
    # 这里可以添加通知逻辑（邮件、钉钉、企业微信等）

# ============== 主程序 ==============
def main():
    init_session_state()
    render_header()
    render_sidebar()
    render_dashboard()
    
    # 启动定时任务（仅在首次加载时）
    if 'scheduler' not in st.session_state:
        st.session_state.scheduler = setup_scheduler()

if __name__ == "__main__":
    main()
