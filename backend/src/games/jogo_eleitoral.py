# -*- coding: utf-8 -*-
import logging
import random
import json
import datetime
import uuid
from flask import request
from flask_socketio import emit, join_room, leave_room
from sqlalchemy.orm import joinedload # To eager load relationships

from src.models.user import db
from src.models.game import GameRoom, Player

# Assuming helper functions are refactored into a common module later
# For now, copy/adapt necessary helpers
from .jogo_123 import get_room_and_game_state as get_base_room_and_state, update_and_emit_state as base_update_and_emit

logger = logging.getLogger(__name__)

GAME_NAME = "Jogo Eleitoral"
CANDIDACY_DECLARATION_SECONDS = 5 * 60 # 5 minutes
GAME_DURATION_SECONDS = 90 * 60 # 90 minutes (total, includes declaration)
POLL_INTERVAL_SECONDS = 30 * 60 # 30 minutes
INITIAL_CHIPS_PER_CANDIDATE = 20

# --- Helper Functions (Specific or Overridden) ---

def get_room_and_game_state(room_code):
    """Fetches room and game state specifically for Jogo Eleitoral."""
    room, game_state = get_base_room_and_state(room_code)
    if room and game_state and game_state.get("game_name") != GAME_NAME:
        logger.warning(f'[{GAME_NAME}] Room {room_code} has state for {game_state.get("game_name")}, not {GAME_NAME}. Resetting.')
        game_state = {} # Reset if wrong game
    if room and not game_state: # Initialize basic structure if empty
         game_state = {"game_name": GAME_NAME, "status": "loading"}
         
    # Ensure election-specific keys exist
    game_state.setdefault("players", {})
    game_state.setdefault("candidates", []) # List of player_ids
    game_state.setdefault("voters", []) # List of player_ids
    game_state.setdefault("polls", []) # List of poll results {time, results: {candidate_id: votes}}
    game_state.setdefault("final_votes", {}) # {voter_id: candidate_id}
    return room, game_state

def update_and_emit_state(socketio, room_code, game_state):
    """Updates and emits state for Jogo Eleitoral."""
    room = GameRoom.query.options(joinedload(GameRoom.players).joinedload(Player.user)).filter_by(room_code=room_code).first()
    if not room:
        return

    try:
        room.game_state = json.dumps(game_state)
        db.session.commit()
        logger.debug(f"[{GAME_NAME}] Game state updated for room {room_code}.")
    except Exception as e:
        db.session.rollback()
        logger.error(f"[{GAME_NAME}] Failed to update game state for room {room_code}: {e}")
        socketio.emit("error", {"message": "Internal server error saving game state."}, to=room_code)
        return

    players_state = game_state.get("players", {})
    if not isinstance(players_state, dict):
        players_state = {}

    # Emit public state
    public_state = {
        "game_name": game_state.get("game_name"),
        "status": game_state.get("status"),
        "start_time": game_state.get("start_time"),
        "declaration_end_time": game_state.get("declaration_end_time"),
        "voting_end_time": game_state.get("voting_end_time"),
        "candidates": game_state.get("candidates", []),
        "voters": game_state.get("voters", []),
        "polls": game_state.get("polls", []),
        # Only show player info (username, status), not chips or votes publicly
        "players": {pid: {"username": pdata.get("username"), "status": pdata.get("status"), "is_candidate": pdata.get("is_candidate", False)} 
                    for pid, pdata in players_state.items() if isinstance(pdata, dict)},
    }
    socketio.emit(f"{GAME_NAME}_update_state", public_state, to=room_code)

    # Emit private state to each player
    for player_id_str, player_data in players_state.items():
        if not isinstance(player_data, dict): continue
        try:
            player_id = int(player_id_str)
        except ValueError:
            continue
            
        player_obj = next((p for p in room.players if p.user_id == player_id), None)
        if player_obj and player_obj.sid:
            private_state = {
                "chips": player_data.get("chips", 0),
                "my_vote": game_state.get("final_votes", {}).get(player_id_str), # Show who they voted for
                "is_candidate": player_data.get("is_candidate", False),
                "can_declare": game_state.get("status") == "declaration" and player_id not in game_state.get("candidates", [])
                # Add other relevant private info if needed
            }
            socketio.emit(f"{GAME_NAME}_update_private_state", private_state, room=player_obj.sid)

# --- Game Initialization ---

