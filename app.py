from flask import Flask, jsonify, render_template
import requests
import time
import os
import json
from datetime import datetime

app = Flask(__name__)

SINYAL_LOG = os.path.expanduser("~/sinyal_gecmisi.json")
TELEGRAM_TOKEN = "8585545858:AAF92TfyCRuiADu6zN1cBfcNK3pY1jVFJ1s"
TELEGRAM_CHAT_ID = "565178732"

def telegram_gonder(mesaj):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mesaj, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

def mavg(data, n):
    result = []
    for i in range(len(data)):
        if i < n - 1:
            result.append(sum(data[:i+1]) / (i+1))
        else:
            result.append(sum(data[i-n+1:i+1]) / n)
    return result

def get_candles(symbol, interval, lookback=50):
    url = "https://api.hyperliquid.xyz/info"
    now = int(time.time() * 1000)
    interval_ms = {"1": 60000, "3": 180000}
    start = now - (lookback * interval_ms[interval])
    payload = {"type": "candleSnapshot", "req": {"coin": symbol, "interval": f"{interval}m", "startTime": start, "endTime": now}}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        print(f"Hata {symbol}: {e}")
        return []

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
        log.insert(0, {"zaman": veri["zaman"], "tarih": datetime.now().strftime('%d/%m/%Y'), "symbol": veri["symbol"], "sinyal": veri["sinyal"], "fiyat": veri["fiyat"], "hma13": veri["hma13"], "hma30": veri["hma30"]})
        log = log[:500]
        with open(SINYAL_LOG, 'w') as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        print(f"Log hatasi: {e}")

def analiz_et(symbol):
    candles_3m = get_candles(symbol, "3", lookback=60)
    candles_1m = get_candles(symbol, "1", lookback=60)
    if not candles_3m or not candles_1m:
        return None
    kapanis_3m = [float(c['c']) for c in candles_3m]
    kapanis_1m = [float(c['c']) for c in candles_1m]
    if len(kapanis_3m) < 30 or len(kapanis_1m) < 30:
        return None
    guncel_fiyat = kapanis_1m[-1]
    onceki_fiyat = kapanis_1m[-2]
    degisim = ((guncel_fiyat - onceki_fiyat) / onceki_fiyat) * 100
    hma13_3m = mavg(kapanis_3m, 13)
    hma30_3m = mavg(kapanis_3m, 30)
    hma13_1m = mavg(kapanis_1m, 13)
    hma30_1m = mavg(kapanis_1m, 30)
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

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/data')
def api_data():
    semboller = ["BTC", "LINK", "AAVE", "ZEC", "HYPE"]
    sonuclar = []
    for s in semboller:
        veri = analiz_et(s)
        if veri:
            sonuclar.append(veri)
            if veri["sinyal"] != "BEKLE":
                sinyal_kaydet(veri)
                if veri["sinyal"] == "AL":
                    os.system(f'say "{s} AL sinyali"')
                    telegram_gonder(f"[AL SINYALI]\n\nSembol: {s}\nFiyat: ${veri['fiyat']}\nHMA13: {veri['hma13']}\nHMA30: {veri['hma30']}\nTrend: {veri['trend_3m']}")
                elif veri["sinyal"] == "SAT":
                    os.system(f'say "{s} SAT sinyali"')
                    telegram_gonder(f"[SAT SINYALI]\n\nSembol: {s}\nFiyat: ${veri['fiyat']}\nHMA13: {veri['hma13']}\nHMA30: {veri['hma30']}\nTrend: {veri['trend_3m']}")
                elif "ZAYIF" in veri["sinyal"]:
                    telegram_gonder(f"[ZAYIF SINYAL]\n\nSembol: {s}\nSinyal: {veri['sinyal']}\nFiyat: ${veri['fiyat']}")
        time.sleep(0.3)
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
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5050)))
