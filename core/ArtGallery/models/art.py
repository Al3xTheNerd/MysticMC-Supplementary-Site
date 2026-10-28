import json
from datetime import datetime, timezone

from core.extensions import db


class ArtPiece(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    creator_name = db.Column(db.String(100), nullable=False, index=True)
    creator_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    uploader_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    server = db.Column(db.String(16), nullable=False, index=True)
    purchase_location = db.Column(db.String(250), nullable=False, default="")
    price = db.Column(db.String(100), nullable=False, default="")
    notes = db.Column(db.String(2000), nullable=False, default="")
    layout_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    @property
    def layout(self):
        return json.loads(self.layout_json)

    @property
    def tile_count(self):
        return sum(tile is not None for row in self.layout for tile in row)
    
    @property
    def height(self):
        return len(self.layout)

    @property
    def width(self):
        return max((len(row) for row in self.layout), default=0)
