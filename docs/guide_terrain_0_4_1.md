# Guide de terrain — Argos 0.4.1

> **Statut : alpha de validation terrain.** Ce guide décrit le parcours à
> utiliser pour les essais. Conserver les FITS bruts et ne pas considérer une
> courbe Argos comme publiable sans réduction et contrôle indépendants.

## 1. Ce qui a changé dans 0.4.1

| Domaine | Nouveauté utile sur le terrain |
|---|---|
| Connexion | Un seul réglage clair : **adresse IP Alpaca + port**. `Discover` recherche le Seestar et mémorise la dernière adresse. |
| Télescope | Le modèle est choisi dans **Connection**. S30 Pro est le profil de référence ; S30 et S50 sont signalés *unvalidated*. |
| Site | **Settings** peut chercher un lieu, récupérer latitude/longitude/altitude de terrain, et enregistrer des sites favoris. |
| Planification | Recherche d'objets (`M 42`, `NGC 7000`, `HD 189733`…), aperçu d'altitude et séquence multi-étapes dans des panneaux déplaçables. |
| Acquisition | Les panneaux de Capture sont de vrais docks : on peut les déplacer, redimensionner, empiler ou détacher sur un second écran. |
| Astrométrie | ASTAP et son dossier de bases stellaires sont configurables explicitement dans **Settings**. |
| Photométrie | Courbe cible/check séparée des diagnostics des comparaisons ; incertitudes par image ; export CSV de toutes les mesures. |
| Informations d'étoile | Cliquer une étoile affiche identité catalogue, coordonnées et mesures ; la carte est déplaçable et redimensionnable. |
| Données | Sessions compatibles Siril, `session.json` et télémétrie JSONL par image. |

## 2. Préparation à domicile

1. Dans **Settings → Observer & Site**, renseigner le nom de l'observateur et,
   si nécessaire, le code AAVSO. Rechercher le lieu, choisir le bon résultat,
   puis corriger l'altitude si l'observatoire a une altitude mesurée. Sauvegarder
   le site en favori.
2. Dans **Settings → Telescope**, sélectionner le matériel réellement utilisé.
   Ne pas faire de photométrie de précision avec le S30 ou le S50 tant que leurs
   paramètres ne sont pas validés sur le terrain.
3. Dans **Settings → Paths**, choisir le dossier racine des sessions. C'est là
   que seront écrits les FITS, le journal de session et les mesures.
4. Dans **Settings → Astrometry**, vérifier que l'exécutable ASTAP est détecté.
   Renseigner **Database folder** si la base stellaire n'est pas dans un chemin
   détecté automatiquement. Le statut doit confirmer ASTAP **et** la base.
5. Dans **Settings → Data & telemetry**, laisser la télémétrie activée pour les
   essais. Elle aidera à expliquer une courbe dégradée.
6. Pendant que l'accès internet est disponible, rechercher les objets prévus et
   résoudre/consulter les champs nécessaires : les recherches de catalogue sont
   alors réutilisables depuis le cache au terrain.

## 3. Déroulé d'une soirée

### 3.1 Connection

1. Choisir le télescope dans **Telescope & equipment**.
2. Entrer l'**adresse IP** du Seestar et le port Alpaca (habituellement
   `32323`), ou appuyer sur **Discover**. En mode point d'accès Seestar,
   l'adresse est normalement `10.0.0.1`.
3. Appuyer sur **Connect equipment**. Les quatre états Telescope, Camera,
   Filter Wheel et Focuser doivent devenir *Ready*.
4. Le bouton **Show connection and device details** donne accès aux contrôles
   individuels et au serveur Stellarium si un diagnostic est nécessaire.

Voir aussi [la documentation de connectivité](field_connectivity.md) pour les
réseaux Seestar, partage de connexion et usage hors ligne.

### 3.2 Plan

