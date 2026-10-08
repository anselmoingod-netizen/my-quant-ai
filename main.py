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
    if df.empty or len(df) < 20:
        return None
        
    curr_price = int(df['Close'].iloc[-1])
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    vol_ma5 = df['Volume'].rolling(5).mean().iloc[-1]
    curr_vol = df['Volume'].iloc[-1]
    std20 = df['Close'].rolling(20).std().iloc[-1]
    upper_band = ma20 + (std20 * 2)
    
    score = 0
    if ma5 > ma20: score += 30
    if curr_price > upper_band: score += 25
    if curr_vol > vol_ma5 * 1.5: score += 20
    if market_bull: score += 15
    if curr_price > ma5: score += 10
    
    signal = "BUY" if score >= 80 else "HOLD"
    target_price = int(curr_price * 1.08)
    stop_price = int(curr_price * 0.95)
    
    return {
        "price": curr_price,
        "score": score,
        "signal": signal,
        "target_price": target_price,
        "stop_price": stop_price
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
        if not kospi.empty and len(kospi) >= 20:
            ma20 = kospi['Close'].rolling(20).mean().iloc[-1]
            market_bull = bool(kospi['Close'].iloc[-1] > ma20)
    except Exception as e:
        print(f"Kospi fetch error: {e}")

    for name, code in TICKERS.items():
        try:
            stock = yf.Ticker(code)
            df = stock.history(period="3mo")
            res = calculate_stock_score(df, market_bull)
            if res:
                res.update({"name": name, "code": code})
                results.append(res)
        except Exception as e:
            print(f"Error fetching {name}: {e}")
            continue

    results.sort(key=lambda x: x['score'], reverse=True)
    return {"market_bull": market_bull, "signals": results}

@app.post("/api/analyze-portfolio")
def analyze_portfolio(items: List[PortfolioItem]):
    market_bull = True
    try:
        kospi = yf.Ticker("^KS11").history(period="1mo")
        if not kospi.empty and len(kospi) >= 20:
            ma20 = kospi['Close'].rolling(20).mean().iloc[-1]
            market_bull = bool(kospi['Close'].iloc[-1] > ma20)
    except Exception as e:
        pass

    diagnostics = []
    total_eval = 0
    total_buy = 0

    for item in items:
        try:
            code = item.code if item.code.endswith('.KS') or item.code.endswith('.KQ') else f"{item.code}.KS"
            stock = yf.Ticker(code)
            df = stock.history(period="3mo")
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

                # 진단 액션 매핑
                if res["score"] >= 80:
                    action = "✨ 추가 매수(불타기) 적기"
                elif curr_price <= res["stop_price"]:
                    action = "🚨 손절가 하향 이탈 (리스크 관리 필요)"
                elif curr_price >= res["target_price"]:
                    action = "🎯 목표가 도달 (수익 실현 고려)"
                else:
                    action = "⏳ 관망 및 보유 (HOLD)"

                diagnostics.append({
                    "code": code,
                    "buy_price": buy_price,
                    "curr_price": curr_price,
                    "quantity": qty,
                    "profit_rate": profit_rate,
                    "score": res["score"],
                    "action": action
                })
        except Exception as e:
            print(f"Portfolio error ({item.code}): {e}")

    total_profit_rate = round(((total_eval - total_buy) / total_buy) * 100, 2) if total_buy > 0 else 0

    return {
        "total_buy": total_buy,
        "total_eval": total_eval,
        "total_profit_rate": total_profit_rate,
        "diagnostics": diagnostics
    }
