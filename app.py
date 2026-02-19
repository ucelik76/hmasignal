from flask import Flask, jsonify, render_template
import requests
import time
import os
import json
import threading
import asyncio
import websockets
from datetime import datetime

app = Flask(__name__)

SINYAL_LOG = os.path.expanduser("~/sinyal_gecmisi.json")
SEMBOLLER = ["BTC", "LINK", "AAVE", "ZEC", "HYPE"]

candle_data = {s: {"1": [], "3": []} for s in SEMBOLLER}
son_durum = {}
lock = threading.Lock()

def telegram_gonder(mesaj):
    pass  # Simdilik devre disi

def mavg(data, n):
    result = []
    for i in range(len(data)):
        if i < n - 1:
            result.append(sum(data[:i+1]) / (i+1))
        else:
            result.append(sum(data[i-n+1:i+1]) / n)
    return result

def crossover_var_mi(hma13, hma30):
    if len(hma13) < 2:
        return None
    if hma13[-2] < hma30[-2] and hma13[-1] > hma30[-1]:
        return "AL"
    if hma13[-2] > hma30[-2] and hma13[-1] < hma30[-1]:
        return "SAT"
    return None

def sinyal_kaydet(veri):
    try:
        log = []
        if os.path.exists(SINYAL_LOG):
            with open(SINYAL_LOG, 'r') as f:
                log = json.load(f)
        log.insert(0, {"zaman": veri["zaman"], "tarih": datetime.now().strftime('%d/%m/%Y'), "symbol": veri["symbol"], "sinyal": veri["sinyal"], "fiyat": veri["fiyat"]})
        log = log[:500]
        with open(SINYAL_LOG, 'w') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        print(f"Log hatasi: {e}")

def analiz_et(symbol):
    with lock:
        kapanis_1m = [c['c'] for c in candle_data[symbol]["1"]]
        kapanis_3m = [c['c'] for c in candle_data[symbol]["3"]]
    if len(kapanis_1m) < 30 or len(kapanis_3m) < 30:
        return None
    guncel_fiyat = kapanis_1m[-1]
    onceki_fiyat = kapanis_1m[-2]
    degisim = ((guncel_fiyat - onceki_fiyat) / onceki_fiyat) * 100
    hma13_1m = mavg(kapanis_1m, 13)
    hma30_1m = mavg(kapanis_1m, 30)
    hma13_3m = mavg(kapanis_3m, 13)
    hma30_3m = mavg(kapanis_3m, 30)
    trend_3m = "YUKARI" if hma13_3m[-1] > hma30_3m[-1] else "ASAGI"
    sinyal_1m = crossover_var_mi(hma13_1m, hma30_1m)
    nihai_sinyal = "BEKLE"
    sinyal_guc = "normal"
    if sinyal_1m == "AL" and trend_3m == "YUKARI":
        nihai_sinyal = "AL"
        sinyal_guc = "guclu"
    elif sinyal_1m == "SAT" and trend_3m == "ASAGI":
        nihai_sinyal = "SAT"
        sinyal_guc = "guclu"
    elif sinyal_1m == "AL":
        nihai_sinyal = "ZAYIF AL"
        sinyal_guc = "zayif"
    elif sinyal_1m == "SAT":
        nihai_sinyal = "ZAYIF SAT"
        sinyal_guc = "zayif"
    return {"symbol": symbol, "fiyat": round(guncel_fiyat, 4), "degisim": round(degisim, 4), "trend_3m": trend_3m, "hma13": round(hma13_1m[-1], 4), "hma30": round(hma30_1m[-1], 4), "sinyal": nihai_sinyal, "sinyal_guc": sinyal_guc, "zaman": datetime.now().strftime('%H:%M:%S'), "grafik": kapanis_1m[-20:], "hma13_grafik": hma13_1m[-20:], "hma30_grafik": hma30_1m[-20:]}

def sinyal_kontrol(veri):
    symbol = veri["symbol"]
    onceki = son_durum.get(symbol, {}).get("sinyal", "BEKLE")
    yeni = veri["sinyal"]
    if yeni != "BEKLE" and yeni != onceki:
        sinyal_kaydet(veri)
        telegram_gonder(f"Sinyal: {yeni} - {symbol} - ${veri['fiyat']}")
    son_durum[symbol] = veri

def get_initial_candles(symbol, interval, lookback=60):
    url = "https://api.hyperliquid.xyz/info"
    now = int(time.time() * 1000)
    interval_ms = {"1": 60000, "3": 180000}
    start = now - (lookback * interval_ms[interval])
    payload = {"type": "candleSnapshot", "req": {"coin": symbol, "interval": f"{interval}m", "startTime": start, "endTime": now}}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return [{"c": float(c['c']), "t": c['t']} for c in r.json()]
    except:
        return []

async def ws_dinle():
    print("Ilk veriler yukleniyor...")
    for symbol in SEMBOLLER:
        with lock:
            candle_data[symbol]["1"] = get_initial_candles(symbol, "1")
            candle_data[symbol]["3"] = get_initial_candles(symbol, "3")
        print(f"{symbol} hazir")
        time.sleep(0.3)

    uri = "wss://api.hyperliquid.xyz/ws"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                for symbol in SEMBOLLER:
                    await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "candle", "coin": symbol, "interval": "1m"}}))
                    await ws.send(json.dumps({"method": "subscribe", "subscription": {"type": "candle", "coin": symbol, "interval": "3m"}}))
                print("WebSocket baglandi!")
                async for message in ws:
                    try:
                        data = json.loads(message)
                        if data.get("channel") == "candle":
                            candle = data["data"]
                            symbol = candle["s"]
                            interval = candle["i"].replace("m", "")
                            if symbol not in SEMBOLLER:
                                continue
                            yeni = {"c": float(candle["c"]), "t": candle["t"]}
                            with lock:
                                lst = candle_data[symbol][interval]
                                if lst and lst[-1]["t"] == yeni["t"]:
                                    lst[-1] = yeni
                                else:
                                    lst.append(yeni)
                                    if len(lst) > 100:
                                        lst.pop(0)
                            veri = analiz_et(symbol)
                            if veri:
                                sinyal_kontrol(veri)
                    except Exception as e:
                        print(f"Mesaj hatasi: {e}")
        except Exception as e:
            print(f"WS hatasi: {e}, 5sn sonra tekrar...")
            await asyncio.sleep(5)

def ws_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_dinle())

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/data')
def api_data():
    sonuclar = []
    for s in SEMBOLLER:
        veri = analiz_et(s)
        if veri:
            sonuclar.append(veri)
    return jsonify({"data": sonuclar, "zaman": datetime.now().strftime('%d/%m/%Y %H:%M:%S')})

@app.route('/api/log')
def api_log():
    try:
        if os.path.exists(SINYAL_LOG):
            with open(SINYAL_LOG, 'r') as f:
                return jsonify(json.load(f))
    except:
        pass
    return jsonify([])

if __name__ == '__main__':
    t = threading.Thread(target=ws_thread, daemon=True)
    t.start()
    print("WebSocket thread baslatildi")
    time.sleep(5)
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5050)))
