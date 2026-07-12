"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Structured to match tests/test_collection.py
(same app / user / film fixtures and assertion style).
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Nonexistent film (Comment 3) ─────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist should raise FilmNotFoundError,
    not a database integrity error. Mirrors
    test_add_to_collection_nonexistent_film_raises.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── Deduplication (Comment 2) ────────────────────────────────────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """Adding the same film twice raises AlreadyInWatchlistError, no dupes."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── remove_from_watchlist (stretch) ──────────────────────────────────────────

def test_remove_from_watchlist_removes_entry(app, sample_user, sample_film):
    """Removing a saved film deletes the entry and returns True."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert remove_from_watchlist(sample_user, sample_film) is True
        assert WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first() is None


def test_remove_from_watchlist_not_present_raises(app, sample_user, sample_film):
    """Removing a film that isn't on the watchlist raises NotInWatchlistError."""
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(sample_user, sample_film)


# ── Second edge case (stretch): dedup is per-user, not global ─────────────────

def test_watchlist_dedup_is_scoped_per_user(app, sample_film):
    """
    Chosen edge case: deduplication must be scoped to (user_id, film_id),
    not global to the film. Two different users saving the same film should
    both succeed — a naive "does any entry for this film exist?" check would
    wrongly block the second user.
    """
    with app.app_context():
        u1 = User(username="alice", email="alice@example.com")
        u2 = User(username="bob", email="bob@example.com")
        db.session.add_all([u1, u2])
        db.session.commit()
        id1, id2 = u1.id, u2.id

        add_to_watchlist(user_id=id1, film_id=sample_film)
        add_to_watchlist(user_id=id2, film_id=sample_film)  # must not raise

        assert WatchlistEntry.query.filter_by(film_id=sample_film).count() == 2
