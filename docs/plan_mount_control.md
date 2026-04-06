# Plan: Contrôle monture — Jogging & Slewing

## Architecture protocoles pour la monture

### Alpaca REST (port 32323) — Tout sauf le jogging

| Commande | Endpoint | Notes |
|----------|----------|-------|
| Connexion | `PUT telescope/0/connected Connected=true` | Toujours en premier |
| Dépliage bras | `PUT telescope/0/unpark` | Déclenche ScopeMoveToHorizon |
| Rangement bras | `PUT telescope/0/park` | Ferme le bras |
| Suivi sidéral | `PUT telescope/0/tracking Tracking=true` | Activer avant slew |
| Slew vers cible | `PUT telescope/0/slewtocoordinatesasync RightAscension=<h>&Declination=<d>` | Async, poll slewing |
| Sync | `PUT telescope/0/synctocoordinates RightAscension=<h>&Declination=<d>` | Post plate-solve |
| Abort | `PUT telescope/0/abortslew` | Stop immédiat |
| Position | `GET telescope/0/rightascension` + `declination` + `altitude` + `azimuth` | Poll toutes les 2s |

**Erreurs communes :**
- `1032` = Not initialised → unpark d'abord
- `1279` = Cible sous l'horizon → attendre

### Port 4700 JSON-RPC — Jogging uniquement

**Pourquoi port 4700 pour le jogging ?**
Alpaca `MoveAxis` retourne erreur `1032` sur le firmware Seestar.
`scope_speed_move` est la seule option pour le jogging continu.

**Commande jogging :**
```json
{"id": N, "method": "scope_speed_move", "params": {"speed": 4000, "angle": 0, "dur_sec": 2}}
```

**Angles :** 0=Nord, 90=Est, 180=Sud, 270=Ouest
**Vitesses :** 500-8000 (4000=normal, 8000=rapide)

**Commande stop :**
```json
{"id": N, "method": "iscope_stop_view", "params": {}}
```

---

## Problème actuel : scope_speed_move timeout

### Hypothèses par probabilité

**H1 — App native Seestar tient le master lock (très probable)**

Le port 4700 a un session master lock. Si l'app Seestar native tourne :
- Elle se connecte en premier → elle est master
- Nos commandes `scope_speed_move` arrivent en tant qu'observer → ignorées
- Notre `set_setting(master_cli=true)` tente de voler le lock
- Peut marcher, mais l'app native risque de se déconnecter

**Test H1 :** Fermer complètement l'app native → relancer SeerControl → tester jogging.

**H2 — Firmware ≥ 2706 bloque les commandes sur port 4700 (possible)**

Les firmwares ≥ 2706 utilisent SSL pour l'auth. Il est possible que les commandes
de contrôle (hors read-only) soient bloquées sur port 4700.

**Test H2 :** Si H1 ne suffit pas, vérifier avec un telnet/netcat si des réponses
arrivent sur port 4700 pour `scope_speed_move`.

**H3 — Bras physiquement fermé (faible)**

Le user a confirmé que "fermer le bras" fonctionne (via Alpaca park).
La question est : est-ce que `scope_speed_move` nécessite le bras ouvert ?
Normalement non — le jogging peut fonctionner bras ouvert ou fermé.

---

## Plan de fix mount control

### Fix 1 (immédiat) — Test terrain

```
1. Fermer l'app Seestar native sur le téléphone/tablette
2. Lancer ./run.sh
3. Connecter la monture
4. Ouvrir Manual Control
5. Appuyer sur flèche Nord 3 secondes
6. Vérifier les logs :
```

**Logs attendus si OK :**
```
Native: claiming master CLI control…
Native → [10004] set_setting  params={'master_cli': True}
Native: response id=10004 method=set_setting OK
[bouton pressé]
Native → [10005] scope_speed_move  params={'speed': 8000, 'angle': 0, 'dur_sec': 2}
Native: response id=10005 method=scope_speed_move OK  ← CLEF
[monture bouge physiquement]
```

**Logs si H2 (firmware bloque) :**
```
Native: response id=10004 method=set_setting OK  ← master_cli OK
Native → [10005] scope_speed_move…
Native: scope_speed_move [10005] — no response within 3.0s  ← toujours timeout
```

### Fix 2 — Si firmware bloque port 4700 (fallback Alpaca)

Implémenter le jogging via Alpaca `slewtocoordinatesasync` avec petits offsets.

**Principe :**
```
Bouton Nord pressé :
  1. Lire RA, Dec actuels
  2. Calculer offset : Dec += delta (selon vitesse choisie)
  3. slewtocoordinatesasync(RA, Dec + delta)
  4. Poll slewing → Repeat pendant que bouton tenu
Bouton relâché :
  abortslew
```

**Inconvénients :**
- Latence ~2s par commande (aller-retour Alpaca + poll)
- Mouvement saccadé
- Moins de contrôle sur la vitesse

**Avantages :**
- Fonctionne même si port 4700 inaccessible
- Utilise uniquement Alpaca (stable)

**Code à modifier :** `native_client.py` → ajouter fallback dans `mount_panel.py`.

---

## Séquence d'initialisation complète recommandée

```
1. Connexion Alpaca
   PUT telescope/0/connected Connected=true

2. Unpark (déployer le bras)
   PUT telescope/0/unpark
   [Attendre ScopeMoveToHorizon event ou 3s]

3. Activer le suivi sidéral
   PUT telescope/0/tracking Tracking=true

4. Connexion native TCP (port 4700)
   UDP 4720 scan_iscope
   TCP 4700 connect
   set_setting(master_cli=true)  ← voler le master lock

5. [Prêt pour jogging et slewing]
```

---

## Machine d'états monture

```
DÉCONNECTÉ
    ↓ connect()
CONNECTÉ (bras fermé, AtPark=true)
    ↓ unpark()
DÉPLOYÉ (bras ouvert, AtPark=false)
    ↓ set_tracking(true)
TRACKING (suivi sidéral actif)
    ↓ slew_to(ra, dec)
SLEWING (en mouvement vers cible)
    ↓ [slewing=false]
ON TARGET (sur la cible, tracking)
    ↓ [pendant session]
    ├── scope_speed_move(angle, speed) → jogging manuel
    └── startexposure() → acquisition science
    ↓ park()
PARKÉ (bras fermé)
```

---

## Fichiers concernés

| Fichier | Modification |
|---------|-------------|
| `seercontrol/core/seestar/native_client.py` | Déjà implémenté — tester uniquement |
| `seercontrol/ui/panels/mount_panel.py` | Ajouter fallback Alpaca jogging si native KO |
| `seercontrol/ui/panels/manual_control_dialog.py` | Indiquer visuellement si jogging natif ou Alpaca |
| `seercontrol/core/alpaca/telescope.py` | Ajouter `jog_offset(direction, speed)` pour fallback |
