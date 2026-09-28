#!/usr/bin/env python3
"""Probe: WS auth, session skapande, wake.start, prompt.submit-deltas.

Tar URL som argument: ws://127.0.0.1:9215/api/ws?token=... eller
wss://pocket.kranium.me/api/ws?token=...
"""
import asyncio, json, sys, pathlib

TOKEN_PATH = pathlib.Path(__file__).parent.parent / "server" / "session-token.txt"
DEFAULT_LOCAL = "ws://127.0.0.1:9215/api/ws?token="
DEFAULT_TLS = "wss://pocket.kranium.me/api/ws?token="


def url_from_args():
    token = TOKEN_PATH.read_text().strip()
    if len(sys.argv) > 1:
        return sys.argv[1] + token
    return DEFAULT_LOCAL + token


class Rpc:
    def __init__(self, ws):
        self.ws, self.n = ws, 0

    async def call(self, method, **params):
        self.n += 1
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self.n,
                                       "method": method, "params": params}))
        while True:
            frame = json.loads(await self.ws.recv())
            if frame.get("id") == self.n:
                return frame
            if frame.get("method"):
                print("EVENT:", frame["method"], json.dumps(frame.get("params", {}))[:200])


async def main():
    import websockets
    url = url_from_args()
    print("connecting:", url.split("token=")[0] + "token=<redacted>")
    async with websockets.connect(url, max_size=10**7) as ws:
        rpc = Rpc(ws)
        print("caps:", json.dumps(await rpc.call("client.capabilities", server_requests=False))[:300])
        lst = await rpc.call("session.list", limit=1)
        print("session.list:", json.dumps(lst)[:300])

        created = await rpc.call("session.create", title="pocket-alfred")
        print("session.create:", json.dumps(created)[:300])
        res = created.get("result") if isinstance(created.get("result"), dict) else created
        sid = res.get("session_id") or res.get("sid") or res.get("id")
        print("session_id:", sid)
        if not sid:
            print("!! session.create gav inget session_id — dokumentera fallback via session.list")
            return

        ws_start = await rpc.call("wake.start", surface="gui",
                                  client_capture=True, session_id=sid)
        print("wake.start:", json.dumps(ws_start)[:400])
        try:
            ws_status = await rpc.call("wake.status", surface="gui")
            print("wake.status.listening:", (ws_status.get("result") or {}).get("listening"))
        except Exception as e:
            print("wake.status fail:", e)

        sub = await rpc.call("prompt.submit", session_id=sid, text="Säg hej på svenska, kort.",
                             surface="voice-live")
        print("prompt.submit:", json.dumps(sub)[:200])
        # Samla message.* events i 20 s
        try:
            while True:
                frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
                if frame.get("method", "").startswith(("message.", "error")):
                    print("STREAM:", frame["method"], json.dumps(frame.get("params", {}))[:150])
        except asyncio.TimeoutError:
            pass
        print("DONE")


asyncio.run(main())
