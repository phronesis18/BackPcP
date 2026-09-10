# Module « Dashboard Investisseur »

Documentation technique du Module 4, ajouté au projet **Phronesis Capital
Partners** (backend FastAPI + frontend TanStack Start). Correspond à
l'écran du cahier des charges §6.

> Objectif : donner à un utilisateur investisseur une vue en lecture seule
> de la performance du fonds — sans inventer de TRI ni de rendement fictif.

---

## 1. Principe : rien n'est inventé, tout est dérivé des contrats réels

La maquette d'origine (`investisseur.tsx`) affichait un TRI, un rendement
annualisé et un historique de distributions 100 % en dur. Il n'y a pas de
vrai cap-table LP ni de moteur de calcul actuariel dans ce projet — plutôt
que fabriquer ces chiffres, `GET /investissements/performance` les calcule
depuis les contrats réellement signés :

| KPI affiché | Calcul |
|---|---|
| Encours total | Somme des échéances (`Paiement`) non payées de tous les contrats actifs |
| Contrats actifs | Nombre de contrats avec au moins une échéance non payée |
| Taux d'impayés | % de contrats actuellement en retard (voir `docs/recouvrement.md`) |
| TEG moyen pondéré | Moyenne des `Demande.taux_teg`, pondérée par le prix véhicule |
| Évolution de l'encours | Capital engagé cumulé (somme des `prix_vehicule`), par mois de signature, sur les 6 derniers mois |
| Répartition par marque | Comptage réel des contrats actifs par `Demande.marque` |

Les seules données qui ne peuvent pas être dérivées des contrats — le
**montant investi par chaque LP** et **les distributions versées** — sont
des saisies admin explicites (`User.capital_investi`, table `Distribution`),
pas des calculs.

Si `capital_investi` n'est pas renseigné pour un investisseur, l'écran
affiche un état vide (« contactez l'administrateur ») plutôt qu'un chiffre
inventé — `mon_investissement`, `part_du_fonds_pct` et
`mes_dividendes_recus` sont `null` dans ce cas.

---

## 2. Backend

### 2.1 Modèles (`backend/app/models.py`)

- `User.capital_investi` (`int | None`) : montant engagé par l'investisseur,
  en XOF. Réutilise `UserUpdate`/`UserPublic` existants (hérite de
  `UserBase`), donc modifiable via `PATCH /users/{id}` sans nouvelle route.
- **`Distribution`** (table) : `periode`, `montant_total`, `statut`
  (`prevue|versee`), `date_versement`.
- `InvestissementPerformancePublic` : KPIs + `evolution` (liste
  `{mois, encours}`) + `repartition_marque` (liste `{marque, count, pct}`) +
  champs personnels (`mon_investissement`, `part_du_fonds_pct`,
  `mes_dividendes_recus`, `prochain_versement`).

### 2.2 Agrégation (`backend/app/api/routes/investissements.py`)

`GET /performance` boucle une fois sur `crud.get_contrats()`, appelle
`contrats_service.build_context(..., reconcile=False)` pour chaque contrat
(lecture seule — consulter son dashboard ne doit pas déclencher de relances
admin) et agrège les KPIs ci-dessus. `part_du_fonds_pct` et
`mes_dividendes_recus` sont calculés au prorata de
`capital_investi / somme(capital_investi de tous les investisseurs)`
(`crud.get_investisseurs_total_capital`).

### 2.3 Routes API

Préfixe `/api/v1/investissements`.

| Méthode | Endpoint | Accès | Description |
|---|---|---|---|
| `GET` | `/performance` | investisseur ou back-office | KPIs du fonds + position personnelle |
| `GET` | `/distributions` | investisseur ou back-office | Historique des distributions |
| `POST` | `/distributions` | back-office | Ajoute une distribution (prévue ou versée) |
| `PATCH` | `/distributions/{id}` | back-office | Modifie une distribution (ex. passer `prevue → versee`) |

### 2.4 Migration Alembic

`f6a7b8c9d0e1_add_capital_investi_and_distribution.py`.

---

## 3. Frontend (`FrontPcp`)

- `src/lib/endpoints.ts::investissementAPI`, `src/hooks/useInvestisseur.ts`
  (React Query : `usePerformance`, `useDistributions`).
- `src/routes/investisseur.tsx` : KPIs, graphique d'évolution et répartition
  par marque (recharts, déjà en place) branchés sur `usePerformance()` ; état
  vide propre si `mon_investissement` est `null`.
- `src/routes/admin.utilisateurs.tsx` / `admin.utilisateurs.nouveau.tsx` :
  champ « Capital investi » visible quand le rôle sélectionné est
  `investisseur`.
- `src/routes/admin.parametres.tsx` : section « Distributions du fonds »
  (liste + formulaire d'ajout, réservée au back-office).

---

## 4. Comment étendre

- **Multi-fonds** : aujourd'hui un seul fonds implicite (tous les contrats).
  Pour plusieurs fonds, ajouter un `fonds_id` sur `Contrat` et filtrer
  l'agrégation par fonds ; `User.capital_investi` deviendrait une table
  `Investissement(user_id, fonds_id, montant)`.
- **Vrai TRI** : nécessiterait un historique de flux de trésorerie daté
  (appels de capital + distributions), pas seulement l'état courant —
  actuellement hors scope, volontairement.
- **Reporting PDF** : brancher un générateur (ex. WeasyPrint) sur les mêmes
  données que `/performance`, pour garder une seule source de vérité entre
  l'écran et le PDF.
