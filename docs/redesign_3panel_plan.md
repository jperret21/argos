# SeerControl — Plan de refonte « 3 panneaux » (spec d'implémentation)

> Document de conception destiné à piloter l'implémentation par un autre modèle
> (DeepSeek). Toute la réflexion est ici ; chaque **Work Unit (WU)** est un prompt
> autonome à copier-coller. Donner systématiquement à l'implémenteur :
> 1. le prompt du WU, 2. l'**Annexe A** (API existantes), 3. les règles d'archi de `CLAUDE.md`.

Auteur de la réflexion : Claude · Date : 2026-06-13 · Cible : branche `main`.

---

## 0. Règles d'architecture (rappel, NON négociable)

- `core/` n'importe **jamais** PyQt6 (testable sans écran).
- `ui/` n'importe **jamais** `requests`/`socket` — tout I/O passe par un **worker** (`QThread`).
- `workers/` est la seule couche qui importe à la fois `core/` et `PyQt6`.
- Communication thread → UI : **signaux Qt uniquement** (`pyqtSignal`). Jamais de variable partagée.
- Tout appel réseau/disque/calcul > 50 ms tourne dans un `QThread`. `QThread.msleep()`, jamais `time.sleep()`.
- FITS = uint16, `BZERO=32768`. Couleurs depuis `ui/theme.py` (jamais en dur). Deps via `uv add`.
- Python 3.11+, type hints partout, docstrings Google, black, ruff, lignes ≤ 100, logging (`getLogger(__name__)`), jamais `print()`.

---

## 1. Objectif & architecture cible

### 1.1 De 4 modes → 3 panneaux

| Aujourd'hui (`ui/sidebar.py`) | Cible | Sort / Devient |
|---|---|---|
| `equipment` (🔌) | **Connection** (🔌) | Connexion appareils **+ carte Stellarium fusionnée** |
| `target` (🎯) | — | **SUPPRIMÉ entièrement** (Simbad, profils, Slew & Start) |
| `imaging` (📷) | **Acquisition** (📷) | Le gros panneau : preview + tous les outils de prise de vue |
| `settings` (⚙) | **Configuration** (⚙) | Réglages soft (thème, langue, chemins, observateur, crédits) |

> **Décision produit (validée) :** targeting **100 % via Stellarium**, aucune saisie
> manuelle de coordonnées, aucune recherche d'objet dans SeerControl. L'onglet Target
> et le « pull HTTP » disparaissent.

### 1.2 Schéma de fenêtre cible

```
┌───────────────────────────────────────────────────────────┐
│ TopStatusBar : badges mount/camera/focuser/filtre + tracking│
├──┬────────────────────────────────────────────────────────┤
│🔌│                                                          │
│📷│   QStackedWidget : page du mode courant                  │
│⚙ │   (Connection | Acquisition | Configuration)            │
└──┴────────────────────────────────────────────────────────┘
```

### 1.3 Le problème central : qui possède les appareils ?

Aujourd'hui c'est `ImagingPage` qui possède les objets `Telescope`/`Camera`/`Focuser`
+ les workers. Avec 3 panneaux, **la connexion (panel 1) et l'acquisition (panel 2)
doivent partager les mêmes appareils.** → On introduit un **`SessionController`**
(QObject, niveau UI) possédé par le `Shell`, injecté dans les deux panels. C'est le
**socle (WU-A)** dont dépend tout le reste.

```
Shell
 └── SessionController (QObject)         ← possède devices + workers
      ├── Telescope / Camera / Focuser / FilterWheel
      ├── MountPollingWorker, LivePreviewWorker, AutofocusWorker, SequenceWorker
      ├── API: connect_*, disconnect_*, slew_to, start_preview, run_autofocus, run_sequence…
      └── signals: device_state_changed, position_updated, frame_ready, log_message, tracking_changed…
 ├── ConnectionPanel(controller)         ← branche les boutons de connexion + Stellarium
 ├── AcquisitionPanel(controller)        ← preview, capture, focus, séquenceur, jog
 └── ConfigurationPanel(config)
```

---

## 2. Réflexions de conception (ce que tu m'as demandé d'étoffer)

### 2.1 Liste EXHAUSTIVE des paramètres d'acquisition (panel 2)

**⚠️ Vérité matérielle Seestar S30 Pro** (cf. `handoff.md`) : la caméra n'expose
**que l'exposition et le gain** en écriture. Pas de refroidissement (capteur non
refroidi), pas de binning réglable, pas de ROI (bug firmware — interdit), `offset`
en **lecture seule**. La liste ci-dessous est donc **tiérisée** : ce qui pilote
vraiment l'appareil vs. ce qui est de l'affichage vs. ce qui est métadonnée.

