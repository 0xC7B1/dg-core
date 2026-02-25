"""Delete confirmation info endpoint — provides human-readable labels and cascade counts."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import RelationshipDirection
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.infra.db import async_session_factory

# Lazily-built cascade map: {ModelClassName: [(ChildModelClass, fk_column_attr_name), ...]}
_CASCADE_MAP: dict[str, list[tuple[type, str]]] | None = None

MAX_PKS = 50


def _build_cascade_map() -> dict[str, list[tuple[type, str]]]:
    """Build cascade map by introspecting ORM relationships with cascade delete."""
    from app.models.db_models import Base

    cascade_map: dict[str, list[tuple[type, str]]] = {}

    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if cls is Base:
            continue

        children: list[tuple[type, str]] = []
        for rel in mapper.relationships:
            # Only parent→child (ONETOMANY) with cascade delete
            if rel.direction != RelationshipDirection.ONETOMANY:
                continue
            if "delete" not in rel.cascade:
                continue

            child_model = rel.mapper.class_
            # Find the FK column on the child that points back to this parent
            for _local_col, remote_col in rel.local_remote_pairs:
                if remote_col.foreign_keys:
                    children.append((child_model, remote_col.key))
                    break

        if children:
            cascade_map[cls.__name__] = children

    return cascade_map


def _get_cascade_map() -> dict[str, list[tuple[type, str]]]:
    global _CASCADE_MAP
    if _CASCADE_MAP is None:
        _CASCADE_MAP = _build_cascade_map()
    return _CASCADE_MAP


class DeleteInfoView(BaseView):
    name = "Delete Info"
    icon = "fa-solid fa-info"

    def is_visible(self, request: Request) -> bool:
        return False

    @expose("/delete-info", methods=["GET"])
    async def delete_info(self, request: Request) -> JSONResponse:
        identity = request.query_params.get("identity", "")
        pks_param = request.query_params.get("pks", "")

        if not identity or not pks_param:
            return JSONResponse({"items": [], "cascade": []})

        pks = [pk.strip() for pk in pks_param.split(",") if pk.strip()]
        if not pks:
            return JSONResponse({"items": [], "cascade": []})

        pks = pks[:MAX_PKS]

        # Resolve model class from identity via admin views
        model_class = None
        for view in self._admin_ref.views:
            if hasattr(view, "model") and getattr(view, "identity", None) == identity:
                model_class = view.model
                break

        if model_class is None:
            return JSONResponse({"items": [], "cascade": []})

        model_name = model_class.__name__
        cascade_map = _get_cascade_map()

        pk_columns = sa_inspect(model_class).mapper.primary_key
        is_composite = len(pk_columns) > 1

        async with async_session_factory() as db:
            # --- Fetch display labels ---
            items = []
            if is_composite:
                # Composite PK (e.g. GamePlayer) — query individually
                for pk_str in pks:
                    parts = pk_str.split(";")
                    if len(parts) != len(pk_columns):
                        items.append({"pk": pk_str, "label": pk_str})
                        continue
                    conditions = [col == val for col, val in zip(pk_columns, parts)]
                    result = await db.execute(select(model_class).where(*conditions))
                    row = result.scalars().first()
                    if row:
                        try:
                            items.append({"pk": pk_str, "label": str(row)})
                        except Exception:
                            items.append({"pk": pk_str, "label": pk_str})
                    else:
                        items.append({"pk": pk_str, "label": pk_str})
            else:
                pk_col = pk_columns[0]
                result = await db.execute(
                    select(model_class).where(pk_col.in_(pks))
                )
                rows = result.scalars().all()
                pk_to_label: dict[str, str] = {}
                for row in rows:
                    pk_val = str(getattr(row, pk_col.key))
                    try:
                        pk_to_label[pk_val] = str(row)
                    except Exception:
                        pk_to_label[pk_val] = pk_val

                for pk in pks:
                    items.append({"pk": pk, "label": pk_to_label.get(pk, pk)})

            # --- Count cascade children ---
            cascade: list[dict[str, str | int]] = []
            children_info = cascade_map.get(model_name, [])
            filter_pks = pks

            for child_cls, fk_attr_name in children_info:
                fk_col = getattr(child_cls, fk_attr_name, None)
                if fk_col is None:
                    continue

                result = await db.execute(
                    select(func.count()).select_from(child_cls).where(
                        fk_col.in_(filter_pks)
                    )
                )
                count = result.scalar_one()
                if count > 0:
                    # Use the admin view's display name if registered
                    display_name = child_cls.__name__
                    for v in self._admin_ref.views:
                        if hasattr(v, "model") and v.model is child_cls:
                            display_name = getattr(v, "name", child_cls.__name__)
                            break
                    cascade.append({"model": display_name, "count": count})

        return JSONResponse({"items": items, "cascade": cascade})
