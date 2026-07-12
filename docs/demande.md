# Module « Demande de financement » (Demande)

Documentation technique du module de demande de crédit auto, ajouté au projet
**Phronesis Capital Partners** (backend FastAPI + frontend TanStack Start).

> Objectif : permettre à un utilisateur connecté de créer une **demande de
> financement** dynamique, persistée en base, avec les documents justificatifs
> associés, et reliée à son compte utilisateur.

---

## 1. Architecture & relations

```
┌──────────┐ 1      * ┌──────────┐ 1      * ┌────────────┐
│  User    │──────────▶│ Demande  │──────────▶│ Document  │
└──────────┘          └──────────┘          └────────────┘
   (user)      owner_id (FK, CASCADE)   demande_id (FK, CASCADE)
```

| Relation | Cardinalité | Clé étrangère | Suppression |
|-----------|-------------|---------------|-------------|
| `User` → `Demande` | 1 → * | `demande.owner_id → user.id` | `ON DELETE CASCADE` |
| `Demande` → `Document` | 1 → * | `document.demande_id → demande.id` | `ON DELETE CASCADE` |

Un utilisateur possède plusieurs demandes ; une demande possède plusieurs
documents. La suppression en cascade garantit l'intégrité référentielle.

---

## 2. Backend

### 2.1 Modèles (`backend/app/models.py`)

- **`Demande`** (table SQLModel) : identité du demandeur (`prenom`, `nom`,
  `date_naissance`, `lieu_naissance`, `cni_number`, `situation_matrimoniale`,
  `profession`, `employeur`, `revenu_mensuel`, `anciennete_annees`, `adresse`),
  véhicule & financement (`marque`, `modele`, `annee`, `kilometrage`,
  `vendeur`, `prix_vehicule`, `duree_mois`, `mensualite`, `taux_teg`), suivi
  (`statut`), relations (`owner_id`, `created_at`, `owner`, `documents`).
- **`Document`** (table SQLModel) : `type`, `nom`, `statut`, `ocr`, `demande_id`.
- **`User.demandes`** : relationship `back_populates="owner"` + `cascade_delete`.
- **Enums** (stockés en `VARCHAR` côté DB, validés côté API) :
  - `SituationMatrimoniale` : `celibataire | marie | divorce | veuf`
  - `StatutDemande` : `brouillon | soumise | en_etude | validee | rejectee | signee`
  - `StatutDocument` : `pending | uploaded | processing | valide`

> Note : les enums sont volontairement persistés en `String` (pas de type
> `ENUM` natif Postgres) pour simplifier les migrations Alembic.

### 2.2 Schémas (Pydantic)

| Schéma | Usage |
|--------|-------|
| `DemandeBase` | champs communs écriture/lecture |
| `DemandeCreate` | création (hérite `DemandeBase` + `documents?: DocumentCreate[]`) |
| `DemandeUpdate` | mise à jour partielle (tous champs optionnels) |
| `DemandePublic` | lecture API (inclut `id`, `owner_id`, `created_at`, `documents`) |
| `DemandesPublic` | liste paginée (`data`, `count`) |
| `Document*`, `DocumentsPublic` | schémas documents |

### 2.3 CRUD (`backend/app/crud.py`)

- `create_demande(session, demande_in, owner_id)` : crée la demande **et** ses
  documents en une transaction.
- `get_demandes(session, owner_id=None, skip, limit)` : renvoie
  `(list[Demande], count)`. Si `owner_id` est fourni → filtré par utilisateur.
- `get_demande(session, demande_id)` : recherche par PK.

### 2.4 Routes API (`backend/app/api/routes/demandes.py`)

Préfixe : `/api/v1/demandes`. Toutes les routes requièrent un JWT
(`CurrentUser`).

