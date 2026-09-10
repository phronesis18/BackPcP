# Module « Recover Bot » (Recouvrement)

Documentation technique du module de recouvrement automatique, ajouté au
projet **Phronesis Capital Partners** (backend FastAPI + frontend TanStack
Start). Correspond à l'Écran 12 du cahier des charges (§4.5).

> Objectif : détecter les échéances impayées en temps réel et déclencher
> automatiquement la séquence de relance (SMS → WhatsApp → appel →
> coupe-moteur) sans tâche planifiée (cron), en gardant une trace horodatée
> et attribuable de chaque action.

Il n'existe aucune intégration réelle MTN MoMo / Moov Africa / SMS gateway
dans ce projet — voir « Ce qui est simulé » ci-dessous.

---

## 1. Architecture & relations

```
┌──────────┐ 1   1 ┌──────────┐ 1      * ┌────────────┐
│ Demande  │───────▶│ Contrat  │──────────▶│ Paiement  │  (une ligne / échéance)
└──────────┘       └──────────┘          └────────────┘
                          │ 1
                          │
                          ▼ *
                     ┌──────────┐
                     │ Relance  │  (log d'actions, auto ou manuel)
                     └──────────┘
```

| Relation | Cardinalité | Clé étrangère | Suppression |
|-----------|-------------|---------------|-------------|
| `Contrat` → `Paiement` | 1 → * | `paiement.contrat_id → contrat.id` | `ON DELETE CASCADE` |
| `Contrat` → `Relance` | 1 → * | `relance.contrat_id → contrat.id` | `ON DELETE CASCADE` |
| `User` → `Relance` | 1 → * (optionnel) | `relance.created_by → user.id` | `ON DELETE SET NULL` |

---

## 2. Le concept clé : l'« épisode de retard »

Un **épisode de retard** est ancré sur la date d'échéance de la **plus
ancienne mensualité impayée** d'un contrat (`recouvrement.oldest_unpaid`).
Tant que cette échéance n'est pas payée, c'est le même épisode : les phases
déjà déclenchées ne repartent jamais de zéro. Dès qu'elle est payée,
l'épisode suivant (s'il y en a un) redémarre à J+0.

Le nombre de jours de retard (`jours_retard`) et la phase courante
(`phase_courante`) sont **toujours recalculés à la volée** — rien n'est mis
en cache côté retard/phase, seule la trace des actions (`Relance`) est
persistée.

### Seuils (`app/recouvrement.py::PHASES`)

| Phase | Canal | Seuil |
|-------|-------|-------|
| 1 | SMS automatique | J+3 |
| 2 | WhatsApp | J+7 |
| 3 | Appel agent | J+15 |
| 4 | Coupe-moteur | J+30 |

---

## 3. Le rattrapage sans cron : `ensure_relance_backlog`

Il n'y a pas de tâche planifiée dans ce projet. À la place,
`app.recouvrement.ensure_relance_backlog(session, contrat, paiements)` est
appelée **à chaque lecture** d'un dossier (`GET /recouvrement/dossiers`,
`GET /contrats/{id}`, `GET /vehicules`...) et fait deux choses,
idempotentes :

1. Pour chaque seuil de phase franchi par le retard courant, si aucune
   `Relance` de ce canal n'existe déjà **depuis le début de l'épisode**, elle
   en crée une, avec un horodatage **rétroactif** (`episode_start + seuil`) —
   donc peu importe quand l'admin ouvre la page, l'historique reflète les
   dates réelles de déclenchement, pas la date de consultation.
2. Au franchissement de la phase 4, elle active `Contrat.cutoff_active`
   **une seule fois par épisode**. Si l'admin réactive manuellement le
   moteur (`POST /vehicules/{id}/restore`), le bot ne le recoupera pas tant
   que le même épisode de retard est en cours — il faut qu'une nouvelle
   échéance devienne la plus ancienne impayée pour qu'un nouveau cycle
   puisse se déclencher.

---

## 4. Ce qui est simulé vs. ce qui est réel

| Élément | Statut |
|---|---|
| Échéancier (`Paiement`), retard, phase, coupe-moteur | **Réel**, calculé depuis la base |
| Envoi effectif d'un SMS/WhatsApp/appel | **Non simulé** — la `Relance` enregistre l'intention et l'horodatage, aucun gateway n'est appelé |
| Paiement Mobile Money | **Simulé** — `POST /contrats/{id}/echeances/{index}/payer` marque l'échéance payée, remplaçant le webhook MoMo/Moov qu'on n'a pas |

