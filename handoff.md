# SeerControl — Handoff document pour Claude Code

## Contexte du projet

SeerControl est une application web de pilotage astrophoto pour le **Seestar S30 Pro** de ZWO.
L'objectif est de remplacer l'app mobile ZWO par un dashboard pro sur Mac, respectant les standards de l'astrophotographie.

---

## Stack technique retenue

- **Frontend** : HTML/CSS/JS vanilla (dark theme style obs) — ou React si le projet grandit
- **Backend proxy** : Python 3 + FastAPI (ou Flask) — nécessaire pour la découverte UDP Alpaca et futures opérations serveur
- **Protocole** : ASCOM Alpaca REST (HTTP/JSON natif au Seestar S30 Pro)
- **Environnement** : macOS Apple Silicon (M-series)

---

## Ce qu'on sait sur la connexion au Seestar S30 Pro

### Protocole Alpaca natif
Le Seestar S30 Pro expose **nativement** un serveur ASCOM Alpaca — pas besoin d'INDIGO, pas de driver tiers.

**Condition préalable obligatoire :**
Le Seestar doit être connecté au WiFi local en **Station Mode** (dans l'app Seestar → Réglages avancés).
L'IP du Seestar est visible dans l'app une fois le Station Mode configuré.
Le port Alpaca du Seestar est probablement **4700** (à confirmer par découverte ou dans l'app).

### Format des endpoints Alpaca
```
GET  http://{host}:{port}/api/v1/{device_type}/{device_number}/{property}?ClientID=1&ClientTransactionID=N
PUT  http://{host}:{port}/api/v1/{device_type}/{device_number}/{method}
     Content-Type: application/x-www-form-urlencoded
     Body: ClientID=1&ClientTransactionID=N&{param}={value}
```

### Devices disponibles sur le Seestar S30 Pro
| Device type | Device number | Contenu |
|---|---|---|
| `telescope` | 0 | Monture Alt-Az intégrée |
| `camera` | 0 | IMX585 1/1.2" (téléphotographique) |
| `focuser` | 0 | Autofocus intégré |
| `filterwheel` | 0 | Roue 3 filtres intégrée |

### Endpoints clés monture
- `GET telescope/0/connected` — état connexion
- `PUT telescope/0/connected` — `{Connected: "true"}`
- `GET telescope/0/name` — nom du device
- `GET telescope/0/rightascension` — RA en heures décimales
- `GET telescope/0/declination` — Dec en degrés décimaux
- `GET telescope/0/altitude` — altitude en degrés
- `GET telescope/0/azimuth` — azimuth en degrés
- `GET telescope/0/tracking` — bool
- `PUT telescope/0/tracking` — `{Tracking: "true/false"}`
- `GET telescope/0/slewing` — bool
- `PUT telescope/0/slewtocoordinatesasync` — `{RightAscension: "h", Declination: "deg"}`
- `PUT telescope/0/abortslew` — stop immédiat
- `PUT telescope/0/park` — park

### Endpoints clés caméra
- `GET camera/0/name`
- `PUT camera/0/connected`
- `GET camera/0/camerastate` — 0=idle, 1=waiting, 2=exposing, 3=reading, 4=download, 5=error
- `GET camera/0/imageready` — bool
- `PUT camera/0/startexposure` — `{Duration: "secondes", Light: "true"}`
- `PUT camera/0/stopexposure`
- `GET camera/0/imagearray` — retourne les pixels (attention : gros payload)
- `GET camera/0/gainmin` / `gainmax` / `gain`
- `PUT camera/0/gain` — `{Gain: "valeur"}`

### Endpoints clés focuser
- `GET focuser/0/position` — position en steps
- `PUT focuser/0/move` — `{Position: "steps"}`
- `GET focuser/0/ismoving`

### Endpoints clés roue à filtres
- `GET filterwheel/0/position` — index filtre actuel
- `PUT filterwheel/0/position` — `{Position: "0/1/2"}`
- `GET filterwheel/0/names` — noms des filtres

---

## Découverte UDP Alpaca

Le protocole de découverte Alpaca :
- Envoie un broadcast UDP sur le port **32227**
- Message : `alpacadiscovery1` (bytes)
- Réponse du device : `{"AlpacaPort": PORT}`
- Les navigateurs ne peuvent PAS faire de UDP — nécessite un proxy backend Python

```python
import socket, json

def discover_alpaca(timeout=8):
    results = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(('', 0))
    sock.sendto(b'alpacadiscovery1', ('255.255.255.255', 32227))
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            resp = json.loads(data.decode())
            results.append({'host': addr[0], 'port': resp.get('AlpacaPort', 80)})
        except socket.timeout:
            break
    sock.close()
    return results
```

---

## Limitations connues du Seestar S30 Pro en Alpaca

1. **Park/Unpark non câblé** : la commande Park via Alpaca ne ferme pas le bras mécaniquement — il faut ouvrir/fermer le bras depuis l'app Seestar.
2. **Slew sans app active** : `SlewToCoordinatesAsync` échoue si l'app Seestar n'est pas active sur le téléphone (bug connu firmware Alpaca 1.1.3). Avec l'app active, ça fonctionne.
3. **Horloge désynchronisée** : quand l'app téléphone n'est pas active, la monture peut signaler une grosse différence d'horloge avec le PC (~217M secondes).
4. **ROI caméra cassé** : le mode ROI de la caméra génère une erreur dans le driver Alpaca du Seestar — ne pas implémenter pour l'instant.
5. **CORS** : le Seestar peut bloquer les requêtes fetch() directes depuis le navigateur — le proxy Python résout ce problème.

---

## MVP déjà réalisé (code disponible dans index.html)

### Frontend (index.html)
- Config host/port Alpaca avec persistence
- Bouton **Découvrir** : appelle le proxy Python local (localhost:5123) → scan UDP → liste les appareils → sélection auto de l'IP/port
- Si proxy absent : affiche le script `seercontrol_proxy.py` à copier
- Connexion à monture, caméra, focuser
- Polling live toutes les 2s : RA/Dec/Alt/Az/Tracking/Slewing
- Goto RA/Dec avec activation auto du tracking
- Tracking ON/OFF
- Abort Slew, Park
- Journal de session horodaté (niveaux : INFO, OK, WARN, ERROR, CMD, DISC)
- Chrono de session

### Backend proxy (seercontrol_proxy.py)
- Flask + CORS
- Route `GET /discover` → retourne la liste des devices Alpaca sur le LAN
- Port : 5123

---

## Architecture cible (prochaines étapes)

```
seercontrol/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── alpaca_client.py     # Wrapper Alpaca (telescope, camera, focuser, filterwheel)
│   ├── discovery.py         # UDP Alpaca discovery
│   ├── imaging.py           # Séquenceur (Light, Dark, Flat, Bias)
│   └── config.py            # Config persistente (host, port, profils)
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── alpaca.js        # Appels REST
│       ├── mount.js
│       ├── camera.js
│       └── log.js
├── requirements.txt
└── README.md
```

## Modules à développer (par priorité)

1. **Backend FastAPI** — remplace le proxy Flask, ajoute CORS, gestion d'erreurs propre
2. **Module caméra** — preview live (ImageArray → canvas), contrôle gain/expo
3. **Séquenceur** — planification de séquences Light/Dark/Flat/Bias avec FITS output
4. **Roue à filtres** — sélection filtre avec labels custom
5. **Autofocus** — routine AF avec courbe HFD
6. **Planificateur** — liste de cibles avec scheduling automatique
7. **Photométrie différentielle** — intégration AstroImageJ ou calcul interne

---

## Environnement de développement

- macOS Apple Silicon (M-series)
- Python 3.9+
- Pas de dépendance Windows (Alpaca est cross-platform)
- Le Seestar doit être sur le même réseau WiFi que le Mac (Station Mode)
- Pour tester sans le vrai télescope : utiliser l'ASCOM OmniSimulator sur macOS
  - Télécharger : https://github.com/ASCOMInitiative/ASCOM.Alpaca.Simulators/releases
  - Démarre sur localhost:32323 par défaut