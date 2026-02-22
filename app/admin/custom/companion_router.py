"""Companion routing panel — visual ghost-patient assignment for DMs."""

from __future__ import annotations

from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.infra.db import async_session_factory
from app.models.db_models import Game, Ghost, Patient


class CompanionRouterView(BaseView):
    name = "Companion Router"
    icon = "fa-solid fa-link"

    @expose("/companion-router", methods=["GET"])
    async def companion_page(self, request: Request):
        game_id = request.query_params.get("game_id", "")
        ghosts = []
        patients = []
        games = []

        async with async_session_factory() as db:
            result = await db.execute(
                select(Game).order_by(Game.created_at.desc())
            )
            games = [{"id": g.id, "name": g.name} for g in result.scalars().all()]

            if game_id:
                ghost_result = await db.execute(
                    select(Ghost)
                    .where(Ghost.game_id == game_id)
                    .options(selectinload(Ghost.current_patient))
                )
                for g in ghost_result.scalars().all():
                    ghosts.append({
                        "id": g.id,
                        "name": g.name,
                        "current_patient_id": g.current_patient_id,
                        "current_patient_name": (
                            g.current_patient.name if g.current_patient else None
                        ),
                    })

                patient_result = await db.execute(
                    select(Patient)
                    .where(Patient.game_id == game_id)
                    .order_by(Patient.name)
                )
                for p in patient_result.scalars().all():
                    patients.append({
                        "id": p.id,
                        "name": p.name,
                        "soul_color": p.soul_color,
                    })

        assigned_patient_ids = {
            g["current_patient_id"] for g in ghosts if g["current_patient_id"]
        }

        return await self.templates.TemplateResponse(
            request,
            "admin/companion_router.html",
            {
                "ghosts": ghosts,
                "patients": patients,
                "games": games,
                "game_id": game_id,
                "assigned_patient_ids": assigned_patient_ids,
            },
        )

    @expose("/companion-router/save", methods=["POST"])
    async def save_assignments(self, request: Request):
        form = await request.form()
        game_id = form.get("game_id", "")

        # Collect all ghost -> patient assignments from the form
        # Form fields are named "ghost_{ghost_id}" with patient_id as value
        assignments: dict[str, str | None] = {}
        for key, value in form.multi_items():
            if key.startswith("ghost_"):
                ghost_id = key[6:]  # strip "ghost_" prefix
                assignments[ghost_id] = value or None

        if not assignments:
            return RedirectResponse(
                url=f"/admin/companion-router?game_id={game_id}", status_code=303,
            )

        async with async_session_factory() as db:
            # Load all affected ghosts in one query
            ghost_result = await db.execute(
                select(Ghost).where(Ghost.id.in_(assignments.keys()))
            )
            ghosts_by_id = {g.id: g for g in ghost_result.scalars().all()}

            # Build a set of patient_ids being assigned (for collision check)
            target_patients: dict[str, str] = {}  # patient_id -> ghost_id
            for ghost_id, patient_id in assignments.items():
                if patient_id:
                    if patient_id in target_patients:
                        # Two ghosts assigned to the same patient in this batch
                        # skip the second one
                        continue
                    target_patients[patient_id] = ghost_id

            # Check for collisions with ghosts NOT in this batch
            for patient_id, ghost_id in target_patients.items():
                existing = await db.execute(
                    select(Ghost).where(
                        Ghost.current_patient_id == patient_id,
                        Ghost.id.not_in(list(assignments.keys())),
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    # Patient already assigned to a ghost outside this batch
                    target_patients.pop(patient_id, None)

            # Apply assignments
            for ghost_id, patient_id in assignments.items():
                ghost = ghosts_by_id.get(ghost_id)
                if ghost is None:
                    continue
                if patient_id and patient_id in target_patients:
                    ghost.current_patient_id = patient_id
                else:
                    ghost.current_patient_id = None

            await db.commit()

        return RedirectResponse(
            url=f"/admin/companion-router?game_id={game_id}", status_code=303,
        )
