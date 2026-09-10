"""
Fleet Monitor GPS simulation.

There is no real Traccar server, no Teltonika/Syrus boxes, and no MQTT/TCP
ingestion pipeline behind this project — the cahier des charges assumes
hardware that was never provisioned. Rather than freeze the map with static
mock coordinates, every vehicle's position/speed/engine state is computed by
a *pure function of time*: seeded on the contract id, it moves the vehicle
along a fixed real-world route (Cotonou / Abomey-Calavi / Porto-Novo) in a
continuous loop. Two requests one second apart return two very slightly
different, physically-consistent positions — two requests for the *same*
contract at the *same* timestamp always return the exact same answer, so
nothing flickers and nothing needs a background job or a stored "last
position" row.

The one thing that IS real state (because it is an actual command with legal
weight per the cahier des charges — "log horodaté + identifiant admin
déclencheur obligatoire") is `cutoff_active` on `Contrat`, persisted and
audited via the `Relance` table. When a vehicle is cut off, the simulation
freezes it at the position/time it had when the cutoff happened instead of
continuing to move a car whose engine is supposed to be off.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Waypoint:
    lat: float
    lon: float
    lieu: str


@dataclass(frozen=True)
class Telemetry:
    lat: float
    lon: float
    lieu: str
    vitesse: int
    moteur: bool
    en_mouvement: bool


@dataclass(frozen=True)
class Trajet:
    depart: str
    arrivee: str
    debut: datetime
    duree_min: int
    distance_km: float
    vitesse_max: int


@dataclass(frozen=True)
class AlerteGps:
    type: str  # "vitesse" | "nuit" | "zone"
    message: str
    survenue_a: datetime


# Bornes géographiques du triangle Cotonou / Abomey-Calavi / Porto-Novo,
# identiques à celles déjà utilisées côté front pour la carte SVG maison
# (FrontPcp/src/routes/fleet.index.tsx).
BOUNDS = {"lat_min": 6.30, "lat_max": 6.52, "lon_min": 2.34, "lon_max": 2.62}

_AKPAKPA = Waypoint(6.3556, 2.4380, "Cotonou - Akpakpa")
_GANHI = Waypoint(6.3700, 2.4100, "Cotonou - Ganhi")
_CADJEHOUN = Waypoint(6.3800, 2.4500, "Cotonou - Cadjehoun")
_SAINTE_RITA = Waypoint(6.3400, 2.4280, "Cotonou - Sainte-Rita")
_ZONGO = Waypoint(6.3650, 2.4460, "Cotonou - Zongo-Ehuzu")
_ABOMEY_CALAVI = Waypoint(6.4490, 2.3560, "Abomey-Calavi")
_PORTO_NOVO = Waypoint(6.4960, 2.6050, "Porto-Novo")

# Chaque itinéraire est une boucle : le véhicule enchaîne les segments
# consécutifs puis reboucle sur le premier point indéfiniment.
ROUTES: list[list[Waypoint]] = [
    [_AKPAKPA, _GANHI, _ZONGO, _SAINTE_RITA],
    [_CADJEHOUN, _ABOMEY_CALAVI],
    [_GANHI, _PORTO_NOVO],
    [_SAINTE_RITA, _CADJEHOUN, _AKPAKPA],
]


def _haversine_km(a: Waypoint, b: Waypoint) -> float:
    r = 6371.0
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(h))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class _VehicleProfile:
    """Paramètres stables d'un véhicule, dérivés une fois de son id de contrat."""

    def __init__(self, contrat_id: uuid.UUID) -> None:
        rng = random.Random(f"pcp-fleet-{contrat_id}")
        self.route = rng.choice(ROUTES)
        self.cycle_seconds = rng.uniform(1800, 5400)  # 30 à 90 min pour boucler
        self.phase_offset = rng.uniform(0, self.cycle_seconds)
        self.base_speed_kmh = rng.uniform(28, 68)
        self.has_speed_alert = rng.random() < 0.3
        self.has_zone_alert = rng.random() < 0.12
        self.has_night_alert = rng.random() < 0.4


