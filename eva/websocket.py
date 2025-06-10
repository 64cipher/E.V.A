import json
from flask_sock import Sock

sock = Sock()


def chat_ws(ws):
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            ws.send(json.dumps({"echo": data}))
    except Exception:
        pass
