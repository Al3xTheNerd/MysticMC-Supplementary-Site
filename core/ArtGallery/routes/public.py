from flask import abort, render_template, request
from sqlalchemy import func

from core.ArtGallery import bp
from core.ArtGallery.models import ArtPiece

SERVERS = ("Arcane", "Cosmic", "Elysium")


@bp.route("/")
def Index():
    pieces = ArtPiece.query.order_by(ArtPiece.created_at.desc(), ArtPiece.id.desc()).all()
    return render_template("ArtGallery/public/list.html", pieces=pieces, heading="All Art")


@bp.route("/server/<server>")
def Server(server):
    if server not in SERVERS:
        abort(404)
    pieces = ArtPiece.query.filter_by(server=server).order_by(ArtPiece.created_at.desc(), ArtPiece.id.desc()).all()
    return render_template("ArtGallery/public/list.html", pieces=pieces, heading=f"{server} Art", server = server)


@bp.route("/creators")
def Creators():
    creators = (
        ArtPiece.query.with_entities(ArtPiece.creator_name, func.count(ArtPiece.id))
        .group_by(ArtPiece.creator_name)
        .order_by(func.lower(ArtPiece.creator_name))
        .all()
    )
    selected = request.args.get("creator", "").strip()
    if selected:
        pieces = ArtPiece.query.filter_by(creator_name=selected).order_by(ArtPiece.created_at.desc(), ArtPiece.id.desc()).all()
    else:
        pieces = ArtPiece.query.order_by(func.lower(ArtPiece.creator_name), ArtPiece.name, ArtPiece.id).all()
    return render_template("ArtGallery/public/creators.html", creators=creators, selected=selected, pieces=pieces)


@bp.route("/piece/<int:art_id>")
def Piece(art_id):
    piece = ArtPiece.query.get_or_404(art_id)
    return render_template("ArtGallery/public/piece.html", piece=piece)
