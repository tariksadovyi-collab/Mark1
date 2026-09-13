import os
import time
import threading
import logging

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pocketoptionapi import PocketOption

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="МАРК 1")

SSID = os.getenv("PO_SSID", "").strip()
ASSET = os.getenv("PO_ASSET", "EURUSD_otc")
PERIOD = int(os.getenv("PO_PERIOD", "60"))

state = {
    "connected": False,
    "asset": ASSET,
    "period": PERIOD,
    "message": "МАРК 1 запускається...",
    "signal": "НЕ ВХОДИТИ",
    "candles": 0,
}

client = None


def ema(values, span):
    alpha = 2 / (span + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None

    gains = []
    losses = []

    for a, b in zip(values[:-1], values[1:]):
        change = b - a
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    return 100 - (100 / (1 + avg_gain / avg_loss))


def make_signal(closes):
    if len(closes) < 30:
        return "НЕ ВХОДИТИ"

    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    r = rsi(closes, 14)

    if r is None:
        return "НЕ ВХОДИТИ"

    if e9 > e21 and r >= 55:
        return "CALL ↑"

    if e9 < e21 and r <= 45:
        return "PUT ↓"

    return "НЕ ВХОДИТИ"


def worker():
    global client

    if not SSID:
        state["message"] = "❌ PO_SSID не задано"
        logging.error("PO_SSID is empty")
        return

    try:
        logging.info("МАРК 1: підключення до Pocket Option DEMO...")

        client = PocketOption(SSID)
        ok, error = client.connect()

        if not ok:
            state["message"] = f"❌ Помилка: {error}"
            logging.error("Connection failed: %s", error)
            return

        deadline = time.time() + 30

        while time.time() < deadline:
            if client.check_connect() and client.is_time_synced():
                break
            time.sleep(0.5)

        if not (client.check_connect() and client.is_time_synced()):
            state["message"] = "❌ Не завершилась синхронізація"
            return

        state["connected"] = True
        state["message"] = "✅ Pocket Option DEMO підключено"

        logging.info("Pocket Option DEMO connected")

        if not client.subscribe(ASSET, period=PERIOD):
            state["message"] = "⚠️ DEMO підключено, але актив не підписаний"
            return

        logging.info("Subscribed to %s", ASSET)

        time.sleep(2)

        raw = client.get_historical_candles(
            ASSET,
            PERIOD,
            offset=9000,
            count_request=1
        )

        if raw:
            df = client.process_candles_data(raw, PERIOD)

            if df is not None and not df.empty and "close" in df.columns:
                closes = df["close"].astype(float).tolist()

                state["candles"] = len(closes)
                state["signal"] = make_signal(closes)
                state["message"] = "✅ DEMO підключено + свічки отримуються"

                logging.info(
                    "TEST OK: candles=%s signal=%s",
                    len(closes),
                    state["signal"]
                )
            else:
                state["message"] = "⚠️ Свічки отримані, але не обробились"
        else:
            state["message"] = "⚠️ Свічки не отримані"

        while True:
            time.sleep(5)

    except Exception as error:
        state["connected"] = False
        state["message"] = f"❌ Помилка: {type(error).__name__}"
        logging.exception("MARK 1 stopped")


@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()


@app.get("/api/state")
def api_state():
    return JSONResponse(state)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html lang="uk">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>МАРК 1</title>
<style>
body {
    font-family: Arial, sans-serif;
    background:#0b1020;
    color:white;
    padding:20px;
}
.card {
    background:#151b2d;
    border-radius:18px;
    padding:18px;
    margin:15px 0;
}
.signal {
    text-align:center;
    font-size:32px;
    padding:30px;
    background:#20283c;
    border-radius:15px;
}
</style>
</head>

<body>

<h1>🤖 МАРК 1</h1>

<div class="card">
<p>Режим: <b>DEMO</b></p>
<p>Актив: <b id="asset">—</b></p>
<p>Статус: <b id="status">—</b></p>
<p>Свічки: <b id="candles">—</b></p>
</div>

<div class="card">
<div class="signal" id="signal">НЕ ВХОДИТИ</div>
</div>

<div class="card">
<p>Сума майбутньої угоди: <b>$10</b></p>
<p>Експірація: <b>60 секунд</b></p>
<p>Автоторгівля: <b>ВИМКНЕНО</b></p>
</div>

<script>
async function update() {
    try {
        const data = await fetch('/api/state').then(r => r.json());

        document.getElementById('asset').textContent = data.asset;
        document.getElementById('status').textContent = data.message;
        document.getElementById('candles').textContent = data.candles;
        document.getElementById('signal').textContent = data.signal;

    } catch (e) {
        document.getElementById('status').textContent = 'Немає зв’язку';
    }
}

setInterval(update, 1500);
update();
</script>

</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000"))
    )