def initialize_game(room_code):
    """Initializes the state for Jogo Eleitoral."""
    room = GameRoom.query.options(joinedload(GameRoom.players).joinedload(Player.user)).filter_by(room_code=room_code).first()
    if not room:
        logger.error(f"[{GAME_NAME}] Cannot initialize game for room {room_code}. Room not found.")
        return None
        
    room.game_type = GAME_NAME
    players = room.players
    # Rule check: How many players needed? Assume at least 3 (1 cand, 2 voters?)
    if len(players) < 3:
        logger.warning(f"[{GAME_NAME}] Not enough players ({len(players)}) to start in room {room_code}.")
        return None

    now = datetime.datetime.utcnow()
    declaration_end_time = now + datetime.timedelta(seconds=CANDIDACY_DECLARATION_SECONDS)
    voting_end_time = now + datetime.timedelta(seconds=GAME_DURATION_SECONDS)

    game_state = {
        "game_name": GAME_NAME,
        "status": "declaration", # declaration -> campaigning -> voting -> finished
        "start_time": now.isoformat(),
        "declaration_end_time": declaration_end_time.isoformat(),
        "voting_end_time": voting_end_time.isoformat(),
        "next_poll_time": (now + datetime.timedelta(seconds=POLL_INTERVAL_SECONDS)).isoformat(),
        "players": {},
        "candidates": [],
        "voters": [], # Populated after declaration phase
        "polls": [],
        "final_votes": {}
    }

    for player in players:
        game_state["players"][str(player.user_id)] = {
            "username": player.user.username,
            "chips": 0, # Start with 0, candidates get chips later
            "status": "active",
            "is_candidate": False
        }
        player.score = 0 # Reset score if needed
        player.inventory = json.dumps({"chips": 0})
        player.status = "active"

    room.status = "in_progress"
    try:
        room.game_state = json.dumps(game_state)
        db.session.commit()
        logger.info(f"[{GAME_NAME}] Game initialized and ready for room {room_code}. Status: declaration.")
        return game_state
    except Exception as e:
        db.session.rollback()
        logger.error(f"[{GAME_NAME}] Failed to save initial game state for room {room_code}: {e}")
        return None

# --- End Declaration Phase Logic ---
def end_declaration_phase(socketio, room_code):
     with socketio.app.app_context(): # Ensure context for DB access
        logger.info(f"[{GAME_NAME}] Ending declaration phase for room {room_code}.")
        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "declaration":
            logger.warning(f'[{GAME_NAME}] Cannot end declaration phase for room {room_code}. Status is {game_state.get("status")}.')
            return

        candidates = game_state.get("candidates", [])
        players_state = game_state.get("players", {})
        all_player_ids = [int(pid) for pid in players_state.keys()]

        # If no candidates, maybe end game or force someone?
        if not candidates:
            logger.warning(f"[{GAME_NAME}] No candidates declared in room {room_code}. Ending game.")
            game_state["status"] = "finished"
            # TODO: Determine winner/loser based on rules for no candidates
            update_and_emit_state(socketio, room_code, game_state)
            socketio.emit(f"{GAME_NAME}_game_over", {"message": "Game Over! No candidates declared."}, to=room_code)
            room.status = "finished"
            db.session.commit()
            return

        # Assign chips to candidates and identify voters
        voters = []
        for player_id_str, player_data in players_state.items():
            player_id = int(player_id_str)
            if player_id in candidates:
                player_data["chips"] = INITIAL_CHIPS_PER_CANDIDATE
                player_data["is_candidate"] = True
            else:
                voters.append(player_id)
                player_data["is_candidate"] = False
        
        game_state["voters"] = voters
        game_state["status"] = "campaigning" # Move to next phase
        logger.info(f"[{GAME_NAME}] Declaration phase ended. Candidates: {candidates}, Voters: {voters}. Status: campaigning.")
        update_and_emit_state(socketio, room_code, game_state)
        # TODO: Schedule first poll?
        # TODO: Schedule end of voting?

# --- SocketIO Event Handlers ---

