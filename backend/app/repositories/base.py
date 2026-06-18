"""Generic Repository base class with common CRUD operations."""

from typing import TypeVar, Generic, Type

from sqlalchemy.orm import Session

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic CRUD repository for SQLAlchemy models.

    Usage:
        class QuestionRepo(BaseRepository[Question]):
            model = Question
    """

    model: Type[ModelType]

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, id: int) -> ModelType | None:
        """Fetch a single record by primary key."""
        return self.db.query(self.model).filter(self.model.id == id).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """Fetch a paginated list of records."""
        return self.db.query(self.model).offset(skip).limit(limit).all()

    def count(self) -> int:
        """Return total record count."""
        return self.db.query(self.model).count()

    def create(self, obj: ModelType) -> ModelType:
        """Insert a new record."""
        self.db.add(obj)
        self.db.flush()
        return obj

    def create_batch(self, objects: list[ModelType]) -> list[ModelType]:
        """Insert multiple records in a single transaction."""
        self.db.add_all(objects)
        self.db.flush()
        return objects

    def delete(self, id: int) -> bool:
        """Delete a record by primary key. Returns True if deleted."""
        obj = self.get_by_id(id)
        if obj:
            self.db.delete(obj)
            self.db.flush()
            return True
        return False

    def commit(self) -> None:
        """Commit the current transaction."""
        self.db.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.db.rollback()
