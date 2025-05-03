# -*- coding: utf-8 -*-
import eventlet
eventlet.monkey_patch()

import os
import sys
import logging

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect, ConnectionRefusedError
# from flask_login import current_user # Removed Flask-Login
from flask_jwt_extended import JWTManager, verify_jwt_in_request, get_jwt_identity, decode_token

# Import database and models
from src.models.user import db, User
from src.models.game import GameRoom, Player

# Import CORS
from flask_cors import CORS

# Import blueprints
from src.routes.user import user_bp
from src.routes.game import game_bp
# from src.routes.auth import auth_bp, login_manager # login_manager removed
from src.routes.auth import auth_bp
from src.games.jogo_123 import register_jogo_123_events
from src.games.jogo_eleitoral import register_jogo_eleitoral_events
from src.games.jogo_abundancia_fome import register_jogo_abundancia_fome_events
from src.games.jogo_zumbi import register_jogo_zumbi_events # Needs update
from src.games.jogo_corrida_cavalos_golpistas import register_corrida_cavalos_golpistas_events
from src.games.jogo_pegue_ladrao import register_pegue_ladrao_events # Needs update
from src.games.jogo_abrir_passar import register_abrir_passar_events
from src.games.jogo_dilema_kong import register_dilema_kong_events
from src.games.jogo_leilao_expressao import register_leilao_expressao_events # Needs update
from src.games.jogo_corrida_cavalos_confinados import register_corrida_cavalos_confinados_events
from src.games.jogo_5_5 import register_jogo_5_5_events
from src.games.jogo_final import register_jogo_final_events # Needs update

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
# Configure CORS
CORS(app, resources={r"/api/*": {"origins": "*"}}) # TODO: Ajuste as origens permitidas em produção!
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_very_secret_key_that_should_be_changed_in_production')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # Mitigate CSRF

# --- JWT Configuration --- 
app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY', 'another_secret_key_for_jwt_change_this') # Change this!
jwt = JWTManager(app)

# Initialize SocketIO
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*") # Adjust CORS for production

# --- Database Configuration --- 
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'instance', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# --- Flask-Login Initialization (Removed) ---
# login_manager.init_app(app)
# login_manager.login_view = None # API-based, no redirect needed

# Create database tables if they don't exist
with app.app_context():
    logger.info("Creating database tables...")
    from src.models import user, game 
    db.create_all()
    logger.info("Database tables created (if they didn't exist).")

# --- Blueprints --- 
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(game_bp, url_prefix='/api/game')
app.register_blueprint(auth_bp, url_prefix='/api/auth') # Register the auth blueprint

# --- Static File Serving --- 
@app.route('/', defaults={'path': ''}) 
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        logger.error("Static folder not configured")
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            logger.error("index.html not found in static folder")
            return "index.html not found", 404

# --- SocketIO Authentication & Event Handlers (JWT Based) --- 

# Store mapping of SID to authenticated User ID
# This replaces the old sid_user_map and authenticate_socket event
socket_sessions = {}

