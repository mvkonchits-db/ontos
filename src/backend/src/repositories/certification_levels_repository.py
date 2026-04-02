"""Repository for certification_levels CRUD operations."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.db_models.certification_levels import CertificationLevelDb
from src.common.logging import get_logger

logger = get_logger(__name__)


class CertificationLevelsRepository:

    def get_all_ordered(self, db: Session) -> List[CertificationLevelDb]:
        return (
            db.query(CertificationLevelDb)
            .order_by(CertificationLevelDb.level_order)
            .all()
        )

    def get_by_id(self, db: Session, level_id: UUID) -> Optional[CertificationLevelDb]:
        return db.query(CertificationLevelDb).filter(
            CertificationLevelDb.id == level_id
        ).first()

    def get_by_order(self, db: Session, level_order: int) -> Optional[CertificationLevelDb]:
        return db.query(CertificationLevelDb).filter(
            CertificationLevelDb.level_order == level_order
        ).first()

    def get_max_order(self, db: Session) -> int:
        from sqlalchemy import func
        result = db.query(func.max(CertificationLevelDb.level_order)).scalar()
        return result or 0

    def create(self, db: Session, *, name: str, level_order: int,
               description: Optional[str] = None, icon: Optional[str] = None,
               color: Optional[str] = None) -> CertificationLevelDb:
        obj = CertificationLevelDb(
            name=name,
            level_order=level_order,
            description=description,
            icon=icon,
            color=color,
        )
        db.add(obj)
        db.flush()
        db.refresh(obj)
        logger.info(f"Created certification level '{name}' at order {level_order}")
        return obj

    def update(self, db: Session, *, db_obj: CertificationLevelDb,
               update_data: dict) -> CertificationLevelDb:
        for field, value in update_data.items():
            if hasattr(db_obj, field) and field != "id":
                setattr(db_obj, field, value)
        db.add(db_obj)
        db.flush()
        db.refresh(db_obj)
        logger.info(f"Updated certification level '{db_obj.name}'")
        return db_obj

    def delete(self, db: Session, *, db_obj: CertificationLevelDb) -> None:
        db.delete(db_obj)
        db.flush()
        logger.info(f"Deleted certification level '{db_obj.name}' (order={db_obj.level_order})")

    def reorder(self, db: Session, *, order_map: dict[str, int]) -> List[CertificationLevelDb]:
        """Bulk reorder: order_map = {str(uuid): new_order, ...}.

        Uses two-pass approach to avoid unique constraint violations on level_order:
        first sets all changing rows to negative temp values, then to final values.
        """
        all_levels = self.get_all_ordered(db)
        changed = []
        for level in all_levels:
            new_order = order_map.get(str(level.id))
            if new_order is not None and new_order != level.level_order:
                changed.append((level, new_order))

        if not changed:
            return all_levels

        for i, (level, _) in enumerate(changed):
            level.level_order = -(i + 1)
            db.add(level)
        db.flush()

        for level, new_order in changed:
            level.level_order = new_order
            db.add(level)
        db.flush()

        return self.get_all_ordered(db)

    def count_entities_using_level(self, db: Session, level_order: int) -> int:
        """Count how many entities reference this certification level."""
        total = 0
        tables_to_check = ["data_products", "data_contracts", "datasets", "assets"]
        for table_name in tables_to_check:
            try:
                from sqlalchemy import text
                result = db.execute(
                    text(f"SELECT COUNT(*) FROM {table_name} WHERE certification_level = :lvl"),
                    {"lvl": level_order},
                ).scalar()
                total += result or 0
            except Exception:
                pass
        return total

    def is_empty(self, db: Session) -> bool:
        return db.query(CertificationLevelDb).count() == 0

    def seed_defaults(self, db: Session) -> List[CertificationLevelDb]:
        """Seed default certification levels if table is empty."""
        if not self.is_empty(db):
            return self.get_all_ordered(db)

        defaults = [
            {"level_order": 1, "name": "Bronze", "description": "Basic certification", "icon": "shield", "color": "amber"},
            {"level_order": 2, "name": "Silver", "description": "Intermediate certification", "icon": "shield-check", "color": "slate"},
            {"level_order": 3, "name": "Gold", "description": "Highest certification", "icon": "shield-check", "color": "yellow"},
        ]
        created = []
        for d in defaults:
            created.append(self.create(db, **d))
        logger.info("Seeded default certification levels: Bronze, Silver, Gold")
        return created


certification_levels_repo = CertificationLevelsRepository()
