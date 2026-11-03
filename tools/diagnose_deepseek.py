"""Diagnostica DeepSeek: rete, chiave e endpoint.
Non stampa mai la chiave: solo lunghezza, caratteri sospetti e l'esito
delle richieste. Eseguire con la variabile DEEPSEEK_API_KEY impostata:
    .\\.venv\\Scripts\\python.exe tools\\diagnose_deepseek.py
"""
from __future__ import annotations
import os
import socket
import requests
URLS = (
    "https://api.deepseek.com/chat/completions",
    "https://api.deepseek.com/v1/chat/completions",
)
PAYLOAD = {
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "ok"}],
    "stream": False,
}
FAKE_KEY = "invalid-key-for-diagnostic"
def describe_key(key: str) -> None:
    if not key:
        print("key: assente")
        return
    control = any(
        ord(character) < 32 or ord(character) > 126
        for character in key
    )
    print(
        "key: "
        f"len={len(key)} "
        f"clean={key == key.strip()} "
        f"spaces={key.count(' ')} "
        f"quotes={key[:1] in chr(34) + chr(39) or key[-1:] in chr(34) + chr(39)} "
        f"non_ascii={control} "
        f"bearer_prefix={key.lower().startswith('bearer ')}"
    )
    if len(key) < 10:
        print(
            "  ATTENZIONE: chiave troppo corta; "
            "il paste nel prompt potrebbe non "
            "essere riuscito."
        )
    if control:
        print(
            "  ATTENZIONE: la chiave contiene "
            "caratteri non ASCII; ricopiala dal sito."
        )
def probe(
    label: str,
    key: str | None,
    user_agent: str | None = None,
) -> None:
    headers = {
        "Content-Type": "application/json",
    }
    if key is not None:
        headers["Authorization"] = f"Bearer {key}"
    if user_agent:
        headers["User-Agent"] = user_agent
    for url in URLS:
        try:
            response = requests.post(
                url,
                headers=headers,
                json=PAYLOAD,
                timeout=20,
            )
        except Exception as exc:
            print(
                f"\n[{label}] {url}\n"
                f"  errore: {type(exc).__name__}: "
                f"{str(exc)[:200]}"
            )
            continue
        print(f"\n[{label}] {url}")
        print(
            "  status:",
            response.status_code,
            "server:",
            response.headers.get("server"),
            "content-type:",
            response.headers.get("content-type"),
        )
        print(
            "  body:",
            repr(response.text[:400]),
        )
def main() -> None:
    key = os.environ.get(
        "DEEPSEEK_API_KEY",
        "",
    )
    try:
        address = socket.gethostbyname(
            "api.deepseek.com"
        )
    except Exception as exc:
        address = f"errore: {exc}"
    print("DNS api.deepseek.com ->", address)
    describe_key(key)
    print(
        "proxy:",
        {
            name: bool(os.environ.get(name))
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
            )
        },
    )
    #
    # Se anche la chiave finta riceve 400, il problema è di rete:
    # la richiesta non arriva all'API.
    #
    probe("chiave finta", FAKE_KEY)
    if not key:
        print(
            "\nDEEPSEEK_API_KEY non impostata: "
            "impostala e riprova."
        )
        return
    probe("chiave utente", key)
    cleaned = (
        key.strip()
        .strip(chr(34))
        .strip(chr(39))
        .strip()
    )
    if cleaned != key:
        probe("chiave ripulita", cleaned)
    probe(
        "chiave utente + UA",
        key,
        user_agent="hagar/0.2.0",
    )
if __name__ == "__main__":
    main()