@socketio.on('connect')
def handle_connect(auth):
    """Handles new SocketIO connections and authenticates using JWT."""
    token = auth.get('token') if isinstance(auth, dict) else None
    sid = request.sid
    
    if not token:
        logger.warning(f"Connection attempt from {sid} without token.")
        # raise ConnectionRefusedError('Authentication token required') # Strict
        emit('auth_required', {'message': 'Token de autenticação necessário.'}, room=sid)
        disconnect(sid)
        return False # Prevent connection

    try:
        # Decode token manually to get identity without Flask request context
        # Ensure JWT_SECRET_KEY is the same as used for encoding
        decoded_token = decode_token(token)
        user_id = decoded_token['sub'] # 'sub' is the standard claim for identity
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Authentication failed for {sid}: Invalid user ID {user_id} in token.")
            # raise ConnectionRefusedError('Invalid user in token') # Strict
            emit('auth_failed', {'message': 'Usuário inválido no token.'}, room=sid)
            disconnect(sid)
            return False
            
        # Store user ID associated with this SID
        socket_sessions[sid] = user_id
        logger.info(f"Client connected and authenticated: {sid} (User ID: {user_id}, Username: {user.username})")
        emit('message', {'data': f'Conectado e autenticado como {user.username}!'}, room=sid)
        return True # Connection accepted

    except Exception as e: # Catch specific JWT errors later (ExpiredSignatureError, InvalidTokenError)
        logger.warning(f"Authentication failed for {sid}: Invalid or expired token. Error: {e}")
        # raise ConnectionRefusedError('Invalid or expired token') # Strict
        emit('auth_failed', {'message': 'Token inválido ou expirado.'}, room=sid)
        disconnect(sid)
        return False

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    logger.info(f"Client disconnected: {sid}")
    
    user_id = socket_sessions.get(sid)
    if user_id:
        # Find player by user_id and potentially room (if they were in one)
        # This logic might need adjustment if a user can be in multiple rooms (not current design)
        player = Player.query.filter_by(user_id=user_id, sid=sid).first() # Match SID too for safety
        if player:
            room_code = player.room.room_code
            username = player.user.username
            logger.info(f"Player {username} (User ID: {user_id}, SID: {sid}) disconnected from room {room_code}")
            
            # Remove player from room or mark as inactive
            # Option 1: Mark SID as None (if user might rejoin with new SID)
            # player.sid = None 
            # Option 2: Delete player record from room (if disconnect means leaving)
            db.session.delete(player)
            
            db.session.commit()
            emit('player_left', {'sid': sid, 'username': username, 'user_id': user_id}, to=room_code)
        else:
            logger.info(f"Disconnected user {user_id} (SID: {sid}) was not found in an active player session.")
    else:
        logger.warning(f"Disconnected SID {sid} had no associated user session.")
        
    # Clean up SID mapping
    if sid in socket_sessions:
        del socket_sessions[sid]

# Removed 'authenticate_socket' event

# --- Helper function to get authenticated user ID --- 
def get_authenticated_user_id(sid):
    user_id = socket_sessions.get(sid)
    if not user_id:
        logger.warning(f"Action attempted by unauthenticated SID: {sid}")
        emit('error', {'message': 'Não autenticado ou sessão expirada. Reconecte.'}, room=sid)
        return None
    return user_id

# --- Updated Event Handlers using JWT identity --- 

@socketio.on('join_room')
def on_join_room(data):
    sid = request.sid
    user_id = get_authenticated_user_id(sid)
    if not user_id:
        return
        
    room_code = data.get('room_code')
    if not room_code:
        emit('error', {'message': 'Código da sala é obrigatório.'}, room=sid)
        return

    room = GameRoom.query.filter_by(room_code=room_code).first()
    user = User.query.get(user_id)

    if not room or not user:
        emit('error', {'message': 'Código da sala ou usuário inválido.'}, room=sid)
        return

    # Check if room is full
    current_player_count = Player.query.filter_by(room_id=room.id).count()
    if current_player_count >= room.max_players:
         emit('error', {'message': f'Sala {room_code} está cheia.'}, room=sid)
         return
         
    # Check if player is already in the room (e.g., reconnecting)
    player = Player.query.filter_by(user_id=user_id, room_id=room.id).first()
    action = "already_joined"
    if not player:
        # Add new player
        player = Player(user_id=user.id, room_id=room.id, sid=sid, is_host=(room.host_id == user.id))
        db.session.add(player)
        action = "joined"
    elif player.sid != sid:
        # Update SID for reconnecting player
        logger.info(f"Player {user.username} reconnecting to room {room_code}. Updating SID from {player.sid} to {sid}.")
        player.sid = sid
        action = "rejoined"
        
    db.session.commit()
    join_room(room_code)
    username = user.username
    logger.info(f"User {username} (SID: {sid}) {action} room: {room_code}")

    # Notify others only if it's a new join
    if action == "joined":
        emit('player_joined', {'user_id': user.id, 'username': username, 'sid': sid}, to=room_code, include_self=False)
        
    # Send current room status to the joining/rejoining player
    players_in_room = Player.query.filter_by(room_id=room.id).all()
    players_in_room_list = [{
        'user_id': p.user_id, 
        'username': p.user.username, 
        'sid': p.sid, 
        'is_host': p.is_host 
        } for p in players_in_room if p.sid is not None] # Only include active players
        
    host_player = next((p for p in players_in_room if p.is_host), None)
    host_sid = host_player.sid if host_player else None
    
    emit('room_status', {
        'room_code': room.room_code, 
        'players': players_in_room_list, 
        'host_sid': host_sid, 
        'current_game_type': room.current_game_type
        }, room=sid)

