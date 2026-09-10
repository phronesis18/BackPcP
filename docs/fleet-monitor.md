# Module « Fleet Monitor » (GPS & Suivi Flotte)

Documentation technique du Module 3, ajouté au projet **Phronesis Capital
Partners** (backend FastAPI + frontend TanStack Start). Correspond aux
Écrans 13-14 du cahier des charges (§5).

> Objectif : donner au back-office une carte flotte temps réel, une fiche
> véhicule détaillée (position, historique, alertes) et le coupe-moteur à
> distance — sans boîtier GPS physique ni serveur Traccar.

---

## 1. Pourquoi une simulation, et comment elle reste honnête

Le cahier des charges suppose du matériel réel (Teltonika/Syrus, protocole
MQTT/TCP vers un serveur Traccar). Rien de tout ça n'est provisionné ici — il
n'y a ni boîtier, ni SIM M2M, ni credential. Plutôt que de figer la carte sur
des coordonnées statiques (ce qu'était `mock-data.ts::vehicules`), la
position/vitesse/moteur de chaque véhicule est calculée par
`app/gps_simulator.py` comme une **fonction pure du temps** :

- Chaque contrat est seedé (`random.Random(f"pcp-fleet-{contrat_id}")`) sur
  un itinéraire réel fixe (Cotonou / Abomey-Calavi / Porto-Novo) et un rythme
  de boucle stable.
- Deux requêtes à la même seconde pour le même véhicule renvoient
  **exactement** la même position (pas de flicker) ; deux requêtes à des
  instants différents montrent une progression continue et cohérente le long
  de la route.
- Rien n'est stocké en base pour la position — aucune tâche planifiée,
  aucun risque de dérive entre ce que montre l'écran et ce que la base
  contient.

La seule chose qui **est** un vrai état persisté est `Contrat.cutoff_active`
— parce que c'est une vraie commande avec une portée légale (le cahier des
charges exige « log horodaté + identifiant admin déclencheur obligatoire »).
Elle est actionnée via `/vehicules/{id}/cutoff` / `/restore` et journalisée
dans la table `Relance` (**partagée avec le module Recouvrement** — un
coupe-moteur déclenché automatiquement par le Recover Bot à J+30 apparaît
donc identiquement dans Fleet Monitor et dans l'écran Recouvrement, une
seule source de vérité).

| Donnée affichée | Statut |
|---|---|
| Position, vitesse, moteur, historique de trajets, alertes GPS | **Simulées**, fonction pure et déterministe du temps |
| Statut couleur (normal/alerte/coupé) | **Réel** — dérivé du retard de paiement réel et de `cutoff_active` |
| Coupe-moteur / réactivation | **Réel**, persisté et audité (`Relance`) |
| Plaque, identifiant boîtier GPS | Générés une fois, déterministement, à la signature du contrat |

---

## 2. Backend

### 2.1 Modèles (`backend/app/models.py`)

- `Contrat.plate`, `Contrat.gps_device_id`, `Contrat.cutoff_active` (voir
  aussi `docs/recouvrement.md` pour `Relance`, réutilisée ici).
- Schémas : `PositionPublic`, `VehiculePublic` (liste), `VehiculeDetailPublic`
  (détail, ajoute `gps_device_id` + `StatsDuJourPublic`), `TrajetPublic`,
  `AlertePublic`, `FleetStatsPublic`.

### 2.2 Simulation (`backend/app/gps_simulator.py`)

| Fonction | Rôle |
|---|---|
| `simulate_telemetry(contrat_id, now, cutoff_active, cutoff_since)` | Position/vitesse/moteur actuels ; si `cutoff_active`, fige la position au moment de la coupure |
| `simulate_historique(contrat_id, now)` | 5 derniers trajets plausibles, stables pour une journée donnée |
| `simulate_alertes(contrat_id, now)` | 0-2 alertes matérielles plausibles (vitesse, conduite de nuit, sortie de zone), stables par véhicule |
| `simulate_stats_du_jour` / `simulate_semaine` | Agrégats jour/semaine pour la fiche véhicule et l'écran Statistiques |
| `generate_plate` / `generate_gps_device_id` | Identité véhicule générée une fois, à la signature du contrat |

### 2.3 Composition (`backend/app/contrats_service.py`)

`to_vehicule_public` / `to_vehicule_detail_public` combinent le retard réel
(`build_context`, voir `docs/recouvrement.md`) avec la télémétrie simulée
pour produire le statut couleur (`normal|alerte|coupe`) et la position.

### 2.4 Routes API (`backend/app/api/routes/vehicules.py`)

Préfixe `/api/v1/vehicules`, accès back-office uniquement (`is_admin` ou
`is_superuser` — c'est la même règle que `canAccessArea(user, "fleet")` côté
front).

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/vehicules` | Flotte complète + télémétrie live |
| `GET` | `/vehicules/stats` | Agrégats flotte (distance, trajets, vitesse moyenne, disponibilité GPS) — **déclaré avant** `/{contrat_id}` pour éviter que FastAPI ne tente de parser `stats` comme un UUID |
| `GET` | `/vehicules/{id}` | Détail + stats du jour + boîtier GPS |
| `GET` | `/vehicules/{id}/historique` | Trajets récents |
| `GET` | `/vehicules/{id}/alertes` | Alertes GPS |
| `POST` | `/vehicules/{id}/cutoff` | Coupe-moteur (journalisé, admin obligatoire) |
| `POST` | `/vehicules/{id}/restore` | Réactivation (journalisée) |

### 2.5 Migration Alembic

`d4e5f6a7b8c9_add_gps_and_cutoff_to_contrat.py` — voir `docs/recouvrement.md`.

---

## 3. Frontend (`FrontPcp`)

- `src/lib/endpoints.ts::fleetAPI`, `src/hooks/useFleet.ts` (React Query,
  `refetchInterval` court sur la liste pour un effet « temps réel » sans
  websocket — même pattern que `useDemandes.ts::UNREAD_POLL_INTERVAL_MS`).
- `src/routes/fleet.index.tsx` : carte SVG maison (déjà en place, bornes
  Cotonou/Abomey-Calavi/Porto-Novo) branchée sur `useVehicules()` au lieu de
  `mock-data.ts`.
- `src/routes/fleet.liste.tsx`, `fleet.$id.tsx`, `fleet.alertes.tsx`,
  `fleet.stats.tsx` : mêmes composants, données réelles ; l'onglet
  « Commande à distance » de `fleet.$id.tsx` appelle les vraies mutations
  cutoff/restore.
- `src/lib/mock-data.ts::vehicules` : supprimé une fois les 5 routes
  migrées (plus aucune référence).

---

## 4. Comment étendre

- **Vraie intégration GPS** : remplacer les appels à `gps_simulator` dans
  `contrats_service.py` par une lecture depuis Traccar/MQTT, en gardant le
  même contrat de schémas (`VehiculePublic`, etc.) — le frontend n'a rien à
  changer.
- **Carte avec tuiles réelles** : si Leaflet + OpenStreetMap est ajouté plus
  tard, seul `fleet.index.tsx` change ; les routes GPS restent identiques.
- **Geofencing réel** : ajouter une zone (polygone Bénin) et comparer la
  position simulée/réelle dans `simulate_alertes` ou son équivalent matériel.
