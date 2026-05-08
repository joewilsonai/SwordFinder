#!/usr/bin/env python3
"""Mint a local X OAuth2 PKCE token with media.write for SwordFinder."""

import argparse
import base64
import hashlib
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - helper still works when env is already sourced.
    load_dotenv = None


AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/callback"
DEFAULT_SCOPES = ("tweet.read", "tweet.write", "users.read", "media.write", "offline.access")


def make_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes=DEFAULT_SCOPES,
) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def read_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    encoded = os.getenv(f"{name}_B64")
    if encoded:
        return base64.b64decode(encoded).decode().strip()
    return ""


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> dict:
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }
    ).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if client_secret:
        encoded_credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded_credentials}"

    request = urllib.request.Request(TOKEN_URL, data=form, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def wait_for_callback(redirect_uri: str, expected_state: str) -> str:
    parsed = urllib.parse.urlparse(redirect_uri)
    result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            result.update(query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif'>"
                b"<h1>SwordFinder X auth received.</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )

        def log_message(self, *_args):
            return

    server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 8080), CallbackHandler)
    server.handle_request()

    if result.get("error"):
        raise SystemExit(f"X authorization failed: {result.get('error')}")
    if result.get("state") != expected_state:
        raise SystemExit("OAuth state did not match. Aborting.")
    if not result.get("code"):
        raise SystemExit("X callback did not include an authorization code.")
    return result["code"]


def print_secret_exports(payload: dict) -> None:
    access_token = payload.get("access_token", "")
    refresh_token = payload.get("refresh_token", "")
    scope = payload.get("scope", "")
    if not access_token:
        raise SystemExit("Token response did not include an access token.")

    def encode(value: str) -> str:
        return base64.b64encode(value.encode()).decode()

    print("Granted scope:", scope or "(not returned)")
    print()
    print("Set these as Railway variables:")
    print(f"X_OAUTH2_ACCESS_TOKEN_B64={encode(access_token)}")
    if refresh_token:
        print(f"X_OAUTH2_REFRESH_TOKEN_B64={encode(refresh_token)}")
    if scope:
        print(f"X_OAUTH2_SCOPE={scope}")
    print("X_MEDIA_UPLOAD_ENABLED=true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    args = parser.parse_args()

    if load_dotenv:
        load_dotenv()

    client_id = read_env("X_CLIENT_ID") or read_env("TWITTER_CLIENT_ID")
    client_secret = read_env("X_CLIENT_SECRET") or read_env("TWITTER_CLIENT_SECRET")
    if not client_id:
        raise SystemExit("Set X_CLIENT_ID first, or source ~/.luna/secrets/keys.env.")

    code_verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    authorize_url = build_authorize_url(
        client_id=client_id,
        redirect_uri=args.redirect_uri,
        state=state,
        code_challenge=make_code_challenge(code_verifier),
    )

    print("Opening X authorization URL with scopes:")
    print(" ".join(DEFAULT_SCOPES))
    print()
    print(authorize_url)
    print()
    webbrowser.open(authorize_url)

    code = wait_for_callback(args.redirect_uri, state)
    payload = exchange_code_for_token(client_id, client_secret, args.redirect_uri, code, code_verifier)
    print_secret_exports(payload)


if __name__ == "__main__":
    main()
