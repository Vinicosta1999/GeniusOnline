from flask_sqlalchemy import SQLAlchemy
import datetime

db = SQLAlchemy() # Initialize db here

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False) # Store hash, not plain password
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships defined via backref in GameRoom ("hosted_rooms", "current_rooms")

    def __repr__(self):
        return f"<User {self.username}>"

