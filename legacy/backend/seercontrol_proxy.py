#!/usr/bin/env python3
# argos_proxy.py — Proxy UDP Alpaca pour SeerControl
# Usage : pip install flask flask-cors && python3 argos_proxy.py

import socket
import json
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


def discover_alpaca(timeout=8):
    """Envoie un broadcast UDP Alpaca sur le port 32227 et collecte les réponses."""
    results = []
    msg = b'alpacadiscovery1'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(('', 0))
    try:
        sock.sendto(msg, ('255.255.255.255', 32227))
        print(f"[Discovery] Broadcast envoyé sur :32227, attente {timeout}s...")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                resp = json.loads(data.decode())
                port = resp.get('AlpacaPort', 80)
                entry = {'host': addr[0], 'port': port}
                results.append(entry)
                print(f"[Discovery] Trouvé : {addr[0]}:{port}")
            except socket.timeout:
                break
            except Exception as e:
                print(f"[Discovery] Erreur parsing réponse : {e}")
    finally:
        sock.close()
    return results


@app.route('/discover')
def discover():
    devices = discover_alpaca()
    print(f"[Discovery] {len(devices)} appareil(s) trouvé(s).")
    return jsonify({'devices': devices})


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'service': 'SeerControl Proxy'})


if __name__ == '__main__':
    print("=" * 50)
    print("  SeerControl Proxy — ASCOM Alpaca UDP Discovery")
    print("  http://localhost:5123")
    print("  /discover  → scan UDP Alpaca LAN")
    print("  /health    → statut du proxy")
    print("=" * 50)
    app.run(host='localhost', port=5123, debug=False)