@socketio.on('leave_room')
def on_leave_room(data):
    sid = request.sid
    user_id = get_authenticated_user_id(sid)
    if not user_id:
        return
        
    # Find player by user_id and sid
    player = Player.query.filter_by(user_id=user_id, sid=sid).first()
    
    if player:
        room_code = player.room.room_code
        username = player.user.username
        logger.info(f"User {username} (SID: {sid}) is leaving room: {room_code}")
        leave_room(room_code)
        db.session.delete(player) # Remove player from room
        db.session.commit()
        emit('player_left', {'sid': sid, 'username': username, 'user_id': user_id}, to=room_code)
    else:
        logger.warning(f"User ID {user_id} (SID: {sid}) attempted to leave room but was not found as an active player.")

@socketio.on('chat_message')
def handle_chat_message(json_data):
    sid = request.sid
    user_id = get_authenticated_user_id(sid)
    if not user_id:
        return
        
    room_code = json_data.get('room_code')
    message = json_data.get('message', '')
    if not room_code or not message:
        return
        
    # Verify player is in the specified room with the correct SID
    player = Player.query.filter_by(user_id=user_id, sid=sid).first()
    if player and player.room.room_code == room_code:
        username = player.user.username
        emit('chat_message', {'username': username, 'message': message, 'user_id': user_id, 'sid': sid}, to=room_code)
    else:
        logger.warning(f"Unauthorized chat message attempt from SID {sid} for room {room_code}. Player not found or room mismatch.")

@socketio.on('get_room_status')
def handle_get_room_status(data):
    sid = request.sid
    user_id = get_authenticated_user_id(sid)
    if not user_id:
        return
        
    room_code = data.get('room_code')
    if not room_code:
        emit('error', {'message': 'Código da sala necessário.'}, room=sid)
        return
        
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if room:
        # Ensure the requesting user is actually part of this room
        player = Player.query.filter_by(user_id=user_id, room_id=room.id).first()
        if player:
            players_in_room = Player.query.filter_by(room_id=room.id).all()
            players_in_room_list = [{
                'user_id': p.user_id, 
                'username': p.user.username, 
                'sid': p.sid, 
                'is_host': p.is_host
                } for p in players_in_room if p.sid is not None]
                
            host_player = next((p for p in players_in_room if p.is_host), None)
            host_sid = host_player.sid if host_player else None
            
            emit('room_status', {
                'room_code': room.room_code, 
                'players': players_in_room_list, 
                'host_sid': host_sid, 
                'current_game_type': room.current_game_type
                }, room=sid)
        else:
            emit('error', {'message': 'Você não está nesta sala.'}, room=sid)
    else:
        emit('error', {'message': f'Sala {room_code} não encontrada.'}, room=sid)

# --- Register Game Specific Logic --- 
# Pass socketio instance AND the helper function to get user_id
# Game logic files will need to be updated to accept and use get_authenticated_user_id
register_jogo_123_events(socketio, get_authenticated_user_id)
register_jogo_eleitoral_events(socketio, get_authenticated_user_id)
register_jogo_abundancia_fome_events(socketio, get_authenticated_user_id)
register_jogo_zumbi_events(socketio, get_authenticated_user_id)
register_corrida_cavalos_golpistas_events(socketio, get_authenticated_user_id)
register_pegue_ladrao_events(socketio, get_authenticated_user_id)
register_abrir_passar_events(socketio, get_authenticated_user_id)
register_dilema_kong_events(socketio, get_authenticated_user_id)
register_leilao_expressao_events(socketio, get_authenticated_user_id)
register_corrida_cavalos_confinados_events(socketio, get_authenticated_user_id)
register_jogo_5_5_events(socketio, get_authenticated_user_id)
register_jogo_final_events(socketio, get_authenticated_user_id)

# --- Main Execution --- 
if __name__ == '__main__':
    logger.info("Starting Flask-SocketIO server with eventlet...")
    # Use 0.0.0.0 to be accessible externally if needed
    # debug=True enables auto-reloader, which can cause issues with eventlet/gevent
    # use_reloader=False is important when using eventlet/gevent
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)

