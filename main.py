from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import numpy as np

app = FastAPI(title="AI Quant Hub Engine")

# 프론트엔드 웹사이트에서 데이터를 요청할 수 있도록 허용 (CORS 설정)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "AI Quant Engine Running"}

@app.get("/api/signals")
def get_ai_signals():
    # 1. KOSPI 시장 지수 트렌드 확인
    kospi = yf.download("^KS11", period="60d", progress=False)
    if isinstance(kospi.columns, pd.MultiIndex): 
        kospi.columns = kospi.columns.get_level_values(0)
    
    kospi['MA20'] = kospi['Close'].ewm(span=20, adjust=False).mean()
    is_market_bull = bool(kospi['Close'].iloc[-1] > kospi['MA20'].iloc[-1])

    # 2. 스캔 대상 핵심 KOSPI 종목
    tickers = {
        "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", 
        "LG에너지솔루션": "373220.KS", "삼성SDI": "006400.KS", "현대차": "005380.KS"
    }
    
    results = []
    
    for name, code in tickers.items():
        try:
            df = yf.download(code, period="100d", progress=False)
            if df.empty or len(df) < 60: continue
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.get_level_values(0)

            # 지표 산출 (EMA, MA, 볼린저밴드, 거래량, ATR)
            df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            df['BB_Mid'] = df['Close'].rolling(window=20).mean()
            df['BB_Std'] = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * 2)
            df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
            
            df['TR'] = np.maximum(df['High'] - df['Low'], np.maximum(abs(df['High'] - df['Close'].shift(1)), abs(df['Low'] - df['Close'].shift(1))))
            df['ATR'] = df['TR'].rolling(window=14).mean()
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 스코어링 (100점 만점)
            score = 0
            if last['Close'] > last['EMA20'] > last['MA60']: score += 30  # 추세 정배열
            if last['Close'] > prev['BB_Upper']: score += 25               # 변동성 상단 돌파
            if last['Volume'] > last['Vol_MA20'] * 1.5: score += 20        # 거래량 수수료 폭발
            if is_market_bull: score += 15                                 # 시장 상승장
            score += 10                                                    # 리스크 필터 합격

            close_price = int(last['Close'])
            atr_val = last['ATR'] if not np.isnan(last['ATR']) else close_price * 0.025
            
            target_price = int(close_price * 1.08)
            stop_price = int(close_price - (atr_val * 1.5))
            
            results.append({
                "name": name,
                "code": code,
                "price": close_price,
                "score": score,
                "signal": "BUY" if score >= 80 else "HOLD",
                "target_price": target_price,
                "stop_price": stop_price
            })
        except Exception:
            continue
            
    # 스코어 높은 순 정렬
    results = sorted(results, key=lambda x: x['score'], reverse=True)
    return {"market_bull": is_market_bull, "signals": results}