#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SignalMonitor_KR 웹 대시보드
Flask 기반 실시간 모니터링 웹 인터페이스
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import json
import os
from collections import defaultdict

app = Flask(__name__)

# 설정
HISTORY_FILE = "signal_history.json"
CACHE_FILE = ".dashboard_cache.json"

# 섹터 정보
SECTOR_INFO = {
    "robot": {"name": "로봇", "emoji": "🤖"},
    "nuclear": {"name": "원전", "emoji": "⚡"},
    "power": {"name": "전력", "emoji": "⚡"},           # 🆕 전력 추가
    "defense": {"name": "방산", "emoji": "🚀"},
    "battery": {"name": "2차전지", "emoji": "🔋"},
    "semiconductor": {"name": "반도체", "emoji": "💾"},
    "lng": {"name": "LNG", "emoji": "🔥"},
    "shipbuilding": {"name": "조선", "emoji": "🚢"},
    "bio": {"name": "바이오", "emoji": "🧬"},          # 🆕 바이오 추가
    "entertainment": {"name": "엔터", "emoji": "🎤"}   # 🆕 엔터 추가
}

SIGNAL_INFO = {
    "STRONG_BUY": {"name": "강력 매수", "emoji": "🔥", "color": "#dc3545"},
    "BUY": {"name": "매수", "emoji": "📈", "color": "#28a745"},
    "HOLD": {"name": "보유", "emoji": "⏸️", "color": "#6c757d"},
    "SELL": {"name": "매도", "emoji": "⚠️", "color": "#ffc107"},
    "STRONG_SELL": {"name": "강력 매도", "emoji": "🚨", "color": "#dc3545"}
}

