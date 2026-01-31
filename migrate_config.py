#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
설정 파일 마이그레이션 스크립트
기존 signal_trading_config.json을 3개 파일로 분리합니다.
"""

import json
import os
from datetime import datetime

def migrate_config():
    """기존 설정을 3개 파일로 분리"""
    
    old_file = "signal_trading_config.json"
    
    # 1. 기존 파일 백업
    if os.path.exists(old_file):
        backup_file = f"signal_trading_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(old_file, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(old_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 기존 설정 백업 완료: {backup_file}")
    else:
        print("❌ 기존 설정 파일이 없습니다.")
        return
    
    # 2. budget 파일 생성
    budget_data = {
        "_comment": "========== 투자 예산 및 리스크 관리 설정 ==========",
        "_note": "이 파일의 모든 값은 사용자가 직접 수정하는 설정입니다",
        "min_asset_threshold": old_data.get("min_asset_threshold", 400000),
        "max_positions": old_data.get("max_positions", 2)
    }
    
    # baseline 정보를 performance에서 가져와 budget에 추가
    performance_data = old_data.get("performance", {})
    budget_data["baseline_asset"] = performance_data.get("baseline_asset", 500000)
    budget_data["baseline_date"] = performance_data.get("baseline_date", "2026-01-27")
    budget_data["baseline_note"] = performance_data.get("baseline_note", "추가 입금/출금 시 baseline_asset을 수동으로 업데이트하세요")
    
    with open("signal_trading_budget.json", 'w', encoding='utf-8') as f:
        json.dump(budget_data, f, ensure_ascii=False, indent=2)
    
    print("✅ signal_trading_budget.json 생성 완료")
    
    # 3. performance 파일 생성 (baseline 제외)
    performance_data = old_data.get("performance", {})
    
    # baseline 관련 필드 제거 (이미 budget으로 이동)
    performance_data.pop('baseline_asset', None)
    performance_data.pop('baseline_date', None)
    performance_data.pop('baseline_note', None)
    
    # 루트 레벨의 performance.xxx 키들도 포함
    for key, value in old_data.items():
        if key.startswith("performance."):
            perf_key = key.replace("performance.", "")
            # baseline 관련은 제외
            if perf_key not in ['baseline_asset', 'baseline_date', 'baseline_note']:
                performance_data[perf_key] = value
    
    performance_data["_comment"] = "========== 봇 성과 추적 데이터 (자동 업데이트) =========="
    performance_data["_note"] = "이 파일의 모든 값은 봇이 자동으로 계산하고 업데이트합니다"
    
    with open("signal_trading_performance.json", 'w', encoding='utf-8') as f:
        json.dump(performance_data, f, ensure_ascii=False, indent=2)
    
    print("✅ signal_trading_performance.json 생성 완료")
    
    # 4. config 파일 생성 (performance와 budget 제거)
    config_data = {k: v for k, v in old_data.items() 
                   if k not in ["min_asset_threshold", "max_positions", "performance"] 
                   and not k.startswith("performance.")}
    
    config_data["_comment"] = "========== 매매 전략 설정 (사용자 수정 가능) =========="
    
    with open("signal_trading_config.json", 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
    
    print("✅ signal_trading_config.json 업데이트 완료")
    
    print("\n" + "=" * 60)
    print("🎉 마이그레이션 완료!")
    print("=" * 60)
    print("\n생성된 파일:")
    print("  1. signal_trading_config.json     (매매 전략)")
    print("  2. signal_trading_budget.json     (투자 예산)")
    print("  3. signal_trading_performance.json (성과 추적)")
    print(f"\n백업 파일: {backup_file}")
    print("\n다음 단계:")
    print("  → Kiwoom_SignalTradingBot.py의 ConfigManager 클래스 교체")
    print("  → 봇 재시작")

if __name__ == "__main__":
    migrate_config()