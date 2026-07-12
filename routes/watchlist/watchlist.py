"""
routes/watchlist.py — CineLog (feature/watchlist branch)

Endpoints for the watchlist feature.
"""

from flask import Blueprint, jsonify, request
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)
from services.collection_service import FilmNotFoundError

watchlist_bp = Blueprint("watchlist", __name__)


@watchlist_bp.route("/<user_id>", methods=["GET"])
def view_watchlist(user_id):
    """GET /watchlist/<user_id> — Return the user's watchlist (newest first)."""
    films = get_watchlist(user_id)
    return jsonify(films)


@watchlist_bp.route("/<user_id>/add", methods=["POST"])
def add_film(user_id):
    """
    POST /watchlist/<user_id>/add

    Body: { "film_id": <uuid>, "public": <bool, optional> }

    `public` is optional and defaults to True; callers may set it
    explicitly to control the entry's visibility.
    """
    data = request.get_json()
    if not data or "film_id" not in data:
        return jsonify({"error": "film_id is required"}), 400

    public = data.get("public", True)

    try:
        entry = add_to_watchlist(
            user_id=user_id, film_id=data["film_id"], public=public
        )
    except FilmNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except AlreadyInWatchlistError as e:
        return jsonify({"error": str(e)}), 409

    return jsonify(entry.to_dict()), 201


@watchlist_bp.route("/<user_id>/remove", methods=["POST"])
def remove_film(user_id):
    """
    POST /watchlist/<user_id>/remove

    Body: { "film_id": <uuid> }
    """
    data = request.get_json()
    if not data or "film_id" not in data:
        return jsonify({"error": "film_id is required"}), 400

    try:
        remove_from_watchlist(user_id=user_id, film_id=data["film_id"])
    except NotInWatchlistError as e:
        return jsonify({"error": str(e)}), 404

    return jsonify({"removed": True}), 200