| Méthode | Endpoint | Accès | Description |
|---------|----------|-------|-------------|
| `POST` | `/demandes` | user | Crée une demande pour l'utilisateur authentifié (201) |
| `GET` | `/demandes` | user | Liste ses demandes ; superuser voit tout |
| `GET` | `/demandes/{id}` | user | Détail (403 si ce n'est pas le sien, sauf superuser) |
| `PATCH` | `/demandes/{id}` | user | Mise à jour (ex. changer `statut`) |
| `DELETE` | `/demandes/{id}` | user | Suppression (cascade documents) |

Enregistrement dans `backend/app/api/main.py` :
`api_router.include_router(demandes.router)`.

### 2.5 Migration Alembic

`backend/app/alembic/versions/c2d3e4f5a6b7_create_demande_and_document_tables.py`
crée les tables `demande` et `document` avec leurs clés étrangères et index.

```bash
docker compose exec backend alembic upgrade head
```

---

## 3. Frontend (`FrontPcp`)

### 3.1 Flux utilisateur

1. **Inscription** (`/inscription`) → `register()` dans
   `src/context/auth-context.tsx` crée le compte **puis connecte
   automatiquement** l'utilisateur (appel à `login`). Cela permet de lier la
   demande au compte sans reconnexion manuelle.
2. **Demande** (`/demande`, `src/routes/demande.tsx`) :
   - Formulaire en 4 étapes (Identité → Véhicule & Financement → Documents →
     Récapitulatif) entièrement **contrôlé** (état `form` + `docs`).
   - La mensualité est calculée en direct via `monthlyPayment()` (`src/lib/format`).
   - Au dernier step, les 3 cases de consentement sont requises.
   - `POST /demandes` via `apiClient` (`src/lib/api.ts`) → le token JWT est
     ajouté automatiquement par l'interceptor.
   - Redirection vers `/dashboard` en cas de succès.
   - Si l'utilisateur n'est pas authentifié, redirection vers `/connexion`.

### 3.2 Mapping des données (frontend → backend)

`src/routes/demande.tsx` construit le payload `DemandeCreate` :
- champs texte/nombre envoyés tels quels (`prenom`, `nom`, `marque`, `modele`,
  `prix_vehicule`, `duree_mois`, `mensualite`, `taux_teg`…) ;
- `revenu_mensuel`, `annee`, `kilometrage`, `anciennete_annees` parsés en entier
  (`toInt`) ; `date_naissance` au format `YYYY-MM-DD` ;
- `documents` : tableau `{ type, nom, statut, ocr }` dérivé de l'état `docs`.

---

## 4. Comment étendre

- **Nouveau champ** : ajouter dans `DemandeBase` (modèle) → `DemandeCreate` /
  `DemandeUpdate` / `DemandePublic` (schémas) → colonne dans la migration
  Alembic → champ `form` dans `demande.tsx`.
- **Nouveau statut** : ajouter la valeur dans l'enum `StatutDemande` (modèle) ;
  côté front, l'UI admin lira `statut` et pourra le modifier via `PATCH`.
- **Documents réels** : remplacer le toggle « Téléverser » par un upload vers un
  stockage (S3/MinIO) ; conserver le modèle `Document` pour la métadonnée.
- **Espace admin** : ajouter une route `/admin/demandes` listant toutes les
  demandes (le backend renvoie déjà tout au superuser via `GET /demandes`).

---

## 5. Tests rapides (curl / PowerShell)

```powershell
$token = (Invoke-RestMethod -Uri "http://localhost:8000/api/v1/login/access-token" `
  -Method Post -ContentType "application/x-www-form-urlencoded" `
  -Body "username=admin@example.com&password=changethis").access_token

$body = @{
  prenom="Jean-Pierre"; nom="ADJOVI"; marque="Toyota"; modele="Corolla";
  prix_vehicule=8500000; duree_mois=48; mensualite=257000;
  documents=@(@{type="CNI"; statut="uploaded"; ocr=$true})
} | ConvertTo-Json -Depth 4

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/demandes/" `
  -Method Post -ContentType "application/json" `
  -Headers @{Authorization="Bearer $token"} -Body $body
```

> Remarque : l'endpoint de collection répond sur `/demandes/` (slash final) ;
> les clients HTTP suivent la redirection 307 en conservant le header
> `Authorization` (axios le fait nativement).