def load_history():
    """신호 히스토리 로드"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f"히스토리 로드 실패: {e}")
        return []

def get_recent_signals(limit=20):
    """최근 신호 가져오기"""
    history = load_history()
    # 최신순 정렬
    history_sorted = sorted(
        history, 
        key=lambda x: x.get('timestamp', ''), 
        reverse=True
    )
    return history_sorted[:limit]

def get_today_signals():
    """오늘 신호만 가져오기"""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    
    today_signals = [
        sig for sig in history 
        if sig.get('timestamp', '').startswith(today)
    ]
    return today_signals

def get_signal_statistics(days=7):
    """신호 통계 생성"""
    history = load_history()
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 최근 N일 신호만 필터링
    recent_signals = [
        sig for sig in history
        if datetime.strptime(sig.get('timestamp', ''), "%Y-%m-%d %H:%M:%S") > cutoff_date
    ]
    
    # 신호별 카운트
    signal_count = defaultdict(int)
    for sig in recent_signals:
        signal_count[sig.get('signal', 'UNKNOWN')] += 1
    
    # 섹터별 카운트
    sector_count = defaultdict(int)
    for sig in recent_signals:
        sector_count[sig.get('sector', 'unknown')] += 1
    
    # 시간대별 카운트
    hour_count = defaultdict(int)
    for sig in recent_signals:
        try:
            timestamp = sig.get('timestamp', '')
            hour = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").hour
            hour_count[hour] += 1
        except:
            pass
    
    return {
        'total_signals': len(recent_signals),
        'signal_count': dict(signal_count),
        'sector_count': dict(sector_count),
        'hour_count': dict(sorted(hour_count.items()))
    }

def get_system_status():
    """시스템 상태 확인"""
    try:
        # signal_history.json 파일 수정 시간
        if os.path.exists(HISTORY_FILE):
            last_modified = os.path.getmtime(HISTORY_FILE)
            last_update = datetime.fromtimestamp(last_modified)
            
            # 10분 이상 업데이트 없으면 경고
            time_diff = (datetime.now() - last_update).total_seconds()
            
            if time_diff < 600:  # 10분
                status = "running"
                status_text = "정상 작동 중"
            else:
                status = "warning"
                minutes_ago = int(time_diff / 60)
                status_text = f"업데이트 없음 ({minutes_ago}분 전)"
        else:
            status = "error"
            status_text = "히스토리 파일 없음"
        
        return {
            'status': status,
            'status_text': status_text,
            'last_update': last_update.strftime("%Y-%m-%d %H:%M:%S") if os.path.exists(HISTORY_FILE) else "N/A"
        }
    except Exception as e:
        return {
            'status': 'error',
            'status_text': f'오류: {str(e)}',
            'last_update': 'N/A'
        }

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """시스템 상태 API"""
    return jsonify(get_system_status())

@app.route('/api/signals/recent')
def api_recent_signals():
    """최근 신호 API"""
    limit = request.args.get('limit', 20, type=int)
    signals = get_recent_signals(limit)
    
    # 신호 정보 보강
    for sig in signals:
        sig['sector_name'] = SECTOR_INFO.get(sig.get('sector', ''), {}).get('name', sig.get('sector', ''))
        sig['sector_emoji'] = SECTOR_INFO.get(sig.get('sector', ''), {}).get('emoji', '📊')
        sig['signal_name'] = SIGNAL_INFO.get(sig.get('signal', ''), {}).get('name', sig.get('signal', ''))
        sig['signal_emoji'] = SIGNAL_INFO.get(sig.get('signal', ''), {}).get('emoji', '📊')
        sig['signal_color'] = SIGNAL_INFO.get(sig.get('signal', ''), {}).get('color', '#6c757d')
    
    return jsonify(signals)

@app.route('/api/signals/today')
def api_today_signals():
    """오늘 신호 API"""
    signals = get_today_signals()
    return jsonify({
        'count': len(signals),
        'signals': signals
    })

@app.route('/api/statistics')
def api_statistics():
    """통계 API"""
    days = request.args.get('days', 7, type=int)
    stats = get_signal_statistics(days)
    
    # 신호별 이름 추가
    signal_count_named = {}
    for signal, count in stats['signal_count'].items():
        signal_info = SIGNAL_INFO.get(signal, {})
        signal_count_named[signal] = {
            'count': count,
            'name': signal_info.get('name', signal),
            'emoji': signal_info.get('emoji', '📊'),
            'color': signal_info.get('color', '#6c757d')
        }
    
    # 섹터별 이름 추가
    sector_count_named = {}
    for sector, count in stats['sector_count'].items():
        sector_info = SECTOR_INFO.get(sector, {})
        sector_count_named[sector] = {
            'count': count,
            'name': sector_info.get('name', sector),
            'emoji': sector_info.get('emoji', '📊')
        }
    
    return jsonify({
        'total_signals': stats['total_signals'],
        'signal_count': signal_count_named,
        'sector_count': sector_count_named,
        'hour_count': stats['hour_count'],
        'period_days': days
    })

@app.route('/api/signals/search')
def api_search_signals():
    """신호 검색 API"""
    # 검색 파라미터
    sector = request.args.get('sector', None)
    signal_type = request.args.get('signal', None)
    date_from = request.args.get('date_from', None)
    date_to = request.args.get('date_to', None)
    
    history = load_history()
    
    # 필터링
    filtered = history
    
    if sector:
        filtered = [s for s in filtered if s.get('sector') == sector]
    
    if signal_type:
        filtered = [s for s in filtered if s.get('signal') == signal_type]
    
    if date_from:
        filtered = [s for s in filtered if s.get('timestamp', '') >= date_from]
    
    if date_to:
        date_to_end = date_to + " 23:59:59"
        filtered = [s for s in filtered if s.get('timestamp', '') <= date_to_end]
    
    # 최신순 정렬
    filtered_sorted = sorted(
        filtered,
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )
    
    return jsonify({
        'count': len(filtered_sorted),
        'signals': filtered_sorted
    })

@app.route('/api/signal/<stock_code>')
def api_signal_detail(stock_code):
    """특정 종목의 신호 상세 정보"""
    history = load_history()
    
    # 해당 종목의 모든 신호
    stock_signals = [
        sig for sig in history
        if sig.get('stock_code') == stock_code
    ]
    
    # 최신순 정렬
    stock_signals_sorted = sorted(
        stock_signals,
        key=lambda x: x.get('timestamp', ''),
        reverse=True
    )
    
    if stock_signals_sorted:
        latest = stock_signals_sorted[0]
        return jsonify({
            'stock_code': stock_code,
            'stock_name': latest.get('stock_name', ''),
            'sector': latest.get('sector', ''),
            'latest_signal': latest,
            'history_count': len(stock_signals_sorted),
            'all_signals': stock_signals_sorted[:10]  # 최근 10개
        })
    else:
        return jsonify({'error': '신호 없음'}), 404

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 SignalMonitor 웹 대시보드 시작")
    print("=" * 60)
    print(f"📊 접속 주소: http://localhost:5000")
    print(f"📱 모바일: http://[서버IP]:5000")
    print("=" * 60)
    
    # 0.0.0.0으로 바인딩하여 외부 접속 허용
    app.run(host='0.0.0.0', port=5000, debug=False)