import sys
from typing import Optional

from . import validators as V
from .radar_store import load_radar, save_radar
from .types import Assignment, Radar, Team, Technology


class RadarProxy:
    def __init__(self) -> None:
        self._radar: Radar = load_radar()
        self._dirty: bool = False

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ---------- reads ----------
    def list_technologies(self, quadrant: Optional[int] = None) -> list[Technology]:
        if quadrant is None:
            return list(self._radar.technologies)
        return [t for t in self._radar.technologies if t.quadrant == quadrant]

    def list_teams(self) -> list[Team]:
        return list(self._radar.teams)

    def list_assignments(self, team_id: str) -> list[Assignment]:
        return list(self._radar.assignments.get(team_id, []))

    def get_assignment(self, team_id: str, tech_id: str) -> Optional[Assignment]:
        for a in self._radar.assignments.get(team_id, []):
            if a.tech == tech_id:
                return a
        return None

    # ---------- writes ----------
    def add_technology(
        self,
        id: str,
        label: str,
        quadrant: int,
        link: Optional[str] = None,
    ) -> Technology:
        existing_ids = {t.id for t in self._radar.technologies}
        if id in existing_ids:
            raise ValueError(
                f"Tech '{id}' already exists. Use radar.list_technologies() to inspect, "
                f"or pick a unique kebab-case id."
            )
        tech = Technology(id=id, label=label, quadrant=quadrant, link=link)  # type: ignore[arg-type]
        self._radar.technologies.append(tech)
        self._dirty = True
        return tech

    def _team_exists(self, team_id: str) -> None:
        if team_id not in {t.id for t in self._radar.teams}:
            raise ValueError(
                f"Team '{team_id}' not found. Available team ids: "
                f"{[t.id for t in self._radar.teams]}"
            )

    def assign(
        self, team_id: str, tech_id: str, ring: int, moved: int = 0
    ) -> Assignment:
        self._team_exists(team_id)
        V.assert_tech_exists(self._radar, tech_id)
        V.assert_not_duplicate(self._radar, team_id, tech_id)
        tech = next(t for t in self._radar.technologies if t.id == tech_id)
        V.assert_adopt_has_link(tech, ring)
        a = Assignment(tech=tech_id, ring=ring, moved=moved)  # type: ignore[arg-type]
        self._radar.assignments.setdefault(team_id, []).append(a)
        self._dirty = True
        return a

    def move(self, team_id: str, tech_id: str, new_ring: int) -> Assignment:
        self._team_exists(team_id)
        V.assert_tech_exists(self._radar, tech_id)
        current = self.get_assignment(team_id, tech_id)
        if current is None:
            raise ValueError(
                f"'{tech_id}' is not assigned to '{team_id}'. "
                f"Use radar.assign('{team_id}', '{tech_id}', {new_ring}) to add it."
            )
        V.assert_legal_ring_transition(current.ring, new_ring)
        tech = next(t for t in self._radar.technologies if t.id == tech_id)
        V.assert_adopt_has_link(tech, new_ring)
        moved = 0
        if new_ring < current.ring:
            moved = 1
        elif new_ring > current.ring:
            moved = -1
        new_a = Assignment(tech=tech_id, ring=new_ring, moved=moved)  # type: ignore[arg-type]
        assignments = self._radar.assignments[team_id]
        for i, a in enumerate(assignments):
            if a.tech == tech_id:
                assignments[i] = new_a
                break
        self._dirty = True
        return new_a

    def remove_assignment(self, team_id: str, tech_id: str) -> None:
        self._team_exists(team_id)
        assignments = self._radar.assignments.get(team_id, [])
        for i, a in enumerate(assignments):
            if a.tech == tech_id:
                del assignments[i]
                self._dirty = True
                return
        raise ValueError(
            f"'{tech_id}' is not assigned to '{team_id}'. Nothing to remove."
        )

    # ---------- persistence ----------
    def commit(self, message: str = "") -> None:
        V.assert_single_default(self._radar)
        save_radar(self._radar)
        self._dirty = False
        if message:
            print(f"[commit] {message}", file=sys.stderr)
        else:
            print("[commit] radar_working.json saved", file=sys.stderr)
