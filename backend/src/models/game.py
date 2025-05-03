from .user import db # Import db from user.py or a central models init
import datetime
import random
import string

def generate_room_code(length=6):
    """Generates a random alphanumeric room code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Association table for the many-to-many relationship between users and rooms they are currently in
players_in_room = db.Table("players_in_room",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("room_id", db.Integer, db.ForeignKey("game_room.id"), primary_key=True)
)

class GameRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(10), unique=True, nullable=False, default=generate_room_code)
    host_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    game_type = db.Column(db.String(50), nullable=False) # e.g., "Jogo 1-2-3", "Jogo Eleitoral"
    status = db.Column(db.String(20), nullable=False, default="waiting") # waiting, in_progress, finished
    max_players = db.Column(db.Integer, nullable=False, default=4)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    game_state = db.Column(db.Text, nullable=True) # JSON string to store game-specific state

    host = db.relationship("User", backref=db.backref("hosted_rooms", lazy=True))
    # Use secondary argument for many-to-many relationship
    current_players = db.relationship("User", secondary=players_in_room,
                                      backref=db.backref("current_rooms", lazy="dynamic"),
                                      lazy="dynamic") # Use dynamic loading for players

    # Relationship to Player model (one-to-many)
    players = db.relationship("Player", back_populates="room", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<GameRoom {self.room_code} ({self.game_type})>"

class Player(db.Model):
    """Represents a user within the context of a specific game room."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey("game_room.id"), nullable=False)
    sid = db.Column(db.String(100), nullable=True) # SocketIO session ID, updated on connect/join
    score = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="active") # e.g., active, eliminated, finished
    inventory = db.Column(db.Text, nullable=True) # JSON string for player-specific items (cards, tokens etc.)
    joined_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = db.relationship("User") # Many-to-one relationship to User
    room = db.relationship("GameRoom", back_populates="players") # Many-to-one relationship to GameRoom

    # Unique constraint to ensure a user is only one player per room
    __table_args__ = (db.UniqueConstraint("user_id", "room_id", name="_user_room_uc"),)

    def __repr__(self):
        return f"<Player UserID:{self.user_id} RoomID:{self.room_id}>"

