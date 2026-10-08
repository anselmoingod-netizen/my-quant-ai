import os
import json
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Render 환경변수에서 키 자동 로드
NAMU_APP_KEY = os.getenv("NAMU_APP_KEY", "")
NAMU_APP_SECRET = os.getenv("NAMU_APP_SECRET", "")
NAMU_BASE_URL = "https://openapi.nhqv.com"  # 나무 증권 정식 API 서버

TICKERS = {
    "LG에너지솔루션": "373220",
    "삼성SDI": "006400",
    "삼성전자": "005930",
    "SK하이닉스": "000660",
    "현대차": "005380",
    "NAVER": "035420",
    "카카오": "035720",
    "POSCO홀딩스": "005490"
}

class PortfolioItem(BaseModel):
    code: str
    buy_price: float
    quantity: int

# 1. 나무증권 접근 토큰(AccessToken) 발급
def get_namu_token():
    if not NAMU_APP_KEY or not NAMU_APP_SECRET:
        return None
    url = f"{NAMU_BASE_URL}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": NAMU_APP_KEY,
        "appsecret": NAMU_APP_SECRET
    }
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body), timeout=5)
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception as e:
        print(f"Token generation error: {e}")
    return None

# 2. 나무증권 실시간 현재가/시세 조회
def fetch_namu_stock(code: str, token: str):
    clean_code = code.replace(".KS", "").replace(".KQ", "").strip()
    url = f"{NAMU_BASE_URL}/uapi/domestic-stock/v1/quoting/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": NAMU_APP_KEY,
        "appsecret": NAMU_APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": clean_code
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=3)
        if res.status_code == 200:
            data = res.json().get("output", {})
            curr_price = int(data.get("stck_prpr", 0))
            open_price = int(data.get("stck_oprc", curr_price))
            high_price = int(data.get("stck_hgpr", curr_price))
            low_price = int(data.get("stck_lwpr", curr_price))
            return {
                "price": curr_price,
                "open": open_price,
                "high": high_price,
                "low": low_price
            }
    except Exception as e:
        print(f"Error fetching {code} from Namu API: {e}")
    return None

@app.get("/")
def read_root():
    return {"status": "Namu Open API Connected & Engine Running"}

@app.get("/api/signals")
def get_signals():
    token = get_namu_token()
    results = []

    for name, code in TICKERS.items():
        stock_info = fetch_namu_stock(code, token) if token else None
        
        if stock_info and stock_info["price"] > 0:
            curr_price = stock_info["price"]
            score = 85 if curr_price >= stock_info["open"] else 55
            signal = "BUY" if score >= 80 else "HOLD"
            
            results.append({
                "name": name,
                "code": f"{code}.KS",
                "price": curr_price,
                "score": score,
                "signal": signal,
                "target_price": int(curr_price * 1.08),
                "stop_price": int(curr_price * 0.95),
                "ohlc": [
                    {"time": "2026-10-06", "open": stock_info["open"], "high": stock_info["high"], "low": stock_info["low"], "close": curr_price}
                ]
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    return {"market_bull": True, "signals": results}

@app.post("/api/analyze-portfolio")
def analyze_portfolio(items: List[PortfolioItem]):
    token = get_namu_token()
    diagnostics = []
    total_eval = 0
    total_buy = 0

    for item in items:
        stock_info = fetch_namu_stock(item.code, token) if token else None
        if stock_info and stock_info["price"] > 0:
            curr_price = stock_info["price"]
            buy_price = item.buy_price
            qty = item.quantity
            
            eval_amount = curr_price * qty
            buy_amount = buy_price * qty
            profit_rate = round(((curr_price - buy_price) / buy_price) * 100, 2) if buy_price > 0 else 0
            
            total_eval += eval_amount
            total_buy += buy_amount

            diagnostics.append({
                "code": item.code,
                "buy_price": buy_price,
                "curr_price": curr_price,
                "quantity": qty,
                "profit_rate": profit_rate,
                "score": 80 if profit_rate >= 0 else 40,
                "action": "✨ 추가 매수 고려" if profit_rate >= 5 else ("🚨 손절 관리" if profit_rate <= -5 else "⏳ 보유 (HOLD)")
            })

    total_profit_rate = round(((total_eval - total_buy) / total_buy) * 100, 2) if total_buy > 0 else 0

    return {
        "total_buy": total_buy,
        "total_eval": total_eval,
        "total_profit_rate": total_profit_rate,
        "diagnostics": diagnostics
    }
