import os
import time
import threading
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pocketoptionapi import PocketOption

app = FastAPI(title="МАРК 1")

SSID = os.getenv("PO_SSID", "").strip()
ASSET = os.getenv("PO_ASSET", "EURUSD_otc")
PERIOD = int(os.getenv("PO_PERIOD", "60"))

state = {
    "connected": False,
    "asset": ASSET,
    "period": PERIOD,
    "message": "МАРК 1 очікує підключення",
    "signal": "НЕ ВХОДИТИ",
}

client = None


def ema(values, span):
    alpha = 2 / (span + 1)
    result = [values[0]]

    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])

    return result[-1]


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
        state["message"] = "SSID не задано — режим очікування"
        return

    try:
        client = PocketOption(SSID)
        ok, error = client.connect()

        if not ok:
            state["message"] = f"Помилка підключення: {error}"
            return

        while not (client.check_connect() and client.is_time_synced()):
            time.sleep(0.5)

        state["connected"] = True
        state["message"] = "МАРК 1 підключений до DEMO"

        client.subscribe(ASSET, period=PERIOD)

        while True:
            time.sleep(2)

    except Exception as error:
        state["connected"] = False
        state["message"] = f"З'єднання зупинено: {type(error).__name__}"


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
</div>

<div class="card">
<div class="signal" id="signal">
НЕ ВХОДИТИ
</div>
</div>

<div class="card">
<p>МАРК 1 працює в режимі аналізу.</p>
<p>Автоматичне відкриття угод вимкнено.</p>
</div>

<script>

async function update() {

    try {

        const data =
            await fetch('/api/state')
            .then(response => response.json());

        document.getElementById('asset').textContent =
            data.asset;

        document.getElementById('status').textContent =
            data.message;

        document.getElementById('signal').textContent =
            data.signal;

    } catch (error) {

        document.getElementById('status').textContent =
            'Немає зв’язку';

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
