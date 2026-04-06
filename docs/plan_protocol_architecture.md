# Plan: Architecture protocoles de communication

## Contexte

Analyse du projet seevar révèle que la Seestar S30 Pro expose **trois canaux de communication**
distincts avec des rôles complémentaires. Notre code actuel n'utilise que l'Alpaca REST
(port 32323) et partiellement le port 4700, ce qui explique le preview à 33s et le
mouvement de monture non fonctionnel.

---

## Vue d'ensemble des canaux

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Seestar S30 Pro Firmware                         │
│                                                                      │
│  ╔══════════════════════════════════════════════════════════════╗    │
│  ║  PORT 32323 — HTTP Alpaca REST                               ║    │
│  ║  Rôle : Contrôle hardware (TOUTES les commandes)            ║    │
│  ║  Pas de session lock — multi-client safe                    ║    │
│  ║  Telescope: slew, track, park, unpark, sync                 ║    │
│  ║  Camera:    startexposure, imageready, imagearray/ImageBytes ║    │
│  ║  FilterWheel: position (Dark=0, IR=1, LP=2)                 ║    │
│  ║  Focuser:   position absolu                                  ║    │
│  ║  Latence commande: <1s                                       ║    │
│  ║  Download science frame (JSON): ~33s pour 8.3MP              ║    │
│  ║  Download science frame (ImageBytes binaire): ~3s estimé    ║    │
│  ╚══════════════════════════════════════════════════════════════╝    │
│                                                                      │
│  ╔══════════════════════════════════════════════════════════════╗    │
│  ║  PORT 4700 — TCP JSON-RPC 2.0                                ║    │
│  ║  Rôle : Jogging monture + trigger modes preview              ║    │
│  ║  Session master lock (premier connecté = master)            ║    │
│  ║  Commandes utiles :                                          ║    │
│  ║    scope_speed_move  → jogging continu (pas d'équiv. Alpaca) ║    │
│  ║    iscope_start_view → active ContinuousExposure/RTSP        ║    │
│  ║    iscope_stop_view  → stoppe                                ║    │
│  ║  Événements émis (lecture) :                                 ║    │
│  ║    PiStatus, ScopeMoveToHorizon, ContinuousExposure…         ║    │
│  ╚══════════════════════════════════════════════════════════════╝    │
│                                                                      │
│  ╔══════════════════════════════════════════════════════════════╗    │
│  ║  PORT 4801 — Binary TCP (raw frames)                         ║    │
│  ║  Rôle : Stream de frames brutes pour preview/mise au point   ║    │
│  ║  Activé par : iscope_start_view sur port 4700                ║    │
│  ║  Format header : 80 bytes big-endian >HHHIHHBBHH             ║    │
│  ║  Frame ID 21 : frame preview (Bayer GRBG uint16, 1080×1920) ║    │
│  ║  Frame ID 23 : stack ZIP (ignorer pour preview)              ║    │
│  ║  Frame rate : ~1-5fps selon temps d'exposition               ║    │
│  ╚══════════════════════════════════════════════════════════════╝    │
│                                                                      │
│  ╔══════════════════════════════════════════════════════════════╗    │
│  ║  PORT 4554 — RTSP (H.264 stream)                             ║    │
│  ║  URL : rtsp://<ip>:4554/stream                               ║    │
│  ║  Rôle : Live view haute fréquence pour mise au point fine    ║    │
│  ║  Activé automatiquement quand device passe en stage "RTSP"   ║    │
│  ║  ~30fps, compressé, via OpenCV VideoCapture                  ║    │
│  ║  Utile pour preview temps réel UNIQUEMENT (pas science)      ║    │
│  ╚══════════════════════════════════════════════════════════════╝    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Problème 1 : Download image scientifique (33 secondes)

### Situation actuelle

Notre `camera.py` tente déjà deux chemins :
1. **Fast path** : Alpaca `ImageBytes` (binaire, `np.frombuffer`) — statut : non confirmé sur firmware ZWO
2. **Slow path** : `imagearray` JSON — confirmé, ~33s pour 8.3MP

### Diagnostic à effectuer

Chercher dans les logs ce pattern :
```
# Si fast path réussit :
Camera: ImageBytes received in X.Xs

# Si fallback JSON :
Camera: imagearray JSON received in 32.Xs
```

### Plan de fix

**Option A (recommandée) — Confirmer ImageBytes binaire**
Si notre fast path échoue sur le firmware ZWO, il faut investiguer le format exact.
L'endpoint Alpaca `imagearray` a aussi un format binaire via header `Accept: application/imagebytes`.
Tester explicitement :
```python
headers = {"Accept": "application/imagebytes"}
r = requests.get(f"{base}/imagearray", params=params, headers=headers)
# Si 200 et binaire → parser selon Alpaca spec
# Si 200 JSON quand même → firmware ne supporte pas
```

**Option B — Port 4801 binary stream pour science**
Si ImageBytes non supporté, utiliser port 4801 pour la frame scientifique :
- Envoyer `iscope_start_view` sur 4700 → device émet frames sur 4801
- Recevoir frame_id=21 (preview) ou frame_id=23 (stack)
- Complexité : gestion double connexion (4700 + 4801)

**Option C (immédiate sans risque) — Optimiser pendant le download**
Paralléliser : pendant les 33s de download, pré-calculer les headers FITS,
lire la température CCD, logger les métriques.

---

## Problème 2 : Live preview pour mise au point

### Situation actuelle (BLOQUANTE)

Notre `LivePreviewWorker` fait des cycles complets Alpaca :
```
startexposure → poll imageready → imagearray download (~33s)
```
→ ~33s par frame = **inutilisable pour la mise au point**.

### Solution : Port 4801 binary stream

Séquence pour activer le preview rapide :

```
1. Connexion TCP port 4700 (déjà fait par native_client)
2. Envoyer iscope_start_view(mode="star")
   → Device passe en stage ContinuousExposure
   → Commence à émettre sur port 4801
3. Ouvrir connexion TCP port 4801
4. Loop de réception :
   - recv(80) → header big-endian >HHHIHHBBHH
   - extraire size, frame_id, width, height
   - Si frame_id == 21 et size == width*height*2 :
     - recv(size) → payload Bayer uint16 big-endian
     - np.frombuffer(payload, dtype='>u2').reshape(height, width)
     - cv2.cvtColor(arr, cv2.COLOR_BAYER_GRBG2BGR) → afficher
   - Si frame_id == 23 : ignorer (stack ZIP)
   - Si len(packet) < 1000 : heartbeat, ignorer
5. Afficher chaque frame dans FitsViewer
```

**Fréquence attendue** : 1-5 fps selon le temps d'exposition configuré.

### Fallback : RTSP (port 4554)

Si port 4801 pose des problèmes, RTSP via OpenCV :
```python
cap = cv2.VideoCapture(f"rtsp://{host}:4554/stream")
# Lire frames avec cap.read()
```
~30fps, mais frames compressées (pas Bayer brut → pas pour science).
Bon pour mise au point visuelle.

### Nouveau module à créer

`seercontrol/core/seestar/preview_client.py` :
- Connexion port 4801
- Thread de réception des frames
- Signal PyQt6 `frame_ready(np.ndarray)` vers UI
- `start_preview()` / `stop_preview()`

---

## Problème 3 : Mount control (scope_speed_move)

### Root cause identifiée

Port 4700 a un **session master lock** :
- Premier client connecté = master (peut envoyer commandes)
- Suivants = observers (reçoivent events, commandes ignorées)

Si l'**app native Seestar tourne**, elle est master → nos commandes de jogging ignorées.

### Plan de fix

**Étape 1 — Test sans app native**
Fermer complètement l'app Seestar native → tester jogging.
Si fonctionne → documenter la contrainte (app native incompatible).

**Étape 2 — Voler le master lock**
Notre code envoie déjà `set_setting(master_cli=true)` après connexion.
Vérifier dans les logs que la réponse revient :
```
Native: response id=N method=set_setting OK  ← doit apparaître
```

**Étape 3 — Si firmware ≥ 2706 bloque totalement port 4700**
Fallback : utiliser Alpaca `slewtocoordinatesasync` avec offsets angulaires progressifs.
Lent (~2s de latence) mais fonctionnel. Mouvement moins fluide.

### Code actuel : native_client.py

Le code est propre. Séquence actuelle :
```
UDP 4720 (scan_iscope) → TCP 4700 → reader thread → heartbeat thread
→ get_device_state (firmware detect) → set_setting(master_cli=true)
→ scope_speed_move
```

**Pas de refactoring nécessaire** — juste valider sur le terrain.

---

## Fichiers à créer / modifier

| Action | Fichier | Priorité |
|--------|---------|----------|
| **Créer** | `seercontrol/core/seestar/preview_client.py` | Haute |
| **Modifier** | `seercontrol/ui/panels/camera_panel.py` | Haute |
| **Modifier** | `seercontrol/workers/exposure_worker.py` | Haute |
| **Créer** | `seercontrol/core/alpaca/filterwheel.py` | Moyenne |
| **Modifier** | `seercontrol/core/imaging/fits_writer.py` | Moyenne |
| **Modifier** | `seercontrol/core/alpaca/camera.py` | Faible |

---

## Dépendances Python à ajouter

```toml
# Pour RTSP fallback (si besoin)
"opencv-python>=4.9.0"  # cv2.VideoCapture pour RTSP
```

Pour port 4801 : pas de dépendance supplémentaire (socket standard).
