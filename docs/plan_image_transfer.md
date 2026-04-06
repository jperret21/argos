# Plan: Transfert d'images — Optimisation

## Situation actuelle

| Méthode | Temps | Statut |
|---------|-------|--------|
| Alpaca `imagearray` JSON | ~33s pour 8.3MP | ✅ Confirmé, utilisé en prod |
| Alpaca `ImageBytes` binaire | ~3-5s estimé | ❓ Non confirmé sur firmware ZWO |
| Port 4801 binary stream | <1s (continu) | ✅ Actif firmware, utilisé pour preview |
| RTSP port 4554 | ~30fps compressé | ✅ Actif firmware, preview uniquement |

## Comprendre le problème

Un téléchargement JSON pour 3840×2160 pixels :
- 3840 × 2160 = 8 294 400 pixels
- int32 par pixel → 33 177 600 bytes de données brutes
- JSON serialization overhead : ~3x → ~99 MB de texte à parser
- Réseau WiFi 20 Mb/s → 40s théorique
- **C'est inévitable avec JSON — il faut ImageBytes binaire**

## Option 1 (priorité haute) — Tester Alpaca ImageBytes

L'endpoint Alpaca supporte une variante binaire via header HTTP `Accept`.
Notre `camera.py` a déjà ce code (fast path) — vérifier s'il fonctionne.

### Vérification

Regarder dans les logs si le fast path est utilisé :
```
# Fast path (binaire) :
Camera: ImageBytes received in 3.2s (7,741,440 bytes raw)

# Slow path (JSON) :
Camera: imagearray JSON 32.8s
```

Si le fast path échoue, ajouter du logging détaillé :
```python
try:
    headers = {"Accept": "application/imagebytes"}
    r = requests.get(f"{base}/imagearray", headers=headers, ...)
    logger.debug("ImageBytes status=%d content-type=%s", r.status_code, r.headers.get("Content-Type"))
    if "imagebytes" in r.headers.get("Content-Type", ""):
        # Parse binary format
        ...
    else:
        logger.warning("ImageBytes not supported — falling back to JSON")
except Exception as e:
    logger.warning("ImageBytes failed: %s — falling back to JSON", e)
```

### Format Alpaca ImageBytes (si supporté)

```
Metadata JSON header (first bytes, length-prefixed)
Followed by raw binary image data
```

Voir Alpaca Platform 1.3+ spec pour le format exact.

## Option 2 — Port 4801 pour science frame

Si ImageBytes non supporté, utiliser le binary stream port 4801 pour les frames scientifiques.

**Workflow :**
```
1. native_client: iscope_start_view(mode="star")   ← active ContinuousExposure
2. Ouvrir TCP port 4801
3. Attendre frame_id=21 (preview) ou frame_id=23 (stack ZIP)
4. Pour science : utiliser frame_id=23 (stack = intégration multi-frames)
   - Décompresser ZIP → image stacked uint16
5. Fermer port 4801
6. native_client: iscope_stop_view
```

**Avantages :**
- Download < 1s (binary, pas de JSON)
- Données raw Bayer GRBG directes
- Même données que le firmware utilise internalement

**Inconvénients :**
- Complexité additionnelle (double connexion 4700 + 4801)
- Nécessite que port 4700 fonctionne en mode master
- Pas de contrôle fin du temps d'exposition via ce canal

## Option 3 — Optimisations immédiates (sans changer de protocole)

Sans changer le download JSON, réduire le temps *perçu* :

### Pendant le download (33s) — paralléliser

```python
async def acquire_and_process():
    # Lancer le download en thread
    download_future = executor.submit(camera.get_image_array)

    # Pendant ce temps :
    temp = camera.get_temperature()          # <1s
    pos = telescope.get_position()           # <1s
    # Pré-calculer FITS headers
    headers = fits_writer.build_headers(pos, temp, ...)

    # Attendre fin du download
    image_array = download_future.result()

    # Écrire FITS immédiatement (headers déjà prêts)
    fits_writer.write(image_array, headers, path)
```

### Indiquer la progression dans l'UI

Afficher une barre de progression pendant le download :
```
⌛ Téléchargement image: ████████░░ 75%  (25s / ~33s)
```

## Recommandations par cas d'usage

| Cas | Solution recommandée |
|-----|---------------------|
| Science (unique frame) | Tester ImageBytes d'abord, fallback JSON |
| Preview mise au point | Port 4801 binary stream (plan_live_preview.md) |
| Séquence d'acquisition | ImageBytes si disponible ; sinon port 4801 + optimization |
| Preview rapide (RTSP) | Port 4554 RTSP via OpenCV (optionnel, phase 2) |

## Fichiers concernés

| Fichier | Modification |
|---------|-------------|
| `seercontrol/core/alpaca/camera.py` | Logging détaillé fast/slow path ; tester Content-Type |
| `seercontrol/workers/exposure_worker.py` | Paralléliser metadata pendant download |
| `seercontrol/core/seestar/preview_client.py` | Nouveau — port 4801 receiver (voir plan_live_preview.md) |
| `seercontrol/ui/panels/camera_panel.py` | Barre de progression download |