---

## 5. Backend

### 5.1 Modèles (`backend/app/models.py`)

- **`Paiement`** (table) : `contrat_id`, `index`, `date_echeance`, `montant`,
  `paid_at` (`None` tant que non payée), `mode_paiement`. Contrainte unique
  `(contrat_id, index)`.
- **`Relance`** (table) : `contrat_id`, `canal` (`CanalRelance` :
  `sms|whatsapp|appel|coupe_moteur|reactivation`), `origine`
  (`OrigineRelance` : `auto|manuel`), `note`, `created_by`, `created_at`.
- Schémas publics : `EcheancePublic`/`EcheancesPublic`,
  `RelancePublic`/`RelancesPublic`, `ContratDossierPublic` (vue dossier
  agrégée : retard, phase, montant dû, dernière/prochaine action).

### 5.2 Logique pure (`backend/app/recouvrement.py`)

`oldest_unpaid`, `jours_retard`, `montant_du`, `phase_courante`,
`prochaine_echeance`, `ensure_relance_backlog` — voir §2-3 ci-dessus.
Aucune de ces fonctions (sauf `ensure_relance_backlog`) n'écrit en base,
elles sont testables sans DB.

### 5.3 Composition partagée (`backend/app/contrats_service.py`)

`build_context(session, contrat)` charge la demande, les paiements, calcule
retard/phase/montant dû et appelle `ensure_relance_backlog`. Utilisé par les
trois modules (`contrats`, `recouvrement`, `vehicules`) pour ne calculer ce
contexte qu'une fois. `to_dossier_public` en dérive le `ContratDossierPublic`
consommé par `admin.recouvrement.tsx`.

### 5.4 CRUD (`backend/app/crud.py`)

- `create_paiements_for_contrat(session, contrat, demande)` : génère
  l'échéancier complet à la signature (appelé automatiquement par
  `create_contrat`), échéance le 5 de chaque mois à partir de `signed_at`.
- `get_paiements`, `pay_echeance`, `get_relances`, `create_relance`.

### 5.5 Routes API

Préfixe `/api/v1/recouvrement` (`backend/app/api/routes/recouvrement.py`) et
`/api/v1/contrats` (`backend/app/api/routes/contrats.py`) — accès
back-office (`is_admin` ou `is_superuser`) sauf mention contraire.

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/recouvrement/config` | Seuils des 4 phases |
| `GET` | `/recouvrement/dossiers` | Dossiers en retard + phase courante (déclenche le rattrapage) |
| `POST` | `/recouvrement/{contrat_id}/relance` | Relance manuelle (`{canal, note?}`) |
| `GET` | `/contrats` | Portefeuille complet |
| `GET` | `/contrats/{id}/echeances` | Échéancier (accessible aussi au client propriétaire) |
| `POST` | `/contrats/{id}/echeances/{index}/payer` | Simule un paiement Mobile Money |

### 5.6 Migrations Alembic

`d4e5f6a7b8c9` (plate/gps_device_id/cutoff_active sur `contrat`, avec
backfill des contrats existants), `e5f6a7b8c9d0` (tables `paiement` et
`relance`).

---

## 6. Frontend (`FrontPcp`)

- `src/lib/endpoints.ts::recouvrementAPI` / `contratsAPI` — appels HTTP.
- `src/hooks/useRecouvrement.ts` — React Query (`useDossiersEnRetard`,
  `useRecouvrementConfig`, mutation `useCreerRelance`, `usePayerEcheance`).
- `src/routes/admin.recouvrement.tsx` — remplace les tableaux en dur par ces
  hooks ; les boutons SMS/Appel/Email déclenchent
  `POST /recouvrement/{id}/relance` (toast + invalidation de la liste).

---

## 7. Comment étendre

- **Nouveau canal** (ex. email) : ajouter la valeur à `CanalRelance`
  (modèle), à `PHASES` si c'est une phase automatique, et au sélecteur de
  canal côté front.
- **Seuils configurables par l'admin** : aujourd'hui des constantes dans
  `app/recouvrement.py` — pour les rendre modifiables, les déplacer vers
  `ParametresFinanciers` (déjà utilisée pour TEG/apport) et lire la valeur
  dans `PHASES` au lieu d'une constante.
- **Vrai envoi SMS/WhatsApp** : brancher un provider (AfricasTalking/Twilio)
  dans `crud.create_relance`, en gardant le log `Relance` comme source de
  vérité de ce qui a été tenté.
