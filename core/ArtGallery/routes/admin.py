import hmac
import json
import shutil
from io import BytesIO
from pathlib import Path
from secrets import token_urlsafe

from PIL import Image, UnidentifiedImageError
from flask import abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from core.ArtGallery import bp
from core.ArtGallery.models import ArtPiece
from core.ArtGallery.routes.public import SERVERS
from core.Configuration.decorators import has_permission
from core.Configuration.models import User, uploadLog
from core.extensions import db

MAX_REQUEST_BYTES = 50 * 1024 * 1024
MAX_TILE_BYTES = 2 * 1024 * 1024


def _csrf_token():
    if "art_csrf" not in session:
        session["art_csrf"] = token_urlsafe(32)
    return session["art_csrf"]


def _check_csrf():
    if request.content_length and request.content_length > MAX_REQUEST_BYTES:
        abort(413, "The upload is too large (50 MB maximum per art piece).")
    sent = request.form.get("csrf_token", "")
    if not hmac.compare_digest(sent, session.get("art_csrf", "")) or not sent:
        abort(400, "Invalid form token. Reload the page and try again.")


def _art_root():
    root = Path(current_app.static_folder) / "images" / "Art"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_tiles():
    if request.content_length and request.content_length > MAX_REQUEST_BYTES:
        raise ValueError("The upload is too large (50 MB maximum per art piece).")
    tiles = []
    for upload in request.files.getlist("tiles"):
        if not upload.filename:
            continue
        if Path(upload.filename).suffix.lower() != ".png":
            raise ValueError("Only .png files can be uploaded.")
        data = upload.stream.read(MAX_TILE_BYTES + 1)
        if len(data) > MAX_TILE_BYTES:
            raise ValueError("Each tile must be 2 MB or smaller.")
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG" or image.size != (128, 128) or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Every tile must be a non-animated 128×128 PNG.")
                image.load()
                output = BytesIO()
                image.convert("RGBA").save(output, format="PNG")
                tiles.append(output.getvalue())
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("One of the selected files is not a valid PNG image.") from exc
    return tiles


def _validate_layout(raw, existing_ids, new_count):
    try:
        rows = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("The tile layout could not be read.") from exc
    if not isinstance(rows, list) or not rows or any(not isinstance(row, list) or not row for row in rows):
        raise ValueError("Add at least one row with a tile.")
    if len(rows) > 1000 or sum(map(len, rows)) > 10000:
        raise ValueError("The layout has too many spaces.")
    used_existing, used_new = set(), set()
    for row in rows:
        for cell in row:
            if cell is None:
                continue
            if not isinstance(cell, str) or len(cell) < 3 or cell[1] != ":" or not cell[2:].isdigit():
                raise ValueError("The layout contains an invalid tile.")
            index = int(cell[2:])
            if cell[0] == "e":
                if index not in existing_ids or index in used_existing:
                    raise ValueError("An existing tile is missing or used twice.")
                used_existing.add(index)
            elif cell[0] == "n":
                if index >= new_count or index in used_new:
                    raise ValueError("An uploaded tile is missing or used twice.")
                used_new.add(index)
            else:
                raise ValueError("The layout contains an invalid tile.")
    if used_new != set(range(new_count)):
        raise ValueError("Place every newly uploaded tile before saving.")
    if not used_existing and not used_new:
        raise ValueError("An art piece needs at least one image tile.")
    return rows, used_existing


def _form_data(other):
    name = request.form.get("name", "").strip()
    server = request.form.get("server", "")
    purchase = request.form.get("purchase_location", "").strip()
    price = request.form.get("price", "").strip()
    notes = request.form.get("notes", "").strip()
    if not name or len(name) > 150:
        raise ValueError("Art name is required and must be 150 characters or fewer.")
    if server not in SERVERS:
        raise ValueError("Choose Arcane, Cosmic, or Elysium.")
    if len(purchase) > 250 or len(price) > 100 or len(notes) > 2000:
        raise ValueError("A text field exceeds its character limit.")
    if other:
        creator_id = request.form.get("creator_user_id", "").strip()
        if creator_id:
            if not creator_id.isdigit():
                raise ValueError("Choose a valid site user.")
            creator = db.session.get(User, int(creator_id))
            if creator is None:
                raise ValueError("The selected site user no longer exists.")
            creator_name = creator.username
            creator_user_id = creator.id
        else:
            creator_name = request.form.get("creator_name", "").strip()
            creator_user_id = None
            if not creator_name or len(creator_name) > 100:
                raise ValueError("Enter a creator name of 100 characters or fewer.")
    else:
        creator_name = current_user.username
        creator_user_id = current_user.id
    return dict(name=name, server=server, purchase_location=purchase, price=price,
                notes=notes, creator_name=creator_name, creator_user_id=creator_user_id)