#### Tier 1 — Réglages de capture réels (écrits dans le FITS)
| Param | Type / plage | Source API | Note |
|---|---|---|---|
| Type de frame | Light / Dark / Flat / **Bias (=Offset)** | → `IMAGETYP`, flag `Light` | Bias = expo minimale, obturateur |
| Exposition (s) | float, min..max device | `Camera.start_exposure(duration, light)` | |
| Gain | int, `gainmin..gainmax` | `Camera.get/set_gain` | |
| Filtre | 3 positions (roue) | `FilterWheel.get/set_position`, `position_name` | N/A pour Dark/Bias |
| Nombre d'images (N) | int ≥ 1 | séquenceur | |
| Intervalle entre frames | s ≥ 0 | séquenceur | |
| Nom de l'objet | str | `FrameContext.object_name` | auto depuis goto Stellarium |
| **Chemin de sauvegarde** | path | `Config.sessions_path` (défaut) + override | dossier Siril auto |
| Binning | **fixe 1×1** | affichage seul | Seestar ne change pas le binning |

#### Tier 2 — Affichage / stretch (PREVIEW UNIQUEMENT, JAMAIS dans le FITS)
> **Intégrité scientifique :** un Light est sauvé en **linéaire 16-bit brut**.
> gamma/contraste/stretch ne touchent **que l'affichage écran**. Ne jamais graver
> ces valeurs dans le FITS.

- Auto-stretch (STF, percentile 1 %–99 %) on/off
- Black point / White point (sliders ou min/max)
- Midtones / **gamma** (slider) · Brightness / **contraste** (slider)
- Histogramme interactif (option log)
- **Sélecteur de canal** : R / G / B / L synthétique / Bayer brut (debayer GRBG via `extract_channel`)
- Zoom / pan (natif PyQtGraph) + boutons « 1:1 » et « Fit »
- Réticule / crosshair, indicateur de FOV, inversion, LUT fausses couleurs (option)

#### Tier 3 — Mise au point (choix validé : HFD/FWHM + overlay + graphe + autofocus)
- Lecture **HFD/FWHM** de la frame courante + **nombre d'étoiles** (`compute_hfd`)
- **Overlay HFD** sur les étoiles détectées (cercles)
- **Graphe d'historique HFD** (N dernières frames) — voit-on l'amélioration ?
- Nudge focuser manuel : position courante + boutons In/Out (±pas), sélecteur de pas
- Bouton **Autofocus** → routine courbe en V (`AutofocusWorker`), affiche la courbe + position optimale
- Température focuser (lecture) pour déclencher un refocus
- *(Hors v1 : loupe/zoom dédié & aide Bahtinov — le zoom PyQtGraph couvre le besoin de base ; à ajouter en Phase 2.)*

#### Tier 4 — Contrôle monture (jog / center / track) dans le panel
- **Pavé directionnel** N/S/E/O : appui → `move_axis(axis, ±rate)`, relâché → `stop_axis(axis)`
- Sélecteur de **vitesse** (presets type Guide/Center/Find/Max, ou ×0.5/×1/×2/×4)
- **Stop / Abort slew** (`abort_slew`)
- **Tracking ON/OFF** + taux (Sidéral/Lunaire/Solaire via `set_tracking_rate`)
- **Center & Track** : re-slew vers la cible courante + tracking on (pas de plate-solve en v1)
- Lecture live RA/Dec/Alt/Az + indicateur slewing

#### Tier 5 — Séquenceur AVANCÉ (choix validé) → voir WU-G
Table multi-étapes ; presets sauvegardables (remplacent les anciens « profils »).

#### Tier 6 — Métadonnées / session (depuis Config, lecture seule ou éditable ici)
- Observateur, site lat/lon/élév (depuis panel Configuration → `Config.observer`)
- Annotation/notes (photométrie, ex. « T CrB pre-outburst » → `FrameContext.annotation`)
- Lectures seules : CCD-TEMP, EGAIN, offset, readout mode (déjà gérés par `FITSWriter`)

#### Tier 7 — Non supporté sur Seestar (afficher désactivé + tooltip, ou omettre)
Refroidissement/température cible · ROI/subframe (**interdit**) · réglage offset · vitesse USB.

### 2.2 Stellarium : supprimer le « pull » ambigu, garder UNIQUEMENT le serveur TCP

**Diagnostic.** Il existe deux mécanismes aujourd'hui :
1. ✅ **Serveur TCP** (`core/stellarium/{protocol,server}.py` + `workers/stellarium_worker.py`) :
   implémente le **protocole standard Stellarium Telescope Control**. SeerControl est un
   « télescope » auquel Stellarium se connecte. C'est event-driven et non ambigu.
2. ❌ **Pull HTTP** (`core/stellarium/remote_pull.py` + `_PullRunner` dans `shell.py`) :
   interroge l'API Remote Control de Stellarium pour lire l'objet sélectionné. C'est le
   système ambigu à supprimer.

**Flux cible (standard, validé par la doc Stellarium).**
1. L'utilisateur ouvre Stellarium, active le plugin **Telescope Control**, ajoute un
   télescope type *« External software or a remote computer »* en **TCP** vers
   `127.0.0.1:10001` (host/port configurables dans le panel Connection).