def _segment_state(profile: _VehicleProfile, at: datetime) -> Telemetry:
    route = profile.route
    n = len(route)
    elapsed = (at.timestamp() + profile.phase_offset) % profile.cycle_seconds
    seg_len = profile.cycle_seconds / n
    seg_index = int(elapsed // seg_len) % n
    frac = (elapsed % seg_len) / seg_len

    origin = route[seg_index]
    dest = route[(seg_index + 1) % n]

    # Les 15 derniers % de chaque segment simulent une arrivée/pause au point.
    if frac > 0.85:
        return Telemetry(
            lat=dest.lat,
            lon=dest.lon,
            lieu=dest.lieu,
            vitesse=0,
            moteur=True,
            en_mouvement=False,
        )

    return _moving_telemetry(profile, origin, dest, frac, at)


def _moving_telemetry(
    profile: _VehicleProfile, origin: Waypoint, dest: Waypoint, frac: float, at: datetime
) -> Telemetry:
    travel_frac = min(frac / 0.85, 1.0)
    lat = _lerp(origin.lat, dest.lat, travel_frac)
    lon = _lerp(origin.lon, dest.lon, travel_frac)
    # Petite variation de vitesse continue (pas de saut brutal d'un appel à l'autre).
    wobble = 6 * math.sin(at.timestamp() / 45.0 + profile.phase_offset)
    vitesse = max(12, round(profile.base_speed_kmh + wobble))
    return Telemetry(
        lat=round(lat, 4),
        lon=round(lon, 4),
        lieu=f"Vers {dest.lieu}",
        vitesse=vitesse,
        moteur=True,
        en_mouvement=True,
    )


def simulate_telemetry(
    contrat_id: uuid.UUID,
    now: datetime,
    cutoff_active: bool,
    cutoff_since: datetime | None,
) -> Telemetry:
    """
    Position/vitesse/moteur "live" d'un véhicule. Si le coupe-moteur est
    actif, le véhicule est figé à la position qu'il occupait au moment de la
    commande plutôt que de continuer à rouler moteur coupé.
    """
    profile = _VehicleProfile(contrat_id)
    reference_time = cutoff_since if (cutoff_active and cutoff_since) else now
    telemetry = _segment_state(profile, reference_time)
    if cutoff_active:
        return Telemetry(
            lat=telemetry.lat,
            lon=telemetry.lon,
            lieu=telemetry.lieu,
            vitesse=0,
            moteur=False,
            en_mouvement=False,
        )
    return telemetry


def simulate_historique(contrat_id: uuid.UUID, now: datetime, jours: int = 2) -> list[Trajet]:
    """Derniers trajets plausibles, stables pour une journée donnée."""
    profile = _VehicleProfile(contrat_id)
    route = profile.route
    n = len(route)
    trajets: list[Trajet] = []
    rng = random.Random(f"pcp-fleet-histo-{contrat_id}-{now.date()}")

    cursor = now - timedelta(hours=rng.uniform(1, 4))
    for i in range(5):
        seg_index = (i + rng.randrange(n)) % n
        origin = route[seg_index]
        dest = route[(seg_index + 1) % n]
        distance = round(_haversine_km(origin, dest) * rng.uniform(1.05, 1.35), 1)
        vitesse_max = round(profile.base_speed_kmh + rng.uniform(5, 25))
        duree_min = max(6, round(distance / max(vitesse_max, 20) * 60))
        trajets.append(
            Trajet(
                depart=origin.lieu,
                arrivee=dest.lieu,
                debut=cursor,
                duree_min=duree_min,
                distance_km=distance,
                vitesse_max=vitesse_max,
            )
        )
        cursor -= timedelta(hours=rng.uniform(2, 9))
        if (now - cursor).days > jours:
            break
    return trajets


def simulate_alertes(contrat_id: uuid.UUID, now: datetime) -> list[AlerteGps]:
    """Alertes GPS "matérielles" plausibles (hors alertes de retard, gérées ailleurs)."""
    profile = _VehicleProfile(contrat_id)
    rng = random.Random(f"pcp-fleet-alertes-{contrat_id}")
    alertes: list[AlerteGps] = []
    if profile.has_speed_alert:
        alertes.append(
            AlerteGps(
                type="vitesse",
                message=f"Vitesse excessive détectée ({round(profile.base_speed_kmh + rng.uniform(15, 30))} km/h)",
                survenue_a=now - timedelta(days=rng.uniform(0.2, 3)),
            )
        )
    if profile.has_night_alert:
        alertes.append(
            AlerteGps(
                type="nuit",
                message="Trajet de nuit détecté (22h-5h)",
                survenue_a=now - timedelta(days=rng.uniform(0.5, 4)),
            )
        )
    if profile.has_zone_alert:
        alertes.append(
            AlerteGps(
                type="zone",
                message="Sortie de la zone Bénin tentée",
                survenue_a=now - timedelta(days=rng.uniform(1, 6)),
            )
        )
    alertes.sort(key=lambda a: a.survenue_a, reverse=True)
    return alertes


def simulate_semaine(contrat_id: uuid.UUID, semaine_offset: int) -> dict:
    """Distance/trajets plausibles d'un véhicule pour une semaine (0 = semaine en cours)."""
    rng = random.Random(f"pcp-fleet-semaine-{contrat_id}-{semaine_offset}")
    nb_trajets = rng.randint(10, 28)
    distance_km = round(nb_trajets * rng.uniform(5, 16), 1)
    return {"distance_km": distance_km, "nb_trajets": nb_trajets}


def average_speed_kmh(contrat_id: uuid.UUID) -> float:
    return _VehicleProfile(contrat_id).base_speed_kmh


def simulate_stats_du_jour(contrat_id: uuid.UUID, now: datetime) -> dict:
    """Distance/durée moteur/nb trajets du jour, stables pour la journée en cours."""
    profile = _VehicleProfile(contrat_id)
    rng = random.Random(f"pcp-fleet-stats-{contrat_id}-{now.date()}")
    nb_trajets = rng.randint(1, 4)
    distance_km = round(nb_trajets * rng.uniform(6, 20), 1)
    duree_min = round(distance_km / max(profile.base_speed_kmh, 20) * 60)
    return {
        "distance_km": distance_km,
        "duree_moteur_min": duree_min,
        "nb_trajets": nb_trajets,
    }


_PLATE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sans I/O, comme les vraies séries


def generate_plate(contrat_id: uuid.UUID) -> str:
    """Immatriculation béninoise plausible, dérivée déterministement de l'id."""
    h = contrat_id.int
    n = len(_PLATE_LETTERS)
    l1 = _PLATE_LETTERS[h % n]
    l2 = _PLATE_LETTERS[(h // n) % n]
    num = (h // (n * n)) % 10000
    l3 = _PLATE_LETTERS[(h // (n * n * 10000)) % n]
    l4 = _PLATE_LETTERS[(h // (n * n * 10000 * n)) % n]
    return f"{l1}{l2} {num:04d} {l3}{l4}"


def generate_gps_device_id(contrat_id: uuid.UUID) -> str:
    """IMEI-like numérique à 15 chiffres pour le boîtier GPS simulé."""
    digits = str(contrat_id.int % 10**15).rjust(15, "3")
    return digits