def _editor(piece=None, other=False):
    users = User.query.order_by(User.username).all() if other else []
    existing = [] if piece is None else sorted({tile for row in piece.layout for tile in row if tile is not None})
    return render_template("ArtGallery/admin/editor.html", piece=piece, other=other, users=users,
                           servers=SERVERS, existing=existing, csrf_token=_csrf_token())


def _save(piece=None, other=False):
    _check_csrf()
    try:
        fields = _form_data(other)
        new_tiles = _read_tiles()
        old_ids = set() if piece is None else {tile for row in piece.layout for tile in row if tile is not None}
        rows, kept = _validate_layout(request.form.get("layout"), old_ids, len(new_tiles))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(request.url)

    creating = piece is None
    if creating:
        piece = ArtPiece(uploader_user_id=current_user.id, layout_json="[]", **fields)
        db.session.add(piece)
        db.session.flush()
    folder = _art_root() / str(piece.id)
    folder.mkdir(exist_ok=True)
    disk_ids = {int(path.stem) for path in folder.glob("*.png") if path.stem.isdigit()}
    next_id = max(disk_ids | old_ids, default=-1) + 1
    new_ids = {index: next_id + index for index in range(len(new_tiles))}
    layout = [[None if cell is None else (int(cell[2:]) if cell[0] == "e" else new_ids[int(cell[2:])])
               for cell in row] for row in rows]
    written = []
    try:
        for index, data in enumerate(new_tiles):
            path = folder / f"{new_ids[index]}.png"
            path.write_bytes(data)
            written.append(path)
        if not creating:
            for key, value in fields.items():
                setattr(piece, key, value)
        piece.layout_json = json.dumps(layout, separators=(",", ":"))
        db.session.commit()
    except Exception:
        db.session.rollback()
        for path in written:
            path.unlink(missing_ok=True)
        if creating:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    for obsolete in old_ids - kept:
        (folder / f"{obsolete}.png").unlink(missing_ok=True)
    uploadLog(current_user, "Art", "created art." if creating else "updated art.", piece.id)
    flash("Art saved.", "success")
    return redirect(url_for("ArtGallery.Piece", art_id=piece.id))


@bp.route("/add", methods=["GET", "POST"])
@login_required
def AddArt():
    return _save() if request.method == "POST" else _editor()


@bp.route("/manage")
@login_required
def ManageArt():
    pieces = ArtPiece.query.filter_by(creator_user_id=current_user.id).order_by(ArtPiece.id.desc()).all()
    return render_template("ArtGallery/admin/manage.html", pieces=pieces, other=False, csrf_token=_csrf_token())


@bp.route("/add_others", methods=["GET", "POST"])
@has_permission("add_art_others")
def AddArtOthers():
    return _save(other=True) if request.method == "POST" else _editor(other=True)


@bp.route("/manage_others")
@has_permission("manage_art_others")
def ManageArtOthers():
    pieces = ArtPiece.query.filter(or_(ArtPiece.creator_user_id != current_user.id,
                                       ArtPiece.creator_user_id.is_(None))).order_by(ArtPiece.id.desc()).all()
    return render_template("ArtGallery/admin/manage.html", pieces=pieces, other=True, csrf_token=_csrf_token())


@bp.route("/edit/<int:art_id>", methods=["GET", "POST"])
@login_required
def EditArt(art_id):
    piece = ArtPiece.query.get_or_404(art_id)
    own = piece.creator_user_id == current_user.id
    if not own and not current_user.has_permission("manage_art_others"):
        abort(403)
    if request.method == "POST":
        return _save(piece, other=not own)
    return _editor(piece, other=not own)


@bp.route("/delete/<int:art_id>", methods=["POST"])
@login_required
def DeleteArt(art_id):
    _check_csrf()
    piece = ArtPiece.query.get_or_404(art_id)
    own = piece.creator_user_id == current_user.id
    if not own and not current_user.has_permission("delete_art_others"):
        abort(403)
    folder = _art_root() / str(piece.id)
    db.session.delete(piece)
    db.session.commit()
    shutil.rmtree(folder, ignore_errors=True)
    uploadLog(current_user, "Art", "deleted art.", art_id)
    flash("Art deleted.", "success")
    destination = "ArtGallery.ManageArt" if own else (
        "ArtGallery.ManageArtOthers" if current_user.has_permission("manage_art_others") else "ArtGallery.Index"
    )
    return redirect(url_for(destination))