def register_jogo_eleitoral_events(socketio, get_authenticated_user_id):
    """Registers SocketIO event handlers specific to Jogo Eleitoral."""
    logger.info(f"Registering {GAME_NAME} events...")

    @socketio.on(f'start_{GAME_NAME.lower().replace(" ", "_")}')
    def handle_start_game(data):
        room_code = data.get("room_code")
        user_sid = request.sid
        player = Player.query.filter_by(sid=user_sid, room_code=room_code).first()
        
        if not player:
            emit("error", {"message": "Player not found in this room."}, room=user_sid)
            return

        room, game_state = get_room_and_game_state(room_code)
        if not room:
            emit("error", {"message": f"Room {room_code} not found."}, room=user_sid)
            return
        
        if room.host_id != player.user_id:
            emit("error", {"message": "Only the host can start the game."}, room=user_sid)
            return
            
        current_game_status = game_state.get("status")
        if room.status == "in_progress" and current_game_status not in ["finished", "loading", None, "starting"]:
            emit("error", {"message": f"Game already in progress ({current_game_status}) in room {room_code}."}, room=user_sid)
            return

        logger.info(f"[{GAME_NAME}] Attempting to start game in room {room_code} by host {player.user_id}.")
        new_game_state = initialize_game(room_code)

        if new_game_state:
            logger.info(f"[{GAME_NAME}] Game started successfully in room {room_code}. Status: declaration.")
            update_and_emit_state(socketio, room_code, new_game_state)
            # Schedule end of declaration phase
            declaration_end_iso = new_game_state.get("declaration_end_time")
            if declaration_end_iso:
                end_time = datetime.datetime.fromisoformat(declaration_end_iso)
                delay = (end_time - datetime.datetime.utcnow()).total_seconds()
                if delay > 0:
                    logger.info(f"[{GAME_NAME}] Scheduling end of declaration phase in {delay:.1f} seconds.")
                    socketio.start_background_task(target=socketio.sleep, seconds=delay)
                    socketio.start_background_task(target=end_declaration_phase, socketio=socketio, room_code=room_code)
                else:
                    # If time already passed, end immediately (shouldn't happen often)
                    logger.warning(f"[{GAME_NAME}] Declaration end time already passed. Ending phase immediately.")
                    socketio.start_background_task(target=end_declaration_phase, socketio=socketio, room_code=room_code)
            # TODO: Schedule polls and game end based on other timers
        else:
            logger.error(f"[{GAME_NAME}] Failed to initialize game state for room {room_code}.")
            emit("error", {"message": "Failed to start game. Not enough players?"}, to=room_code)

    @socketio.on(f"{GAME_NAME}_declare_candidacy")
    def handle_declare_candidacy(data):
        room_code = data.get("room_code")
        player_id = data.get("user_id") # ID of player declaring
        user_sid = request.sid

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state:
            emit("error", {"message": "Game/Room not found."}, room=user_sid)
            return

        # Check phase and time
        if game_state.get("status") != "declaration":
            emit("error", {"message": "Cannot declare candidacy now."}, room=user_sid)
            return
        declaration_end_time = datetime.datetime.fromisoformat(game_state.get("declaration_end_time"))
        if datetime.datetime.utcnow() > declaration_end_time:
             emit("error", {"message": "Declaration phase is over."}, room=user_sid)
             return

        # Validate player
        requesting_player = Player.query.filter_by(sid=user_sid, room_code=room_code).first()
        if not requesting_player or requesting_player.user_id != player_id:
            emit("error", {"message": "Invalid player ID."}, room=user_sid)
            return
        if player_id in game_state.get("candidates", []):
            emit("error", {"message": "You are already a candidate."}, room=user_sid)
            return

        # Add player to candidates list
        game_state.setdefault("candidates", []).append(player_id)
        logger.info(f"[{GAME_NAME}] Player {player_id} declared candidacy in room {room_code}.")
        update_and_emit_state(socketio, room_code, game_state)
        emit(f"{GAME_NAME}_candidacy_declared", {"player_id": player_id}, room=user_sid) # Confirmation

    # TODO: Implement other handlers:
    # - give_chips (sender_id(candidate), receiver_id(voter), amount)
    # - conduct_poll (maybe triggered by timer?)
    # - withdraw_candidacy (candidate_id)
    # - cast_vote (voter_id, candidate_id)
    # - end_game (triggered by timer)

    @socketio.on(f"{GAME_NAME}_get_state")
    def handle_get_state(data):
        room_code = data.get("room_code")
        user_sid = request.sid
        player = Player.query.filter_by(sid=user_sid, room_code=room_code).first()

        if not player:
            emit("error", {"message": "Player not found in this room."}, room=user_sid)
            return
            
        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state:
            emit("error", {"message": "Game state not found or invalid."}, room=user_sid)
            return

        logger.info(f"[{GAME_NAME}] User {player.user_id} requested state for room {room_code}.")
        update_and_emit_state(socketio, room_code, game_state)

    logger.info(f"{GAME_NAME} events registered.")

# --- Placeholder for Timer-Based Actions ---
# def conduct_poll_logic(socketio, room_code):
#     with socketio.app.app_context():
#         # ... fetch state, simulate votes based on chips/strategy?, record poll, emit results ...
#         pass

# def end_voting_logic(socketio, room_code):
#     with socketio.app.app_context():
#         # ... fetch state, count votes, determine winner/loser, convert chips, emit game over ...
#         pass

