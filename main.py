from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd

app = FastAPI()

# CORS 설정 (프론트엔드 Vercel 연동 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 대상 종목 리스트 (KOSPI 대표주)
TICKERS = {
    "LG에너지솔루션": "373220.KS",
    "삼성SDI": "006400.KS",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS"
}

@app.get("/")
def read_root():
    return {"status": "AI Quant Engine Running"}

@app.get("/api/signals")
def get_signals():
    results = []
    
    # 1. KOSPI 지수 추세 체크 (시장 건강도)
    market_bull = True
    try:
        kospi = yf.Ticker("^KS11").history(period="1mo")
        if not kospi.empty and len(kospi) >= 20:
            ma20 = kospi['Close'].rolling(20).mean().iloc[-1]
            market_bull = bool(kospi['Close'].iloc[-1] > ma20)
    except Exception as e:
        print(f"Kospi fetch error: {e}")

    # 2. 개별 종목 다층 알고리즘 스캔
    for name, code in TICKERS.items():
        try:
            stock = yf.Ticker(code)
            df = stock.history(period="3mo")
            
            if df.empty or len(df) < 20:
                continue
                
            curr_price = int(df['Close'].iloc[-1])
            
            # 지표 계산
            ma5 = df['Close'].rolling(5).mean().iloc[-1]
            ma20 = df['Close'].rolling(20).mean().iloc[-1]
            vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
            curr_vol = df['Volume'].iloc[-1]
            
            # 볼린저 밴드
            std20 = df['Close'].rolling(20).std().iloc[-1]
            upper_band = ma20 + (std20 * 2)
            
            # 점수 계산 (5팩터 모델)
            score = 0
            if ma5 > ma20: score += 30      # 추세 정배열
            if curr_price > upper_band: score += 25  # 변동성 상단 돌파
            if curr_vol > vol_ma5 * 1.5: score += 20 # 거래량 수수급 유입
            if market_bull: score += 15     # 시장 상승장 가산점
            if curr_price > ma5: score += 10 # 단기 이평선 지지
            
            signal = "BUY" if score >= 80 else "HOLD"
            
            # 타점 산출
            target_price = int(curr_price * 1.08) # 목표가 +8%
            stop_price = int(curr_price * 0.95)   # 손절가 -5%
            
            results.append({
                "name": name,
                "code": code,
                "price": curr_price,
                "score": score,
                "signal": signal,
                "target_price": target_price,
                "stop_price": stop_price
            })
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            continue

    # 점수 기준 내림차순 정렬
    results.sort(key=lambda x: x['score'], reverse=True)
    
    return {
        "market_bull": market_bull,
        "signals": results
    }
