# Architecture des interactions — Argos 0.4.1

## Principe directeur

L'interface doit parler du travail astronomique effectué, jamais de
l'organisation interne du logiciel. Un observateur doit pouvoir répondre à
trois questions sans connaître Argos : **que veux-je faire maintenant ?**,
**de quelle mesure ai-je besoin ?**, et **quelle action est sûre ensuite ?**.

Les termes scientifiques sont conservés lorsqu'ils désignent une quantité ou
une opération précise (FWHM, HFD, WCS, photométrie différentielle). Au premier
emploi dans l'interface, l'intitulé développé ou une infobulle donne le sens du
sigle ; un terme de développement tel que « dock », « solve », « display » ou
« history » ne doit jamais être la seule indication visible.

## Parcours de la nuit

```text
Ce soir (connexion) → Acquisition et cadrage → Mise au point
       → Identification astrométrique du champ → Sélection de cible/comparaisons
       → Séquence d'acquisition → Photométrie et contrôle qualité → Analyse
```

Chaque étape conserve les informations utiles à la suivante :

| Étape | Produit | Utilisé par |
|---|---|---|
| Connexion | capacités de caméra, roue à filtres, monture, focuser | Acquisition, Mise au point, Séquence |
| Acquisition | image FITS, filtre, gain, temps de pose, objet | Identification du champ, photométrie, sauvegarde |
| Mise au point | HFD/FWHM, position focuser, courbe en V | contrôle de qualité, séquence avec autofocus |
| Identification du champ | WCS, centre, échelle | grille RA/Dec, catalogue, rôle des étoiles |
| Rôles photométriques | cible, comparaisons, étoiles de contrôle | photométrie différentielle, export |
| Séquence | séries de poses, répertoire de session | photométrie en direct, analyse de session |
| Diagnostics | statistiques d'image, tendance HFD, journal | décision de recadrer, refaire la mise au point, ou poursuivre |

## Inventaire des surfaces de contrôle

| Surface actuelle | But réel | Libellé UI retenu | Placement par défaut | Relation principale |
|---|---|---|---|---|
| Camera | exposer une image ou le flux de prévisualisation | **Acquisition** | droite | produit l'image et ses métadonnées |
| Mount | pointer, synchroniser, suivre, parquer | **Télescope** | droite | fournit la position et le suivi |
| Focuser | déplacer le focuser et lancer l'autofocus | **Mise au point** | droite | utilise HFD/FWHM de l'image |
| Display | étirement, rotation, aides visuelles et mesure de région | **Affichage de l'image** | à la demande | ne modifie jamais le FITS ni les mesures |
| Statistics | statistiques de pixels et d'étoiles de l'image courante | **Statistiques d'image** | diagnostic, masqué au départ | contrôle de qualité de l'acquisition |
| HFD History | tendance HFD et nombre d'étoiles au fil des images | **Diagnostic de mise au point** | diagnostic, masqué au départ | indique dérive de focus/nuages |
| Log | événements et erreurs de la session | **Journal d'activité** | bas | explique l'état des instruments et des tâches |
| Light curve | courbes cible, comparaisons et incertitudes | **Photométrie différentielle** | bas, à la demande | consomme les rôles + les images sauvegardées |
| Sequencer | plan de séries, répétitions, autofocus et arrêt | **Séquence d'acquisition** | espace Plan, puis dock optionnel | pilote Acquisition, sauvegarde et photométrie |

## Règles de la barre du cockpit

La barre ne contient que les cinq surfaces utilisées pendant le cadrage :
**Acquisition**, **Télescope**, **Mise au point**, **Affichage de l'image** et
**Photométrie**. Les trois lectures secondaires — Journal d'activité,
Statistiques d'image et Diagnostic de mise au point — vivent dans le menu
**Panneaux**. Le journal reste ouvert par défaut au bas du cockpit.

Le bouton **Organiser les panneaux** reste toujours présent : déplacer,
tabuler, ancrer et détacher les panneaux est une capacité centrale, pas une
préférence cachée. Les libellés de ce menu reprennent les noms scientifiques
ci-dessus.

## Contrats de libellés

| À éviter | À employer | Justification |
|---|---|---|
| Solve / plate solve | Identifier le champ | décrit le résultat ; ASTAP reste cité dans l'infobulle |
| Display | Affichage de l'image | indique que les données scientifiques ne changent pas |
| Statistics | Statistiques d'image | précise l'objet mesuré |
| HFD History | Diagnostic de mise au point | l'objectif est lisible ; HFD est développé en infobulle |
| Light curve | Photométrie différentielle | nomme la mesure plutôt que son seul graphique |
| Log | Journal d'activité | comprend les actions, états et erreurs |

## Critères d'acceptation UI

1. Un utilisateur débutant retrouve Acquisition, Télescope et Mise au point
   sans ouvrir de menu secondaire.
2. Toute quantité scientifique abrégée possède une unité et une infobulle au
   premier point d'accès.
3. Une commande de présentation ne peut pas être confondue avec une commande
   qui modifie l'acquisition ou les données.
4. Les panneaux diagnostic restent disponibles et librement ancrables, sans
   encombrer l'espace de travail initial.
5. Aucun changement de terminologie ne modifie les clés de sauvegarde, FITS,
   CSV ou API internes.