2. Il sélectionne un objet et presse **Ctrl+1** (⌘+1 sur Mac) = *« Slew telescope to
   selected object »*. Stellarium envoie un `GotoMessage` (RA/Dec J2000) au serveur.
3. `StellariumWorker.target_received(ra, dec)` → `SessionController.slew_to(ra, dec)` +
   tracking on. SeerControl renvoie en continu sa position (`set_position`) pour que le
   réticule Stellarium suive la monture.

→ **WU-D supprime** `remote_pull.py`, `_PullRunner*`, le signal `pull_requested`, le bouton
« Pull » et les handlers `_on_stellarium_pull*`. La carte Stellarium **déménage** dans le
panel Connection.

> Note : dans Stellarium, « centrer » (espace) ne déplace que la **vue**, pas le télescope.
> Le seul geste qui pilote la monture est le **slew (Ctrl+1)**. C'est volontaire et sans
> ambiguïté — c'est ce qu'on veut.

### 2.3 i18n (langue dans le panel Configuration)

Mettre en place un mécanisme léger FR/EN (dictionnaire `tr(key)` ou `QTranslator`).
La langue est dans `Config` (`ui.language`). Voir WU-I. Les strings UI sont les seules
autorisées en français (cf. CLAUDE.md).

---

## 3. Plan multi-agent (découpage & dépendances)

| WU | Titre | Dépend de | Parallélisable |
|---|---|---|---|
| **A** | `SessionController` (socle devices + workers) | — | non (socle) |
| **B** | Sidebar 3 modes + suppression Target + rewire Shell | A | après A |
| **C** | Panel **Connection** (appareils + Stellarium) | A, B | avec D, E |
| **D** | Simplification Stellarium (suppr. pull) | B | avec C, E |
| **E** | Panel **Acquisition** — squelette + preview + stretch + HFD overlay | A, B | avec C, D |
| **F** | Acquisition — capture + focus/autofocus | A, E | après E |
| **G** | Séquenceur **avancé** (`SequenceWorker` core + table UI) | A, E, F | après F |
| **H** | Acquisition — pavé jog + center/track | A, E | après E |
| **I** | Panel **Configuration** (thème/langue/chemins/observateur/crédits) + i18n | B | avec C–H |