L'espace **Plan** sépare volontairement la recherche, les paramètres du plan,
l'altitude, les préréglages et les commandes d'exécution. Les panneaux peuvent
être déplacés, redimensionnés, empilés ou flottés ; le tableau des étapes reste
au centre.

1. Dans **Target search**, chercher par désignation. La recherche passe par CDS
   Sesame et accepte notamment Messier, NGC, IC, HD et de nombreux noms usuels.
   Elle demande internet au premier usage, puis garde le résultat en cache.
2. Le résultat remplit le nom et les coordonnées du plan. Il **n'effectue pas
   automatiquement un GoTo** : vérifier la cible et commander le pointage dans
   le panneau Telescope de Capture ou par Stellarium.
3. **Target visibility** trace l'altitude pendant la prochaine nuit locale ; la
   ligne pointillée correspond à 30°. Ce calcul dépend du site configuré.
4. Construire les étapes dans le tableau : type (Light/Dark/Flat/Bias), filtre,
   exposition, gain, nombre d'images et intervalle. Le temps estimé est une
   estimation ; prévoir une marge pour les téléchargements et l'autofocus.
5. **Plan settings** permet les répétitions, la cadence d'autofocus, l'action de
   fin et le nom d'objet. **Presets** enregistre/recharge un plan JSON.
6. Lancer avec **Start sequence**. Pause termine l'image en cours puis bloque la
   suivante ; Stop interrompt la suite. La progression reste visible en haut et
   les images/courbes restent dans **Observe**.

### 3.3 Observe

**Observe** est le poste de travail de la séance. Les panneaux Camera,
Telescope, Focuser, Filters, Histogram, Statistics, Focus diagnostics, Log et
Light curve sont des docks. Les déplacer par leur barre de titre ; les détacher
sur un autre écran si souhaité. **View → Reset Window Layout** restaure la mise
en page au prochain démarrage.

- **File → Open FITS image…** ouvre une image existante pour inspection et
  identification de champ ; il ne faut plus chercher cette fonction dans un
  ancien bouton de Capture.
- **Field → Identify field** résout l'image courante. Les options ASTAP et les
  catalogues sont regroupés sous le menu **Field**.
- Dans le panneau Telescope, faire le GoTo seulement après avoir vérifié le nom,
  les coordonnées et la cible prévue. Le pointage Stellarium reste une méthode
  normale et complémentaire.
- La barre de contexte sous l'image montre le nom de la frame et l'avancement
  utile de la séance ; les statistiques détaillées sont dans leur panneau, pas
  dans la zone d'image.

## 4. Photométrie et carte d'information d'étoile

Après une identification de champ, cliquer une étoile dans l'image.

La carte affiche, lorsque l'information est disponible, le nom catalogue, les
coordonnées RA/Dec, magnitude(s), FWHM, HFD, SNR et saturation. Elle se déplace
en faisant glisser son titre et se redimensionne par son coin inférieur droit.

| Bouton | Sens scientifique |
|---|---|
| **Target** | Étoile variable/cible dont la magnitude différentielle est mesurée. |
| **Comparison star** | Étoile de référence qui construit le zéro-point de l'ensemble. |
| **Check star** | Étoile supposée constante, mesurée contre l'ensemble pour contrôler sa stabilité. |
| **Remove** | Retire cette étoile de l'ensemble sauvegardé. |
| **Dismiss** | Ferme seulement la carte ; les rôles déjà définis sont conservés. |

Le bouton **Check star** ne « vérifie » pas la mise au point : il attribue le
rôle scientifique d'étoile de contrôle. Les boutons de rôle restent désactivés
tant que le champ n'a pas été résolu et que l'étoile ne possède pas de
coordonnées fiables.

Flux recommandé : résoudre le champ, choisir une cible, laisser Argos proposer
des comparaisons ou les choisir explicitement, puis ajouter une étoile de
contrôle. La configuration par défaut demande au moins deux comparaisons ; une
mesure avec moins de comparaisons est signalée comme fragile.

