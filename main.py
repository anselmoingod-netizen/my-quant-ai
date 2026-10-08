from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from pydantic import BaseModel
from typing import List

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TICKERS = {
    "LG에너지솔루션": "373220.KS",
    "삼성SDI": "006400.KS",
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "NAVER": "035420.KS",
    "카카오": "035720.KS",
    "POSCO홀딩스": "005490.KS"
}

class PortfolioItem(BaseModel):
    code: str
    buy_price: float
    quantity: int

def calculate_stock_score(df, market_bull):
    if df is None or df.empty or len(df) < 5:
        return None
        
    curr_price = int(df['Close'].iloc[-1])
    ma5 = df['Close'].rolling(5).mean().iloc[-1] if len(df) >= 5 else curr_price
    ma20 = df['Close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else ma5
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1] if len(df) >= 5 else 1
    curr_vol = df['Volume'].iloc[-1]
    
    score = 0
    if ma5 > ma20: score += 30
    if curr_vol > vol_ma5 * 1.2: score += 20
    if market_bull: score += 15
    if curr_price > ma5: score += 15
    
    signal = "BUY" if score >= 60 else "HOLD"
    target_price = int(curr_price * 1.08)
    stop_price = int(curr_price * 0.95)
    
    # 캔들스틱 차트용 OHLC 데이터 파싱
    ohlc_data = []
    for date, row in df.tail(30).iterrows():
        ohlc_data.append({
            "time": date.strftime("%Y-%m-%d"),
            "open": int(row['Open']),
            "high": int(row['High']),
            "low": int(row['Low']),
            "close": int(row['Close'])
        })

    return {
        "price": curr_price,
        "score": score,
        "signal": signal,
        "target_price": target_price,
        "stop_price": stop_price,
        "ohlc": ohlc_data
    }

@app.get("/")
def read_root():
    return {"status": "AI Quant Engine Running"}

@app.get("/api/signals")
def get_signals():
    results = []
    market_bull = True
    try:
        kospi = yf.Ticker("^KS11").history(period="1mo")
        if not kospi.empty and len(kospi) >= 5:
            ma20 = kospi['Close'].rolling(20).mean().iloc[-1]
            market_bull = bool(kospi['Close'].iloc[-1] > ma20)
    except Exception:
        pass

    for name, code in TICKERS.items():
        try:
            stock = yf.Ticker(code)
            df = stock.history(period="1mo")
            res = calculate_stock_score(df, market_bull)
            if res:
                res.update({"name": name, "code": code})
                results.append(res)
        except Exception:
            continue

    results.sort(key=lambda x: x['score'], reverse=True)
    return {"market_bull": market_bull, "signals": results}

@app.post("/api/analyze-portfolio")
def analyze_portfolio(items: List[PortfolioItem]):
    market_bull = True
    diagnostics = []
    total_eval = 0
    total_buy = 0

    for item in items:
        try:
            raw_code = item.code.strip().upper()
            code = raw_code if ('.KS' in raw_code or '.KQ' in raw_code) else f"{raw_code}.KS"
            
            stock = yf.Ticker(code)
            df = stock.history(period="1mo")
            res = calculate_stock_score(df, market_bull)
            
            if res:
                curr_price = res["price"]
                buy_price = item.buy_price
                qty = item.quantity
                
                eval_amount = curr_price * qty
                buy_amount = buy_price * qty
                profit_rate = round(((curr_price - buy_price) / buy_price) * 100, 2) if buy_price > 0 else 0
                
                total_eval += eval_amount
                total_buy += buy_amount

                if res["score"] >= 70:
                    action = "✨ 추가 매수(불타기) 고려"
                elif curr_price <= res["stop_price"]:
                    action = "🚨 손절가 하향 이탈"
                elif curr_price >= res["target_price"]:
                    action = "🎯 목표가 도달 (익절)"
                else:
                    action = "⏳ 보유 (HOLD)"

                diagnostics.append({
                    "code": code,
                    "buy_price": buy_price,
                    "curr_price": curr_price,
                    "quantity": qty,
                    "profit_rate": profit_rate,
                    "score": res["score"],
                    "action": action
                })
        except Exception:
            continue

    total_profit_rate = round(((total_eval - total_buy) / total_buy) * 100, 2) if total_buy > 0 else 0

    return {
        "total_buy": total_buy,
        "total_eval": total_eval,
        "total_profit_rate": total_profit_rate,
        "diagnostics": diagnostics
    }
