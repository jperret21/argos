# Plan: Live Preview — Mise au point en temps réel

## Problème

Le `LivePreviewWorker` actuel utilise le cycle Alpaca complet :
```
startexposure → poll imageready → imagearray JSON download (~33s)
```
→ **33 secondes par frame = inutilisable pour la mise au point.**

## Solution : Preview via port 4801 (binary frame stream)

### Protocole

La Seestar émet des frames brutes sur port 4801 quand elle est en mode
`ContinuousExposure`. Ce mode est activé par `iscope_start_view` sur port 4700.

**Format binary frame port 4801 :**
```
[80 bytes header][N bytes payload]

Header (big-endian, struct '>HHHIHHBBHH') :
  offset 0-1   : _s1 (ignore)
  offset 2-3   : _s2 (ignore)
  offset 4-5   : _s3 (ignore)
  offset 6-9   : size (payload size en bytes)
  offset 10-11 : _s5 (ignore)
  offset 12-13 : _s6 (ignore)
  offset 14    : code (ignore)
  offset 15    : frame_id
  offset 16-17 : width
  offset 18-19 : height

frame_id == 21 : frame preview Bayer GRBG uint16
frame_id == 23 : stack ZIP (ignorer en preview)
size < 1000    : heartbeat (ignorer)

Payload (si frame_id == 21) :
  width × height × 2 bytes
  uint16 big-endian
  Bayer GRBG pattern
  shape numpy : (height, width), dtype '>u2'
```

### Architecture du nouveau module

```
seercontrol/core/seestar/preview_client.py

class SeestarPreviewClient:
    """Reçoit les frames brutes sur port 4801.

    Utilise native_client existant pour le trigger iscope_start_view (port 4700).
    Ouvre une connexion TCP séparée sur port 4801 pour les frames.
    
    Thread de réception (daemon) → signal frame_ready(np.ndarray).
    """

    PREVIEW_PORT = 4801
    HEADER_SIZE  = 80
    HEADER_FMT   = ">HHHIHHBBHH"
    FRAME_PREVIEW = 21
    FRAME_STACK   = 23
    MIN_HEARTBEAT = 1000  # bytes — en dessous = heartbeat, ignorer

    def __init__(self, host: str, native: SeestarNativeClient) -> None: ...

    def start(self) -> None:
        """Active ContinuousExposure via iscope_start_view sur port 4700,
        ouvre TCP 4801, lance le thread de réception."""

    def stop(self) -> None:
        """Envoie iscope_stop_view, ferme TCP 4801, stoppe le thread."""

    # Signal PyQt6 (ou callback)
    frame_ready: Callable[[np.ndarray], None]
    
    def _receive_loop(self) -> None:
        """Thread daemon — lit les frames en continu."""
```

### Intégration dans camera_panel.py

Modifier `LivePreviewWorker` pour utiliser `SeestarPreviewClient` si disponible,
sinon fallback sur le cycle Alpaca (exposition longue pour science).

```
Bouton "Live Preview" :
  Si native_client connecté :
    → SeestarPreviewClient.start()
    → frames arrivent via frame_ready callback
    → affichage dans FitsViewer (stride decimation pour perf)
  Sinon (pas de connexion native) :
    → LivePreviewWorker Alpaca (cycle complet, lent)
    → afficher warning "Preview lent (33s/frame)"
```

### Fallback RTSP (optionnel, phase 2)

Si port 4801 pose des problèmes de compatibilité firmware :
```python
# rtsp://<ip>:4554/stream via OpenCV
import cv2
cap = cv2.VideoCapture(f"rtsp://{host}:4554/stream")
```
~30fps, compressé H.264. Bon pour mise au point visuelle mais frames pas Bayer brut
→ pas utilisable pour science, uniquement pour aperçu.

Nécessite `opencv-python` comme dépendance supplémentaire.

---

## Fichiers à créer / modifier

### Nouveau : `seercontrol/core/seestar/preview_client.py`

```python
"""Binary frame stream receiver for Seestar live preview (port 4801).

Activates ContinuousExposure mode via iscope_start_view on the existing
native JSON-RPC connection (port 4700), then opens a separate TCP socket
on port 4801 to receive raw Bayer GRBG uint16 frames.

Usage::

    preview = SeestarPreviewClient(host, native_client)
    preview.on_frame = lambda arr: ...  # callback with numpy (H, W) uint16
    preview.start()
    # ... user focusing ...
    preview.stop()
"""
```

### Modifier : `seercontrol/workers/exposure_worker.py`

Ajouter `PreviewWorker(QThread)` qui wrap `SeestarPreviewClient`.
Émet `frame_ready = pyqtSignal(np.ndarray)` à chaque frame reçue.

### Modifier : `seercontrol/ui/panels/camera_panel.py`

- Ajouter bouton "Live Preview" / "Mise au point"
- Connecter à `PreviewWorker`
- Afficher dans `FitsViewer` existant
- Indicateur FPS en bas du panneau

---

## Vérification

1. Connecter la monture (native_client)
2. Cliquer "Live Preview"
3. Logs attendus :
   ```
   Preview: iscope_start_view sent
   Preview: port 4801 connected
   Preview: frame received frame_id=21 width=1920 height=1080 (2.07 MP)
   Preview: 2.3 fps
   ```
4. L'image doit apparaître dans le FitsViewer et se rafraîchir ~2-5fps
5. L'image doit être en Bayer GRBG (vert dominant — normal)
6. Bouton Stop → `iscope_stop_view` → preview s'arrête

---

## Notes sur les dimensions

Les frames preview sont **1080×1920** (portrait) selon seevar,
pas 3840×2160 (résolution science).
→ Le firmware under-samples pour le preview → normal.
→ Suffisant pour évaluer la mise au point (HFD, FWHM).
