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
    async def router_page(self, request: Request):
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

    @expose("/companion-router/assign", methods=["POST"])
    async def assign_companion(self, request: Request):
        form = await request.form()
        ghost_id = form.get("ghost_id", "")
        patient_id = form.get("patient_id", "") or None
        game_id = form.get("game_id", "")

        async with async_session_factory() as db:
            ghost_result = await db.execute(
                select(Ghost).where(Ghost.id == ghost_id)
            )
            ghost = ghost_result.scalar_one_or_none()
            if ghost:
                if patient_id:
                    # Check no other ghost already assigned to this patient
                    existing = await db.execute(
                        select(Ghost).where(
                            Ghost.current_patient_id == patient_id,
                            Ghost.id != ghost_id,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        return RedirectResponse(
                            url=f"/admin/companion-router?game_id={game_id}",
                            status_code=303,
                        )
                    ghost.current_patient_id = patient_id
                else:
                    ghost.current_patient_id = None
                await db.commit()

        return RedirectResponse(
            url=f"/admin/companion-router?game_id={game_id}", status_code=303
        )