La fenêtre **Photometry** contient :

- **Light curve** : cible et étoile de contrôle sur le graphe scientifique ;
  comparaisons dans leur propre graphe de diagnostics, centrées sur leur médiane.
  La case **Show uncertainties** montre/cache les barres d'incertitude sans
  modifier les données.
- **Metrics** : état de la séance (qualité de champ, fond, etc.).
- **Targets** et **Comparisons** : ensemble actuellement utilisé.
- **Export measurements…** : CSV de la cible, contrôle et comparaisons ; ce
  format conserve les rôles et peut être rouvert dans **Review**.
- **Export target (AAVSO)…** : cible(s) scientifique(s) uniquement. Les courbes
  de comparaison sont des diagnostics et ne doivent pas devenir des observations
  AAVSO.

Les incertitudes de la courbe en direct combinent l'erreur formelle de la mesure
et un plancher systématique de séance compatible avec `star_var_script`. Cette
courbe reste une **prévisualisation** : les bruts ne sont ni dark/flat/bias
calibrés ni transformés en BJD_TDB par Argos.

## 5. Données produites

Une séquence est organisée pour Siril sous le dossier de sessions configuré :

```text
<sessions>/
└── <date>_<objet>/
    ├── Lights/
    ├── Darks/
    ├── Flats/
    ├── Bias/
    ├── session.json
    └── diagnostics/
```

Les mesures en direct et les jeux de cibles sont également conservés sous
`<sessions>/targets/`. Garder ensemble les FITS bruts, `session.json`, les CSV
et les fichiers `*_diagnostics.jsonl` quand une observation est rapportée.

Dans **Review**, ouvrir un CSV de session pour revoir/exporter la courbe, ou
**Inspect a frame…** pour étudier un FITS individuel. Renseigner le code AAVSO
dans Settings avant un export ; `XXX` indique qu'il manque.

## 6. Checklist de test terrain

| Test | Résultat attendu | À noter en cas d'écart |
|---|---|---|
| Démarrage | fenêtre visible, pas d'erreur, bonne version | macOS/Linux, version et message exact |
| Connexion | les quatre appareils passent Ready | IP, réseau et appareil qui échoue |
| GoTo + position | cible cohérente dans l'image | objet, coordonnées demandées/obtenues |
| Résolution ASTAP | centre, échelle et grille plausibles | durée, message ASTAP, dossier de base |
| Recherche catalogue | objet trouvé ou réponse claire | requête, réseau ou cache utilisé |
| Séquence Light | compteur et fichiers progressent | étape, nombre attendu/écrit, log |
| Darks/Flats/Bias | fichiers dans le bon dossier | type, filtre, exposition et chemin |
| Photométrie | cible, comps et check produisent les courbes attendues | captures, CSV, diagnostics et anomalie |
| Déplacement de docks | mise en page conservée après relance | panneau concerné, disposition attendue |
| Incident volontaire | arrêt propre lors de perte réseau/ASTAP | action, heure, log et fichiers restants |

Pour un retour exploitable, joindre si possible : version Argos, modèle de
Seestar, macOS/Linux, réseau, log Argos, `session.json`, le CSV, un ou deux FITS
bruts et une capture de l'écran. Ne pas envoyer seulement une image étirée : le
FITS brut et le contexte de séance sont indispensables.

## 7. Aide et limites

- **More → Documentation & website** ouvre les ressources en ligne ;
  **More → About & credits** donne version, licence et crédits.
- Le S30 Pro est le profil de référence. S30 et S50 restent des profils de test
  pour la photométrie de précision.
- La météo, la sécurité d'observatoire et la récupération automatique après un
  redémarrage ne sont pas des fonctions d'exploitation autonome : rester
  présent pendant une séance.
- ASTAP, ses bases stellaires et les catalogues distants restent des dépendances
  externes. Les pannes doivent être signalées avec leur message exact.
