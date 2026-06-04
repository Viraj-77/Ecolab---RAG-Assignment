from difflib import get_close_matches

from .types import Radar, Technology

RING_NAMES = {0: "ADOPT", 1: "TRIAL", 2: "ASSESS", 3: "HOLD"}


def assert_tech_exists(radar: Radar, tech_id: str) -> None:
    ids = [t.id for t in radar.technologies]
    if tech_id in ids:
        return
    similar = get_close_matches(tech_id, ids, n=5, cutoff=0.3) or ids[:5]
    raise ValueError(
        f"Tech '{tech_id}' not found in radar. Did you mean one of: {similar}?"
    )


def assert_not_duplicate(radar: Radar, team_id: str, tech_id: str) -> None:
    existing = radar.assignments.get(team_id, [])
    for a in existing:
        if a.tech == tech_id:
            ring_name = RING_NAMES.get(a.ring, str(a.ring))
            raise ValueError(
                f"{tech_id} is already assigned to {team_id} (ring: {ring_name}). "
                f"Use radar.move('{team_id}', '{tech_id}', <new_ring>) to change its ring."
            )


def assert_legal_ring_transition(from_ring: int, to_ring: int) -> None:
    if (from_ring == 0 and to_ring == 3) or (from_ring == 3 and to_ring == 0):
        raise ValueError(
            "Cannot move from ADOPT to HOLD (or HOLD to ADOPT) in one step. "
            "Allowed intermediate rings: TRIAL (1) or ASSESS (2)."
        )


def assert_adopt_has_link(tech: Technology, ring: int) -> None:
    if ring == 0 and tech.link is None:
        raise ValueError(
            f"Tech '{tech.id}' cannot be set to ADOPT without a link. "
            f"Add a link field first: e.g. "
            f"radar.update_technology('{tech.id}', link='https://...')"
        )


def assert_single_default(radar: Radar) -> None:
    team_ids = [t.id for t in radar.teams]
    if radar.default_team not in team_ids:
        raise ValueError(
            f"default_team '{radar.default_team}' is not a known team. "
            f"Available team ids: {team_ids}"
        )
