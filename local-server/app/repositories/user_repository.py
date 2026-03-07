"""Mock in-memory user repository.

This repository stores users in memory for MVP validation.
To migrate to a real database later, replace this class with an
implementation that uses SQLAlchemy, Tortoise ORM, or raw SQL,
keeping the same public interface.
"""

from datetime import datetime

from app.domain.user import User


class UserRepository:
    """In-memory user storage."""

    def __init__(self) -> None:
        self._users: dict[int, dict] = {}
        self._next_id: int = 1

    def create(self, username: str, email: str, hashed_password: str) -> User:
        """Create and store a new user."""
        now = datetime.now()
        user_data = {
            "id": self._next_id,
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "created_at": now,
            "updated_at": now,
        }
        self._users[self._next_id] = user_data
        self._next_id += 1
        return User(
            id=user_data["id"],
            username=user_data["username"],
            email=user_data["email"],
            created_at=user_data["created_at"],
            updated_at=user_data["updated_at"],
        )

    def get_by_id(self, user_id: int) -> User | None:
        """Retrieve a user by ID."""
        data = self._users.get(user_id)
        if data is None:
            return None
        return User(
            id=data["id"],
            username=data["username"],
            email=data["email"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def get_by_email(self, email: str) -> tuple[User, str] | None:
        """Retrieve a user by email. Returns (User, hashed_password) or None."""
        for data in self._users.values():
            if data["email"] == email:
                user = User(
                    id=data["id"],
                    username=data["username"],
                    email=data["email"],
                    created_at=data["created_at"],
                    updated_at=data["updated_at"],
                )
                return user, data["hashed_password"]
        return None

    def email_exists(self, email: str) -> bool:
        """Check if an email is already registered."""
        return any(u["email"] == email for u in self._users.values())

    def username_exists(self, username: str) -> bool:
        """Check if a username is already taken."""
        return any(u["username"] == username for u in self._users.values())
