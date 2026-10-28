from flask import Blueprint

bp = Blueprint("ArtGallery", __name__, url_prefix="/art", template_folder="templates")

RegisteredPermissions = [
    ("add_art_others", "Upload art for another creator"),
    ("manage_art_others", "Manage art uploaded by other users"),
    ("delete_art_others", "Delete art uploaded by other users"),
]

from core.ArtGallery import routes  # noqa: E402,F401
