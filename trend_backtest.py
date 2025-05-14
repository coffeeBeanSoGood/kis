#!/usr/bin/env python3
"""
기존 trend_trading.py의 백테스트 기능을 주기적으로 실행하기 위한 간단한 스크립트
특정 기간 백테스트 지원
"""

import os
import sys
import json
import time
import datetime
import subprocess
import logging
from logging.handlers import RotatingFileHandler

# 로깅 설정
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

logger = logging.getLogger('BacktestScheduler')
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'backtest_scheduler.log'),
    maxBytes=5*1024*1024,  # 5MB
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 설정 파일 경로
CONFIG_PATH = "trend_trader_config.json"

def load_config():
    """설정 파일 로드"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.exception(f"설정 파일 로드 중 오류: {str(e)}")
        return {}

def save_config(config):
    """설정 파일 저장"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info("설정 파일 저장 완료")
    except Exception as e:
        logger.exception(f"설정 파일 저장 중 오류: {str(e)}")


# trend_backtest.py 파일에 다음 로직을 추가
def run_backtest(start_date=None, end_date=None, days=30, is_adaptive=True):
    """백테스트 실행
    
    Args:
        start_date: 시작일자 (YYYYMMDD 형식, 없으면 days 기준으로 계산)
        end_date: 종료일자 (YYYYMMDD 형식, 없으면 현재일)
        days: 백테스트 기간 (일수, start_date가 없을 때만 사용)
        is_adaptive: 적응형 백테스트 여부
    """
    # 기간 설정 (start_date가 없으면 days 기준으로 계산)
    if not start_date:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
    
    # 종료일 설정 (end_date가 없으면 현재일)
    if not end_date:
        end_date = datetime.datetime.now().strftime("%Y%m%d")
    
    logger.info(f"백테스트 실행: {start_date} ~ {end_date} (적응형: {is_adaptive})")
    
    try:
        # 백테스트 명령어 구성
        cmd = ["python", "trend_trading.py", "backtest", start_date, end_date]
        
        # 적응형 백테스트 옵션 추가
        if is_adaptive:
            cmd.append("--adaptive")
            
        logger.info(f"실행 명령: {' '.join(cmd)}")
        
        # 실시간으로 출력 표시하면서 로그에도 기록
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # stderr를 stdout으로 리디렉션
            text=True,
            bufsize=1  # 라인 버퍼링
        )

        # 실시간으로 출력 읽기
        all_output = []
        for line in process.stdout:
            line = line.strip()
            all_output.append(line)  # 전체 출력 저장
            print(line)  # 콘솔에 출력
            logger.info(f"[백테스트] {line}")  # 로그에도 기록
        
        # 프로세스 완료 대기
        process.wait()
        
        # 전체 출력을 stdout 형태로 결합 (기존 코드와의 호환성)
        stdout = "\n".join(all_output)
        stderr = ""  # stderr는 stdout으로 리디렉션됨
        
        if process.returncode == 0:
            logger.info("백테스트 실행 성공")
            logger.debug(f"출력: {stdout}")
            
            # === 여기서부터 추가된 로직 시작 ===
            # 최신 백테스트 결과 파일 찾기
            import glob
            import os
            
            # 백테스트 결과 파일 패턴
            result_pattern = "backtest_result_*.json"
            
            logger.info("최신 백테스트 결과 파일 검색 중...")
            result_files = glob.glob(result_pattern)
            
            if not result_files:
                logger.error(f"백테스트 결과 파일({result_pattern})을 찾을 수 없습니다.")
                return False
            
            # 파일 수정 시간을 기준으로 정렬 (최신 파일이 첫 번째)
            result_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            latest_file = result_files[0]
            
            logger.info(f"최신 백테스트 결과 파일 찾음: {latest_file}")
            
            # 백테스트 결과 분석 명령 실행
            logger.info(f"백테스트 결과 분석 시작: {latest_file}")
            analyze_cmd = ["python", "trend_trading.py", "analyze-backtest", latest_file]
            
            # 분석 프로세스도 실시간 출력 표시
            analyze_process = subprocess.Popen(
                analyze_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # 실시간으로 분석 출력 읽기
            analyze_output = []
            for line in analyze_process.stdout:
                line = line.strip()
                analyze_output.append(line)  # 출력 저장
                print(line)  # 콘솔에 출력
                logger.info(f"[분석] {line}")  # 로그에도 기록
            
            # 프로세스 완료 대기
            analyze_process.wait()
            
            # 분석 출력을 결합
            analyze_stdout = "\n".join(analyze_output)
            analyze_stderr = ""
            
            if analyze_process.returncode == 0:
                logger.info(f"백테스트 결과 분석 성공")
                logger.debug(f"분석 출력: {analyze_stdout}")
            else:
                logger.error(f"백테스트 결과 분석 실패 (코드: {analyze_process.returncode})")
                logger.error(f"분석 오류: {analyze_stderr}")
                return False
            # === 추가된 로직 끝 ===
            
        else:
            logger.error(f"백테스트 실행 실패 (코드: {process.returncode})")
            logger.error(f"오류: {stderr}")
            return False
        
        # 최적 전략 적용
        logger.info("최적 전략 적용 시작")
        cmd = ["python", "trend_trading.py", "apply-optimal"]
        
        # 최적화 프로세스도 실시간 출력 표시
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # 실시간으로 최적화 출력 읽기
        optimize_output = []
        for line in process.stdout:
            line = line.strip()
            optimize_output.append(line)  # 출력 저장
            print(line)  # 콘솔에 출력
            logger.info(f"[최적화] {line}")  # 로그에도 기록
        
        # 프로세스 완료 대기
        process.wait()
        
        # 최적화 출력을 결합
        stdout = "\n".join(optimize_output)
        stderr = ""
        
        if process.returncode == 0:
            logger.info("최적 전략 적용 성공")
            logger.debug(f"출력: {stdout}")
        else:
            logger.error(f"최적 전략 적용 실패 (코드: {process.returncode})")
            logger.error(f"오류: {stderr}")
            return False
        
        # 설정 파일 업데이트 (백테스트 날짜 기록)
        config = load_config()
        config["last_backtest_date"] = datetime.datetime.now().strftime("%Y-%m-%d")
        save_config(config)
        
        return True
    except Exception as e:
        logger.exception(f"백테스트 프로세스 실행 중 오류: {str(e)}")
        return False
    

def check_and_run_backtest():
    """백테스트 실행 필요성 확인 및 실행"""
    try:
        # 설정 파일 로드
        config = load_config()
        last_backtest_date_str = config.get("last_backtest_date", "")
        
        # 마지막 백테스트 날짜 확인
        if not last_backtest_date_str:
            logger.info("이전 백테스트 기록 없음, 백테스트 실행")
            return run_backtest()
        
        try:
            last_backtest_date = datetime.datetime.strptime(last_backtest_date_str, "%Y-%m-%d").date()
            today = datetime.datetime.now().date()
            days_since_last_backtest = (today - last_backtest_date).days
            
            # 요일 확인 (0=월요일, 6=일요일)
            weekday = today.weekday()
            
            # 백테스트 실행 조건
            if days_since_last_backtest >= 7:
                logger.info(f"마지막 백테스트 후 {days_since_last_backtest}일 경과, 백테스트 실행")
                return run_backtest()
            
            # 월요일에 실행 (주간 업데이트)
            if weekday == 0 and days_since_last_backtest >= 3:
                logger.info("월요일 주간 백테스트 실행")
                return run_backtest()
            
            logger.info(f"백테스트 필요 없음. 마지막 실행: {last_backtest_date_str}, 경과일: {days_since_last_backtest}")
            return False
            
        except ValueError:
            logger.warning(f"날짜 형식 오류: {last_backtest_date_str}")
            return run_backtest()
            
    except Exception as e:
        logger.exception(f"백테스트 체크 중 오류: {str(e)}")
        return False

def main():
    """메인 함수"""
    # 명령행 인자 처리
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "force":
            # 강제 백테스트 실행 (최근 X일)
            if len(sys.argv) > 2 and sys.argv[2].isdigit():
                days = int(sys.argv[2])
                logger.info(f"강제 백테스트 실행 (최근 {days}일)")
                run_backtest(days=days)
            elif len(sys.argv) > 2:
                # 시작일 지정
                start_date = sys.argv[2]
                end_date = sys.argv[3] if len(sys.argv) > 3 else None
                logger.info(f"강제 백테스트 실행 (기간: {start_date} ~ {end_date or '현재'})")
                run_backtest(start_date=start_date, end_date=end_date)
            else:
                # 기본 30일
                logger.info("강제 백테스트 실행 (최근 30일)")
                run_backtest()
                
        elif command == "check":
            logger.info("백테스트 필요성 체크")
            check_and_run_backtest()
            
        elif command == "period":
            # 특정 기간 지정 백테스트
            if len(sys.argv) < 3:
                logger.error("시작일을 지정해야 합니다")
                print("사용법: python run_backtest.py period <시작일> [종료일] [--standard]")
                return
                
            start_date = sys.argv[2]
            end_date = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else None
            is_adaptive = "--standard" not in sys.argv
            
            logger.info(f"특정 기간 백테스트 실행: {start_date} ~ {end_date or '현재'} (적응형: {is_adaptive})")
            run_backtest(start_date=start_date, end_date=end_date, is_adaptive=is_adaptive)
            
        else:
            logger.error(f"알 수 없는 명령: {command}")
            print("사용법:")
            print("  python run_backtest.py - 백테스트 필요성 확인 후 실행")
            print("  python run_backtest.py force [일수/시작일] [종료일] - 강제 백테스트 실행")
            print("  python run_backtest.py check - 백테스트 필요성 확인 후 필요시 실행")
            print("  python run_backtest.py period <시작일> [종료일] [--standard] - 특정 기간 백테스트")
    else:
        # 기본 동작: 필요성 확인 후 실행
        check_and_run_backtest()

if __name__ == "__main__":
    main()