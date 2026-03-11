import os
from flask import Flask, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


with app.app_context():
    db.create_all()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/items")
def list_items():
    return jsonify([i.to_dict() for i in Item.query.all()])


@app.post("/items")
def create_item():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    item = Item(name=data["name"], description=data.get("description"))
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@app.get("/items/<int:item_id>")
def get_item(item_id):
    item = db.get_or_404(Item, item_id, description="not found")
    return jsonify(item.to_dict())


@app.put("/items/<int:item_id>")
def update_item(item_id):
    item = db.get_or_404(Item, item_id, description="not found")
    data = request.get_json() or {}
    item.name = data.get("name", item.name)
    item.description = data.get("description", item.description)
    db.session.commit()
    return jsonify(item.to_dict())


@app.delete("/items/<int:item_id>")
def delete_item(item_id):
    item = db.get_or_404(Item, item_id, description="not found")
    db.session.delete(item)
    db.session.commit()
    return "", 204