**Ordre conseillé :** A → B → (C, D, E en //) → (F, H en //) → G → I.
**« L'agent sur le gros morceau »** = E+F+G (le panel Acquisition), à confier en priorité
et idéalement à une seule session pour la cohérence.

---

## 4. Prompts détaillés par Work Unit

> Chaque section est un prompt autonome pour l'implémenteur. Reproduire la **section 0**
> et l'**Annexe A** en tête de chaque prompt.

### WU-A — `SessionController` (socle)

**But.** Extraire toute la possession des appareils + workers hors de `ImagingPage` vers
un nouvel objet `SessionController` réutilisable par les panels Connection et Acquisition.

**Fichier à créer :** `seercontrol/ui/session_controller.py`
*(c'est un objet UI-level : il a le droit d'instancier les workers Qt et de tenir les
objets `core`. Il ne fait aucun appel réseau lui-même — il délègue aux workers.)*

**Classe :**
```python
class SessionController(QObject):
    # --- état appareils ---
    device_state_changed = pyqtSignal(str, str, str)   # device_id, state('connected'|'connecting'|'disconnected'|'error'), info
    position_updated     = pyqtSignal(float, float, bool)  # ra_h, dec_d, slewing
    tracking_changed     = pyqtSignal(object)          # bool|None
    # --- imagerie ---
    frame_ready          = pyqtSignal(object, object, object, object)  # preview_arr, full_arr, start_dt, end_dt
    hfd_measured         = pyqtSignal(object, int)     # hfd|None, star_count
    # --- divers ---
    log_message          = pyqtSignal(str, str)        # level, message
    discovered_address   = pyqtSignal(str, int)

    def __init__(self, config: Config) -> None: ...

    # Connexion (chaque méthode lance la connexion ; émet device_state_changed)
    def start_discovery(self) -> None: ...
    def connect_mount(self, host: str, port: int) -> None: ...
    def connect_camera(self, host: str, port: int) -> None: ...
    def connect_focuser(self, host: str, port: int) -> None: ...
    def connect_filterwheel(self, host: str, port: int) -> None: ...
    def disconnect_device(self, device_id: str) -> None: ...
    def disconnect_all(self) -> None: ...
    def is_connected(self, device_id: str) -> bool: ...

    # Monture
    def slew_to(self, ra_h: float, dec_d: float, label: str = "") -> None: ...
    def abort_slew(self) -> None: ...
    def set_tracking(self, on: bool) -> None: ...
    def set_tracking_rate(self, rate: int) -> None: ...
    def jog_start(self, axis: int, rate: float) -> None: ...   # move_axis off-thread
    def jog_stop(self, axis: int) -> None: ...
    def center_and_track(self) -> None: ...                    # re-slew cible courante + tracking on

    # Caméra / preview
    def start_preview(self, exposure: float, gain: int, scale: int = 4) -> None: ...
    def stop_preview(self) -> None: ...
    def update_preview_settings(self, exposure: float, gain: int) -> None: ...

    # Focuser / autofocus
    def focuser_step(self, delta: int) -> None: ...
    def focuser_move_to(self, position: int) -> None: ...
    def run_autofocus(self, exposure_s: float, gain: int, half_range: int, num_steps: int) -> None: ...

    # Séquenceur (branché en WU-G)
    def run_sequence(self, plan: "SequencePlan") -> None: ...
    def stop_sequence(self) -> None: ...

    # Accès pour FrameContext (lecture position/temp courantes)
    def current_frame_context(self, **overrides) -> FrameContext: ...

    def shutdown(self) -> None:  # quit()+wait() de tous les workers
        ...
```

**Détails d'implémentation.**
- Réutiliser tels quels : `MountPollingWorker` (→ `position_updated`, `connection_lost`),
  `LivePreviewWorker` (→ `frame_ready`), `AutofocusWorker`. **Le code de connexion/preview
  existe déjà dans `ImagingPage`** : le déplacer ici sans changer la logique.
- `jog_start/stop` doivent exécuter `Telescope.move_axis/stop_axis` **hors thread UI**
  (réutiliser le pattern `QRunnable` déjà présent dans `imaging_page.py` / `shell.py`).
- `current_frame_context` lit `Telescope.get_position`, `Camera.get_ccd_temperature`,
  `get_offset`, `get_electrons_per_adu`, `get_readout_mode_name`, et les `Config.observer`,
  pour construire un `FrameContext` complet (utilisé par le preview et le séquenceur).
- Toutes les exceptions `AlpacaError` des workers → `log_message.emit("ERROR", ...)` +
  `device_state_changed(..., "error", msg)`. Aucun try/except silencieux.

**Critères d'acceptation.**
- `ImagingPage` n'instancie plus aucun `Telescope/Camera/Focuser/worker` directement :
  elle reçoit un `SessionController` et s'y abonne.
- `from seercontrol.ui.session_controller import SessionController` importe sans QApplication.
- Aucun import `requests`/`socket` dans ce fichier (tout via workers).

---

### WU-B — Sidebar 3 modes + suppression Target + rewire Shell

**But.** Passer la sidebar de 4 à 3 modes, supprimer l'onglet Target, instancier le
`SessionController` dans le `Shell` et l'injecter dans les deux panels.

**Fichiers modifiés :** `ui/sidebar.py`, `ui/shell.py`.
**Fichiers supprimés :** `ui/pages/target_page.py`, `ui/wizard/session_wizard.py`,
`core/targets/` (resolver Simbad + horizon), `core/profiles.py` *(si plus référencé —
vérifier les imports avant suppression).*

**`sidebar.py` :** remplacer `MODES` par :
```python
MODES = [
    ("connection",    "🔌", "Connection",    "Connect Seestar devices and Stellarium"),
    ("acquisition",   "📷", "Acquisition",   "Live preview, focus, capture and sequencing"),
    ("configuration", "⚙",  "Configuration", "Theme, language, paths, observer, credits"),
]
```
Mettre à jour la docstring (« 4 modes » → « 3 modes »), la méthode `pulse` (cibler
`"acquisition"` quand mount+camera connectés au lieu de `"target"`).

**`shell.py` :**
- Instancier `self._controller = SessionController(config)`.
- Registre `_pages` = `{"connection": ConnectionPanel(controller), "acquisition": AcquisitionPanel(controller), "configuration": ConfigurationPanel(config)}`.
- Supprimer tout le wiring Target (`_wire_target_page`, `_on_slew_and_start`).
- Brancher `controller.device_state_changed` → `TopStatusBar.set_device_state` + badges.
- Raccourcis menu : F1=Connection, F2=Acquisition, F3=Configuration.
- `closeEvent` → `self._controller.shutdown()`.
- Mode par défaut : `connection` si rien n'est connecté.

> **Important** : la fonction `_build_window` de `main.py` instancie déjà `Shell(config)`.
> Le flag `SEERCONTROL_LEGACY` peut être retiré une fois le redesign stable (optionnel).

**Critères d'acceptation.** L'app démarre sur 3 modes, plus aucune référence à
`target`/`TargetPage`/`session_wizard`/`resolver`. `compileall` + imports OK.

---

### WU-C — Panel Connection (appareils + Stellarium)

**But.** Un seul panneau pour : (1) découverte + connexion mount/camera/focuser/filterwheel,
(2) connexion/déconnexion du serveur Stellarium.

**Fichier à créer :** `ui/pages/connection_page.py` (+ réutiliser/déplacer `ui/panels/stellarium_card.py`).

**Contenu UI (cards via `ui/design.py`) :**
1. **Card « Découverte »** : champ host/port + bouton *Discover* (`controller.start_discovery`),
   pré-remplit host/port via `controller.discovered_address`. Bouton *Connect all*.
2. **Card par appareil** (Mount / Camera / Focuser / Filter wheel) : badge d'état (LED),
   nom du device, bouton Connect/Disconnect. Câblé à `controller.connect_*/disconnect_device`
   et `controller.device_state_changed`.
3. **Card « Stellarium »** (l'ancienne `StellariumCard`, **sans** le bouton Pull) :
   - host/port (défaut `127.0.0.1:10001`, persistés dans `Config` `stellarium.host/port`)
   - bouton Start/Stop server, badge état + compteur de clients
   - bloc d'aide : « Dans Stellarium : plugin Telescope Control → External software (TCP)
     → host/port ci-dessus → sélectionner un objet → **Ctrl+1 / ⌘+1** pour slew. »
   - le démarrage/arrêt du serveur reste géré par le `Shell` (`StellariumWorker`), le panel
     émet juste `start_server_requested(host, port)` / `stop_server_requested()`.

**Critères d'acceptation.** Connexion d'un appareil depuis ce panel met à jour les badges
ici **et** dans la TopStatusBar **et** est visible par le panel Acquisition (même
`SessionController`). Démarrer Stellarium ici fait suivre le réticule à la position monture.

---

### WU-D — Simplification Stellarium (supprimer le pull HTTP)

**But.** Ne garder que le serveur TCP event-driven.

**Suppressions :**
- `core/stellarium/remote_pull.py` (fichier entier).
- Dans `ui/shell.py` : classes `_PullRunnerSignals`, `_PullRunner`, import
  `pull_selected_object`, méthodes `_on_stellarium_pull`, `_on_stellarium_pull_target`,
  `_on_stellarium_pull_failed`, et la connexion `card.pull_requested.connect(...)`.
- Dans `stellarium_card.py` : signal `pull_requested`, bouton « Pull selected », handlers.

**Conserver / vérifier :** `protocol.py`, `server.py`, `stellarium_worker.py` inchangés.
Le flux `target_received(ra, dec)` doit désormais appeler `SessionController.slew_to(ra, dec)`
(+ tracking on) — câbler dans le `Shell` : `worker.target_received.connect(self._controller.slew_to)`.
La position monture alimente le serveur : `controller.position_updated.connect(worker.update_mount_position)`.

**Critères d'acceptation.** `grep -r remote_pull seercontrol/` ne renvoie rien. Plus aucun
bouton « Pull ». Un Ctrl+1 dans Stellarium déclenche un slew réel.

---

### WU-E — Panel Acquisition : squelette + preview + stretch + HFD overlay

**But.** Poser le panneau central : viewer FITS au centre, rails de contrôle autour ;
brancher le preview live et les contrôles d'affichage (Tier 2) + l'overlay HFD (Tier 3).

**Fichier à créer :** `ui/pages/acquisition_page.py`. Réutiliser `ui/widgets/fits_viewer.py`
(PyQtGraph), `ui/widgets/histogram_dock.py`, `ui/widgets/image_toolbar.py`,
`core/imaging/debayer.py` (`extract_channel`, `compute_hfd`).

**Layout (responsive, pas de tailles fixes) :**
```
┌──────────────┬─────────────────────────────┬──────────────┐
│ Rail gauche  │      Viewer FITS (PyQtGraph) │ Rail droit   │
│ (capture +   │      + overlay HFD + reticle │ (affichage:  │
│  séquence)   │                              │  stretch,    │
│  → WU-F/G    │                              │  histogramme,│
│              │                              │  canal,      │
│  Pavé jog    │                              │  focus →WU-F)│
│  → WU-H      │                              │              │
└──────────────┴─────────────────────────────┴──────────────┘
```
*(Rails = `QScrollArea` de cards `design.py`. Le viewer prend l'espace extensible.)*

**À implémenter dans ce WU :**
- Abonnement `controller.frame_ready` → afficher `preview_arr` dans le viewer.
- Contrôles Tier 2 : auto-stretch on/off, black/white point, gamma, contraste, histogramme
  (réutiliser `histogram_dock`), **sélecteur de canal** (R/G/B/L/Bayer via `extract_channel`),
  boutons 1:1 / Fit, réticule on/off. **Tous appliqués à l'affichage uniquement.**
- Overlay HFD : sur chaque frame, calculer `compute_hfd` et afficher HFD + nb d'étoiles ;
  dessiner des cercles sur les étoiles détectées (toggle).
- Contrôles preview : Start/Stop preview, expo & gain « live » (→ `controller.start_preview` /
  `update_preview_settings`).

**Critères d'acceptation.** Le preview live s'affiche, le stretch/gamma/canal changent
l'image **sans** modifier les données sauvées, HFD s'affiche par frame.

---

### WU-F — Acquisition : capture (Tier 1) + focus/autofocus (Tier 3)

**But.** Le formulaire de capture unitaire + les outils de mise au point.

**Modifie :** `ui/pages/acquisition_page.py` (rail gauche + rail droit « Focus »).

**Capture (Tier 1) — card « Capture » :**
- ComboBox type frame (Light/Dark/Flat/Bias), champ Objet (auto-rempli depuis le label de
  goto Stellarium), ComboBox Filtre (depuis `FilterWheel`), SpinBox Exposition (min/max device),
  SpinBox Gain (`gainmin..gainmax`), champ **Chemin** (défaut `Config.sessions_path`, bouton
  « Parcourir »).
- Bouton **« Take shot »** : une pose → sauvegarde FITS via `FITSWriter.write` dans
  `FITSWriter.session_folder(...)` avec `FITSWriter.build_filename(...)` et le
  `FrameContext` de `controller.current_frame_context(object_name=…, filter_name=…)`.
- Désactiver Objet/Filtre selon le type (Dark/Bias → pas d'objet/filtre).

**Focus (Tier 3) — card « Focus » :**
- Lecture HFD/FWHM + nb étoiles de la dernière frame ; **graphe d'historique HFD**
  (PyQtGraph, N=100 dernières mesures, comme NINA).
- Nudge focuser : position courante (`Focuser.get_position`), boutons **In/Out** (±pas),
  sélecteur de pas (10/50/100/500), bouton Halt.
- Bouton **Autofocus** : ouvre un petit dialog de params (expo, gain, half_range, num_steps),
  lance `controller.run_autofocus(...)` → `AutofocusWorker`. Afficher la **courbe en V**
  (steps → HFD) + position optimale trouvée (`best_found`). Désactiver pendant le run.

**Critères d'acceptation.** « Take shot » produit un FITS conforme dans l'arbo Siril.
L'autofocus balaie le focuser et affiche la courbe V + le minimum.

---

### WU-G — Séquenceur AVANCÉ (`SequenceWorker` core + table UI)

**But.** Séquenceur multi-étapes (choix validé). Logique métier **dans `core/`** (corrige
la dette actuelle où le séquençage est dans l'UI), exécution dans un `QThread`.

**Fichiers à créer :**
- `core/imaging/sequencer.py` — modèle + moteur **sans Qt** :
  ```python
  @dataclass
  class SequenceStep:
      enabled: bool = True
      frame_type: str = "Light"      # Light|Dark|Flat|Bias
      filter_name: str = "LRGB"
      exposure_s: float = 10.0
      gain: int = 80
      count: int = 10
      dither_every: int = 0          # 0 = off (dithering N/A Seestar — voir note)

  @dataclass
  class SequencePlan:
      steps: list[SequenceStep]
      object_name: str = ""
      repeat: int = 1                # répète toute la liste
      autofocus_every_n: int = 0     # 0 = off
      autofocus_on_filter_change: bool = False
      base_dir: Path | None = None   # défaut = Config.sessions_path

  def expand_plan(plan: SequencePlan) -> Iterator[FrameSpec]:
      """Aplatis le plan en suite de frames à shooter (type/filtre/expo/gain/index)."""
  ```
- `workers/sequence_worker.py` — `SequenceWorker(QThread)` qui consomme un `SequencePlan` :
  ```python
  class SequenceWorker(QThread):
      step_started   = pyqtSignal(int, object)              # step_index, SequenceStep
      frame_started  = pyqtSignal(int, int, object)         # done, total, FrameSpec
      frame_saved    = pyqtSignal(str, object)              # path, hfd|None
      progress       = pyqtSignal(int, int, float)          # done, total, eta_seconds
      autofocus_due  = pyqtSignal()                         # demande au controller de lancer l'AF
      error_occurred = pyqtSignal(str)
      finished       = pyqtSignal(bool)                     # completed_fully
      # __init__(camera, telescope, filterwheel, plan, frame_context_provider, parent=None)
  ```

**Boucle du worker (par frame) :** régler filtre (`FilterWheel.set_position`) si besoin →
`Camera.set_gain` → `Camera.start_exposure(expo, light=type==Light)` → poll
`Camera.is_image_ready` (avec `QThread.msleep`) jusqu'au timeout `expo+15s` → `get_image_array`
→ `FITSWriter.write(...)` dans `session_folder/build_filename` → `frame_saved` → respecter
l'intervalle. Gérer Stop (flag), Pause optionnelle. Déclencher `autofocus_due` selon
`autofocus_every_n` / changement de filtre (le `SessionController` orchestre l'AF puis
reprend). Dithering : **laisser le hook mais désactivé** (Seestar Alt-Az sans guidage —
afficher « non supporté » dans l'UI ; option future : micro-nudge `move_axis`).

**UI — card « Sequence » (rail gauche) :**
- **Table d'étapes** (`QTableWidget`) : colonnes On / Type / Filtre / Expo / Gain / Count /
  Dither. Boutons Add / Duplicate / Remove / Move up-down.
- Champs plan : Objet, Repeat, Autofocus every N, AF on filter change.
- Barre de progression globale + ETA + étape courante + frames sauvées.
- Boutons **Start / Pause / Stop**.
- **Save preset / Load preset** (JSON dans `~/.seercontrol/sequences/` ; ce sont les
  « profils » nouvelle version).

**Critères d'acceptation.** Un plan à 2 étapes (ex. 5×Ha 60s + 5×OIII 60s) shoote 10 frames
dans les bons sous-dossiers Siril, progress + ETA corrects, Stop interrompt proprement,
preset rechargeable. La logique de `core/imaging/sequencer.py` est testable sans Qt.

---

### WU-H — Pavé jog + center/track

**But.** Contrôle manuel de la monture dans le panel Acquisition.

**Modifie :** `ui/pages/acquisition_page.py` (card « Mount » du rail gauche).

- **Pavé directionnel** 4 flèches (N/S/E/O) : `pressed` → `controller.jog_start(axis, ±rate)`,
  `released` → `controller.jog_stop(axis)`. Axe 0 = RA/Az, axe 1 = Dec/Alt (cf. `move_axis`).
- Sélecteur de **vitesse** (presets : Slow ×0.5 / Med ×1 / Fast ×2 / Max — mapper sur des
  `rate` deg/s raisonnables).
- Bouton **Stop** (`controller.abort_slew`), **Tracking ON/OFF**, ComboBox taux de tracking.
- Bouton **Center & Track** (`controller.center_and_track`).
- Lecture live RA/Dec/Alt/Az + LED slewing (depuis `controller.position_updated`).

**Critères d'acceptation.** Maintenir une flèche déplace la monture ; relâcher l'arrête.
Tracking et abort fonctionnent. (Tester avec le simulateur ASCOM.)

---

### WU-I — Panel Configuration + i18n

**But.** Construire le 3ᵉ panneau (aujourd'hui placeholder de 10 lignes) et l'i18n.

**Fichiers :** `ui/pages/configuration_page.py` (remplace `settings_page.py`),
`ui/i18n.py` (mécanisme `tr`), `core/config.py` (nouvelles clés).

**Cards :**
1. **Apparence** : sélecteur de thème (au moins « Dark » ; structure extensible),
   **langue** (FR/EN) → `Config["ui.language"]`, police/taille (option).
2. **Chemins** : dossier de sessions par défaut (`Config.sessions_path`, bouton Parcourir),
   dossier des presets de séquence.
3. **Observateur & site** : nom, latitude, longitude, élévation (`Config.observer.*`) —
   utilisés par `FrameContext` (SITELAT/SITELONG/OBSERVER + AIRMASS/MOON).
4. **Stellarium** (option, sinon dans Connection) : host/port par défaut.
5. **Avancé** : niveau de log (`ui.log_level`), reset layout fenêtre.
6. **À propos / Crédits** : version (`Shell.APP_VERSION`), auteur, licence, liens.

**i18n.** `ui/i18n.py` : dict `{"en": {...}, "fr": {...}}` + `tr(key) -> str` lisant
`Config["ui.language"]`. Wrapper les strings UI nouvelles via `tr(...)`. Changement de
langue → message « relancer l'app » (ou re-render si simple). Ne pas sur-ingénierer en v1.

**Clés Config à ajouter :**
```jsonc
{
  "ui": { "language": "fr", "theme": "dark" },
  "stellarium": { "host": "127.0.0.1", "port": 10001 },
  "paths": { "sequences": "~/.seercontrol/sequences" }
}
```

**Critères d'acceptation.** Modifier observateur/site/chemin persiste dans `config.json`
et se reflète dans les FITS suivants. Le sélecteur de langue bascule FR/EN.

---

## 5. Annexe A — API existantes (à fournir à l'implémenteur)

> Signatures réelles présentes sur `main`. **Ne pas réinventer ces classes.**

### `core/alpaca/camera.py` — `Camera`
```
__init__(host, port)
connect() -> str ; disconnect() ; is_connected() -> bool
get_state() -> int            # 0 idle,1 waiting,2 exposing,3 reading,4 download,5 error
is_image_ready() -> bool
get_gain() -> int ; set_gain(gain: int)
get_ccd_temperature() -> float|None
get_electrons_per_adu() -> float|None
get_offset() -> int|None      # LECTURE SEULE
get_readout_mode_name() -> str|None
get_full_well() -> int|None
get_sensor_metadata() -> dict
start_exposure(duration: float, light: bool = True)
stop_exposure()
get_image_array() -> np.ndarray   # uint16 2-D (height, width)
```
*(Plages gain : lire `gainmin/gainmax` via Alpaca si exposées ; sinon 0..max raisonnable.)*

### `core/alpaca/telescope.py` — `Telescope` / `MountPosition`
```
MountPosition(ra, dec, altitude, azimuth, ...) : .ra_str/.dec_str/.alt_str/.az_str
get_position() -> MountPosition ; get_altaz() -> (alt, az)
slew_to(ra, dec) ; abort_slew() ; sync_to(ra, dec) ; set_target(ra, dec)
set_tracking(enabled: bool) ; set_tracking_rate(rate: int) ; get_tracking_rate() -> int|None
move_axis(axis: int, rate: float) ; stop_axis(axis: int) ; pulse_guide(direction, duration_ms)
is_parked() -> bool ; park() ; unpark() ; side_of_pier() -> str|None
```

### `core/alpaca/focuser.py` — `Focuser`
```
get_position() -> int ; is_moving() -> bool ; get_temperature() -> float|None
move_to(position: int) ; step(delta: int) -> int ; halt()
```

### `core/alpaca/filterwheel.py` — `FilterWheel`
```
get_position() -> int ; set_position(position: int) ; position_name() -> str
# constante module: POSITION_NAMES
```

### `core/imaging/debayer.py`
```
extract_channel(arr, channel: str) -> np.ndarray   # 'R'|'G'|'B'|'L'... (GRBG)
compute_hfd(arr, search_radius: int = 32) -> float|None
```

### `core/imaging/fits_writer.py`
```
FITSWriter.write(arr, path, exposure_start, exposure_end, exposure_time, gain,
                 image_type="Light Frame", context: FrameContext|None=None)
FITSWriter.build_filename(object_name, image_type, exposure_start, exposure_time,
                          filter_name, frame_index) -> str
FITSWriter.session_folder(base_dir: Path, object_name, exposure_start,
                          image_type, filter_name) -> Path
# FrameContext: ra,dec,altitude,azimuth,pier_side,target_ra,target_dec,ccd_temp,
#   egain_driver,offset,readout_mode,object_name,filter_name,observer,
#   site_lat,site_lon,site_elev,software,annotation,sensor_meta
# IMAGE_TYPE_MAP = {'light':'Light Frame','dark':'Dark Frame','flat':'Flat Frame','bias':'Bias Frame'}
```

### `core/config.py` — `Config`
```
Config.load() -> Config ; .save() ; .get(key, default) ; .set(key, value)
.alpaca_host / .alpaca_port / .sessions_path (properties)
# Clés pointées: "alpaca.host", "observer.name", "ui.log_level", ...
```

### Workers existants (réutiliser, ne pas recréer)
```
MountPollingWorker(telescope) : position_updated(MountPosition), error_occurred(str), connection_lost()
LivePreviewWorker(camera, exposure=1.0, gain=80, preview_scale=4)
    : frame_ready(preview, full, start_dt, end_dt), status_updated, error_occurred, finished
    ; .update_settings(exposure, gain, scale=0) ; .stop()
AutofocusWorker(focuser, camera, exposure_s=5.0, gain=80, half_range=2000, num_steps=9)
    : step_done(step,total,pos,hfd), best_found(pos,hfd), error_occurred, finished ; .stop()
StellariumWorker(host="127.0.0.1", port=10001)
    : target_received(ra_h, dec_d), client_count_changed(int), server_started, server_stopped, error_occurred
    ; .configure(host,port) ; .update_mount_position(ra,dec,slewing) ; .stop()
```

### Stellarium core (garder)
```
core/stellarium/protocol.py : GotoMessage, encode_position(ra_h,dec_d,...), decode_goto(buf), find_next_message
core/stellarium/server.py   : StellariumServer(host,port,on_goto,push_interval_s,on_client_count)
                              async start()/stop() ; set_position(ra_h,dec_d,slewing) ; client_count
```

---

## 6. Annexe B — Tokens de thème (`ui/theme.py`, à réutiliser tels quels)

```
ACCENT #58a6ff · SUCCESS #3fb950 · WARNING #f0883e · DANGER #f85149
SURFACE_1 #0d1117 · SURFACE_2 #161b22 · SURFACE_3 #21262d · SURFACE_4 #30363d
TEXT_PRIMARY #e6edf3 · TEXT_MUTED #8b949e
# get_stylesheet() applique la feuille globale ; design.py fournit les cards.
```

---

## 7. Notes & risques

- **Préreq matériel** (cf. `handoff.md`) : alignement initial via l'app native Seestar
  obligatoire avant tout slew ; sinon `slew_to` échoue/pointe à côté. À rappeler dans l'UI.
- **Tests** : `core/imaging/sequencer.py` doit avoir des tests unitaires (sans Qt). Le reste
  se teste avec le simulateur ASCOM (`localhost:32323`).
- **Dette corrigée** : le séquençage repart dans `core/` (WU-G), conforme à CLAUDE.md.
- **Roadmap CLAUDE.md §11** : à mettre à jour (Phase 4/5 marquées non faites alors qu'elles
  le sont) — tâche annexe.

---

## Sources (références consultées)

- NINA — Imaging tab : https://nighttime-imaging.eu/docs/master/site/tabs/imaging/
- NINA — Focusing (HFR/autofocus) : https://nighttime-imaging.eu/docs/master/site/quickstart/focusing/
- Stellarium — Telescope Control plugin : https://stellarium.org/doc/25.0/group__telescopeControl.html
- Stellarium TelescopeControl source : https://github.com/Stellarium/stellarium/blob/master/plugins/TelescopeControl/src/TelescopeControl.cpp
- SharpCap — Focus assistance : https://www.sharpcap.co.uk/sharpcap/features/focus-assistance
- APT — Bahtinov aid (réf. focus, hors v1) : https://astrophotography.app/usersguide/bahtinov_aid.htm
