# Identifier un champ résolu

Argos distingue la **résolution astrométrique** (la relation fiable entre
coordonnées de l'image et ICRS) de l'**identification catalogue** (ce que sont
les objets à ces coordonnées). Une couche d'information ne modifie jamais le
FITS, les mesures de photométrie ou les étoiles retenues pour une séquence.

## Utilisation

1. Ouvrir une image ou attendre le prévisualisation live, puis choisir
   **Field → Identify field**.
2. Les couches disponibles apparaissent sous l'image avec le nombre de
   résultats du champ. Elles restent cliquables même lorsque ce nombre vaut
   zéro. Elles peuvent être affichées ou masquées indépendamment.
3. Cliquer un marqueur pour consulter ses coordonnées, sa provenance et les
   magnitudes disponibles (Gaia G/BP/RP, bandes VSP, ou magnitudes NASA selon
   la source). Les rôles Target, Comparison et Check restent des choix
   explicites de l'observateur.
4. La première ligne est organisée par nature physique: **Stars**,
   **Variables**, **Galaxies**, **Nebulae + clusters**, **Exoplanets** et
   **Other objects**. La seconde regroupe la grille, les étoiles de référence,
   la sélection de session et les labels. **Labels** reste désactivé par défaut
   et applique un placement anti-chevauchement.
5. Déplacer **Gaia G limit** pour filtrer instantanément les étoiles Gaia déjà
   en cache. Utiliser **Catalogues / depth…** pour régler profondeur,
   fournisseurs réseau et budget de requête sans refaire la résolution.
6. Cliquer une étoile non marquée lance une identification ponctuelle dans un
   cône de 10″. Argos choisit la source Gaia la plus proche puis n'ajoute le
   nom/type SIMBAD que si les positions concordent à moins de 3″. Le résultat
   est mis en cache et ajouté au champ courant; sans correspondance fiable, la
   fiche reste explicitement une mesure manuelle.

## Couches actuelles

| Couche | Contenu | Réseau | Rôle scientifique |
| --- | --- | --- | --- |
| Grid | grille RA/Dec issue de la WCS ASTAP | non après la résolution | contrôler le repérage sur l'image |
| Stars | Gaia DR3 enrichi des identités stellaires SIMBAD | cache, puis Gaia/SIMBAD si nécessaire | identifier les étoiles ordinaires; pas une calibration photométrique |
| Variables | AAVSO VSX | cache, puis AAVSO | trouver des variables connues et les filtrer par type ou magnitude |
| Galaxies | types physiques SIMBAD + catalogue essentiel local | cache/réseau et local | regrouper les galaxies quelle que soit la base qui fournit leur identité |
| Nebulae + clusters | types physiques SIMBAD + catalogue essentiel local | cache/réseau et local | reconnaître nébuleuses et amas sans mélanger fournisseur et type d'objet |
| Exoplanet hosts | hôtes confirmés de NASA Exoplanet Archive | cache, puis NASA si autorisé | savoir si un hôte connu est dans le champ; les éphémérides détaillées restent la préparation d'une cible |
| Other objects | autres types physiques SIMBAD (radio, rayons X, etc.) | cache, puis SIMBAD | conserver l'accès aux identités spécialisées sans encombrer les catégories principales |
| VSP references | AAVSO VSP | cache, puis AAVSO | repérer des références calibrées candidates; l'ensemble final doit être validé |
| Selected stars | Target, Comparison et Check de la session | non | montrer exactement les objets utilisés par Argos |

## Filtres et profondeur

Les boutons de couche règlent seulement l'affichage. Les critères de contenu
restent dans **Catalogues / depth…** afin que la barre au-dessus de l'image reste
lisible.

- **VSX faint-end magnitude** et **Maximum VSX variables**: rendent une liste
  dense exploitable. Le tableau Variables et les cercles image utilisent le
  même filtre.
- **Gaia G limit**, directement sous l'image, est la limite d'affichage des
  étoiles Gaia en bande G. Elle ne filtre pas une galaxie en magnitude intégrée
  J/K: ces valeurs ne sont pas scientifiquement interchangeables. La fiche
  conserve et nomme chaque bande disponible.
- **Gaia cache depth**: `Bright` (G ≤ 15), `Standard` (G ≤ 18) ou `Deep`
  (G ≤ 20).
  C'est la profondeur téléchargée; le curseur de l'image ne peut naturellement
  pas révéler des sources plus faibles que ce cache.
- **Field identification budget**: 100, 200, 400, 800 ou 1 600 objets. Ce
  plafond est partagé entre Gaia (socle stellaire) et SIMBAD (noms et types).
  Un budget de 200/400 accélère nettement un champ dense. Atteindre le plafond
  signifie que la liste est limitée, pas qu'elle est complète jusqu'à G=18.
- **Only draw Gaia sources with a local image detection**: désactivé par
  défaut. Après une bonne WCS, c'est la coordonnée Gaia qui doit commander
  l'annotation; l'activer est un moyen de désencombrer une prévisualisation
  très bruitée, pas une validation d'identité.
- Les recherches SIMBAD et NASA peuvent être activées ou désactivées
  séparément. Les désactiver maintient un mode strictement cache-only.

## Catalogues, cache et confidentialité

Dans **Settings → Catalogues · data**, chaque cache possède un chemin visible
et modifiable ainsi qu'un bouton **Refresh**. Refresh efface uniquement la
copie locale: rien n'est téléchargé immédiatement. La prochaine recherche
correspondante récupérera une réponse récente si une connexion est disponible.
Les chemins couvrent CDS/SIMBAD, NASA, AAVSO et Gaia. Le catalogue
Messier/NGC/IC est versionné dans l'application et est en lecture seule.

Argos ne transmet aucune télémétrie. Quand l'observateur choisit **Field →
Identify field**, Argos consulte d'abord le cache puis, si les options sont
autorisées, interroge SIMBAD et NASA pour ce seul cône céleste. Le mode
cache-only est disponible dans **Catalogues / depth…**. Toute fiche indique sa
provenance; le logiciel reste utilisable hors-ligne avec les données déjà
enregistrées.

## Évolutions prévues, à ne pas confondre avec les données actuelles

La couverture maximale d'un champ nécessite plusieurs bases; Gaia ne donne pas
à lui seul les noms usuels (HD, HIP, Bayer/Flamsteed), les classifications
SIMBAD ou les objets faibles. L'enrichissement local encore prévu est:

1. un pack local, versionné, de correspondances modernes Gaia ↔ HD/HIP/Tycho
   et noms brillants; les positions historiques HD ne doivent pas être utilisées
   seules pour annoter ou pointer.

Les filtres de type sont désormais distincts des fournisseurs de données.
Chaque entrée doit garder sa source et sa date de récupération dans sa fiche.
Argos ne devra jamais dessiner un marqueur comme « identifié » s'il provient
d'une simple détection locale sans correspondance astrométrique/catalogue.

Pendant une séquence, les catalogues ne sont pas retéléchargés à chaque image.
Le suivi astrométrique reprojette les mêmes identités fiables sur chaque frame
entrante; une nouvelle requête n'est nécessaire qu'après un changement réel de
champ ou de profondeur catalogue.
