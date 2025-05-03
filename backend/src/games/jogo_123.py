# -*- coding: utf-8 -*-
import logging
import random
import json
import datetime
import uuid # Import uuid for challenge/trade IDs
from flask import request
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User # Import User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

GAME_NAME = "Jogo 1-2-3"
GAME_DURATION_SECONDS = 90 * 60 # 90 minutes
INITIAL_CARDS = [1, 1, 1, 2, 2, 2, 3, 3, 3]

# --- Helper Functions (No auth changes needed here) ---

def get_room_and_game_state(room_code):
    """Fetches the room and parses its game state."""
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        logger.error(f"[{GAME_NAME}] Room {room_code} not found.")
        return None, None
    try:
        game_state = json.loads(room.game_state) if room.game_state else {}
        if not isinstance(game_state, dict):
             logger.error(f"[{GAME_NAME}] Invalid game state format for room {room_code}. Resetting.")
             game_state = {}
    except json.JSONDecodeError:
        logger.error(f"[{GAME_NAME}] Failed to decode game state for room {room_code}. Resetting.")
        game_state = {}
    # Ensure essential keys exist
    game_state.setdefault("players", {})
    game_state.setdefault("challenges", {})
    game_state.setdefault("duels", {})
    game_state.setdefault("trades", {})
    return room, game_state

def update_and_emit_state(socketio, room_code, game_state):
    """Updates the game state in DB and emits public/private states."""
    room = GameRoom.query.filter_by(room_code=room_code).first()
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
        logger.warning(f"[{GAME_NAME}] Players state was not a dict for room {room_code}. Corrected.")

    # Emit public state to the room
    public_state = {
        "game_name": game_state.get("game_name"),
        "status": game_state.get("status"),
        "round": game_state.get("round"),
        "players": {pid: {"username": pdata.get("username"), "score": pdata.get("score", 0), "status": pdata.get("status")} 
                    for pid, pdata in players_state.items() if isinstance(pdata, dict)},
        "active_duels": {
            duel_id: {
                "player1_id": d.get("player1_id"), 
                "player2_id": d.get("player2_id"), 
                "status": d.get("status")
            }
            for duel_id, d in game_state.get("duels", {}).items() 
            if d.get("status") in ["waiting_cards", "waiting_p1", "waiting_p2"]
        }
        # Add active trades info if needed publicly?
    }
    socketio.emit(f"{GAME_NAME}_update_state", public_state, to=room_code)

    # Emit private state to each player
    for player_id_str, player_data in players_state.items():
        if not isinstance(player_data, dict): continue
        try:
            player_id = int(player_id_str)
        except ValueError:
            continue
            
        # Find the player object using user_id and room_id to get the SID
        player_obj = Player.query.filter_by(user_id=player_id, room_id=room.id).first()
        if player_obj and player_obj.sid:
            challenges = game_state.get("challenges", {})
            duels = game_state.get("duels", {})
            trades = game_state.get("trades", {})
            players = game_state.get("players", {})

            pending_challenges_sent = [
                {"challenge_id": cid, "challenged_id": cdata["challenged_id"]}
                for cid, cdata in challenges.items()
                if cdata.get("challenger_id") == player_id and cdata.get("status") == "pending"
            ]
            pending_challenges_received = [
                 {"challenge_id": cid, "challenger_id": cdata["challenger_id"], "challenger_username": players.get(str(cdata.get("challenger_id")), {}).get("username")}
                 for cid, cdata in challenges.items()
                 if cdata.get("challenged_id") == player_id and cdata.get("status") == "pending"
            ]
            active_duels = [
                {"duel_id": did, 
                 "opponent_id": ddata["player2_id"] if ddata["player1_id"] == player_id else ddata["player1_id"], 
                 "status": ddata["status"],
                 "my_card_played": ddata.get("card1") is not None if ddata.get("player1_id") == player_id else ddata.get("card2") is not None
                 }
                for did, ddata in duels.items()
                if (ddata.get("player1_id") == player_id or ddata.get("player2_id") == player_id) and ddata.get("status") in ["waiting_cards", "waiting_p1", "waiting_p2"]
            ]
            pending_trades_sent = [
                {"trade_id": tid, "receiver_id": tdata["receiver_id"], "offered_card": tdata["offered_card"], "requested_card": tdata["requested_card"]}
                for tid, tdata in trades.items()
                if tdata.get("sender_id") == player_id and tdata.get("status") == "pending"
            ]
            pending_trades_received = [
                 {"trade_id": tid, "sender_id": tdata["sender_id"], "sender_username": players.get(str(tdata.get("sender_id")), {}).get("username"), "offered_card": tdata["offered_card"], "requested_card": tdata["requested_card"]}
                 for tid, tdata in trades.items()
                 if tdata.get("receiver_id") == player_id and tdata.get("status") == "pending"
            ]

            private_state = {
                "hand": player_data.get("hand", []),
                "score": player_data.get("score", 0),
                "pending_challenges_sent": pending_challenges_sent,
                "pending_challenges_received": pending_challenges_received,
                "active_duels": active_duels,
                "pending_trades_sent": pending_trades_sent,
                "pending_trades_received": pending_trades_received
            }
            socketio.emit(f"{GAME_NAME}_update_private_state", private_state, room=player_obj.sid)

# --- Game Initialization (No auth changes needed here) ---

def initialize_game(room_code):
    """Initializes the state for Jogo 1-2-3."""
    room = GameRoom.query.filter_by(room_code=room_code).first()
    if not room:
        logger.error(f"[{GAME_NAME}] Cannot initialize game for room {room_code}. Room not found.")
        return None
        
    room.game_type = GAME_NAME

    players = room.players # Fetch Player objects
    active_players = [p for p in players if p.sid is not None]
    if len(active_players) < 2:
        logger.warning(f"[{GAME_NAME}] Not enough active players ({len(active_players)}) to start in room {room_code}.")
        return None

    game_state = {
        "game_name": GAME_NAME,
        "status": "starting",
        "round": 0,
        "start_time": None,
        "end_time": None,
        "players": {},
        "challenges": {}, # {challenge_id: {challenger_id, challenged_id, status}}
        "duels": {}, # {duel_id: {player1_id, player2_id, card1, card2, status, winner_id, loser_id}}
        "trades": {} # {trade_id: {sender_id, receiver_id, offered_card, requested_card, status}}
    }

    for player in active_players:
        hand = list(INITIAL_CARDS)
        random.shuffle(hand)
        game_state["players"][str(player.user_id)] = {
            "username": player.user.username,
            "score": 0,
            "hand": hand,
            "cards_used": [],
            "status": "active" # Mark as active in game state
        }
        # Update Player model if needed (optional, game_state is primary)
        # player.score = 0
        # player.inventory = json.dumps({"hand": hand})
        # player.status = "active"

    room.status = "in_progress"
    try:
        room.game_state = json.dumps(game_state)
        db.session.commit()
        logger.info(f"[{GAME_NAME}] Game initialized and ready for room {room_code}.")
        return game_state
    except Exception as e:
        db.session.rollback()
        logger.error(f"[{GAME_NAME}] Failed to save initial game state for room {room_code}: {e}")
        return None

# --- SocketIO Event Handlers ---

def register_jogo_123_events(socketio, get_authenticated_user_id):
    """Registers SocketIO event handlers specific to Jogo 1-2-3."""
    logger.info(f"Registering {GAME_NAME} events...")

    @socketio.on(f"start_{GAME_NAME.lower().replace(' ', '_')}")
    def handle_start_game(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return # Error emitted by get_authenticated_user_id

        room_code = data.get("room_code")
        room, game_state = get_room_and_game_state(room_code)
        if not room:
            emit("error", {"message": f"Room {room_code} not found."}, room=sid)
            return
        
        # Check if the authenticated user is the host
        if room.host_id != user_id:
            emit("error", {"message": "Only the host can start the game."}, room=sid)
            return
            
        current_game_status = game_state.get("status")
        if room.status == "in_progress" and current_game_status == "in_progress":
            emit("error", {"message": f"Game already in progress in room {room_code}."}, room=sid)
            return

        logger.info(f"[{GAME_NAME}] Attempting to start game in room {room_code} by host {user_id}.")
        new_game_state = initialize_game(room_code)

        if new_game_state:
            now = datetime.datetime.utcnow()
            new_game_state["start_time"] = now.isoformat()
            new_game_state["end_time"] = (now + datetime.timedelta(seconds=GAME_DURATION_SECONDS)).isoformat()
            new_game_state["status"] = "in_progress"
            
            logger.info(f"[{GAME_NAME}] Game started successfully in room {room_code}.")
            update_and_emit_state(socketio, room_code, new_game_state)
            # TODO: Schedule game end logic
        else:
            logger.error(f"[{GAME_NAME}] Failed to initialize game state for room {room_code}.")
            emit("error", {"message": "Failed to start game. Not enough active players?"}, to=room_code)

    @socketio.on(f"{GAME_NAME}_challenge_player")
    def handle_challenge_player(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        # challenger_id = data.get("challenger_id") # Use authenticated user_id instead
        challenged_id = data.get("challenged_id")
        
        try: # Validate challenged_id is an integer
            challenged_id = int(challenged_id)
        except (ValueError, TypeError):
             emit("error", {"message": "Invalid challenged player ID format."}, room=sid)
             return

        logger.info(f"[{GAME_NAME}] Received challenge from {user_id} to {challenged_id} in room {room_code}.")

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "in_progress":
            emit("error", {"message": "Game not active or room not found."}, room=sid)
            return

        players_state = game_state.get("players", {})
        challenger_data = players_state.get(str(user_id))
        challenged_data = players_state.get(str(challenged_id))
        
        # Check if authenticated user is part of the game
        if str(user_id) not in players_state:
             emit("error", {"message": "Invalid action: You are not part of this game."}, room=sid)
             return

        if not challenger_data or challenger_data.get("status") != "active":
            emit("error", {"message": "Invalid challenger or challenger not active."}, room=sid)
            return
        if not challenged_data or challenged_data.get("status") != "active":
            emit("error", {"message": "Invalid challenged player or player not active."}, room=sid)
            return
        if user_id == challenged_id:
            emit("error", {"message": "Cannot challenge yourself."}, room=sid)
            return
        if not challenger_data.get("hand"): 
             emit("error", {"message": "You have no cards left to challenge."}, room=sid)
             return
        if not challenged_data.get("hand"): 
             emit("error", {"message": f"{challenged_data.get('username', 'Player')} has no cards left." }, room=sid)
             return
             
        challenge_id = str(uuid.uuid4())
        game_state.setdefault("challenges", {})[challenge_id] = {
            "challenger_id": user_id, # Use authenticated user_id
            "challenged_id": challenged_id,
            "status": "pending"
        }

        update_and_emit_state(socketio, room_code, game_state)

        challenged_player_obj = Player.query.filter_by(user_id=challenged_id, room_id=room.id).first()
        if challenged_player_obj and challenged_player_obj.sid:
            emit(f"{GAME_NAME}_challenge_received", {
                "challenge_id": challenge_id,
                "challenger_id": user_id,
                "challenger_username": challenger_data.get("username")
            }, room=challenged_player_obj.sid)
            logger.info(f"[{GAME_NAME}] Challenge {challenge_id} sent to challenged player {challenged_id}.")
        else:
            logger.warning(f"[{GAME_NAME}] Challenged player {challenged_id} not found or not connected. Challenge {challenge_id} pending.")

        emit(f"{GAME_NAME}_challenge_sent", {"challenge_id": challenge_id, "challenged_id": challenged_id}, room=sid)
        logger.info(f"[{GAME_NAME}] Challenge {challenge_id} confirmed sent to challenger {user_id}.")

    @socketio.on(f"{GAME_NAME}_respond_challenge")
    def handle_respond_challenge(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        challenge_id = data.get("challenge_id")
        response = data.get("response") # "accept" or "reject"

        logger.info(f"[{GAME_NAME}] Received response \'{response}\' for challenge {challenge_id} from user {user_id} in room {room_code}.")

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "in_progress":
            emit("error", {"message": "Game not active or room not found."}, room=sid)
            return

        challenges = game_state.get("challenges", {})
        challenge_data = challenges.get(challenge_id)
        if not challenge_data or challenge_data.get("status") != "pending":
            emit("error", {"message": "Invalid or expired challenge."}, room=sid)
            return

        challenged_id = challenge_data.get("challenged_id")
        challenger_id = challenge_data.get("challenger_id")

        # Check if the authenticated user is the challenged player
        if user_id != challenged_id:
            emit("error", {"message": "You are not the challenged player."}, room=sid)
            return

        challenger_player_obj = Player.query.filter_by(user_id=challenger_id, room_id=room.id).first()

        if response == "accept":
            players_state = game_state.get("players", {})
            challenger_hand = players_state.get(str(challenger_id), {}).get("hand", [])
            challenged_hand = players_state.get(str(challenged_id), {}).get("hand", [])
            if not challenger_hand or not challenged_hand:
                 emit("error", {"message": "One or both players have no cards left for the duel."}, room=sid)
                 challenge_data["status"] = "rejected"
                 update_and_emit_state(socketio, room_code, game_state)
                 if challenger_player_obj and challenger_player_obj.sid:
                     emit(f"{GAME_NAME}_challenge_result", {"challenge_id": challenge_id, "status": "rejected", "reason": "No cards left"}, room=challenger_player_obj.sid)
                 return

            challenge_data["status"] = "accepted"
            duel_id = str(uuid.uuid4())
            game_state.setdefault("duels", {})[duel_id] = {
                "player1_id": challenger_id,
                "player2_id": challenged_id,
                "card1": None,
                "card2": None,
                "status": "waiting_cards", # Both players need to select a card
                "winner_id": None,
                "loser_id": None
            }
            logger.info(f"[{GAME_NAME}] Challenge {challenge_id} accepted. Duel {duel_id} created between {challenger_id} and {challenged_id}.")
            # Notify both players about the duel start
            duel_info = {"duel_id": duel_id, "opponent_id": challenged_id, "status": "waiting_cards"}
            if challenger_player_obj and challenger_player_obj.sid:
                emit(f"{GAME_NAME}_duel_start", duel_info, room=challenger_player_obj.sid)
            duel_info["opponent_id"] = challenger_id
            emit(f"{GAME_NAME}_duel_start", duel_info, room=sid) # Emit to challenged player (current user)

        elif response == "reject":
            challenge_data["status"] = "rejected"
            logger.info(f"[{GAME_NAME}] Challenge {challenge_id} rejected by {user_id}.")
            # Notify challenger
            if challenger_player_obj and challenger_player_obj.sid:
                emit(f"{GAME_NAME}_challenge_result", {"challenge_id": challenge_id, "status": "rejected"}, room=challenger_player_obj.sid)
        else:
            emit("error", {"message": "Invalid response."}, room=sid)
            return

        update_and_emit_state(socketio, room_code, game_state)

    @socketio.on(f"{GAME_NAME}_play_card_duel")
    def handle_play_card_duel(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        duel_id = data.get("duel_id")
        card = data.get("card")

        logger.info(f"[{GAME_NAME}] User {user_id} attempting to play card {card} for duel {duel_id} in room {room_code}.")

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "in_progress":
            emit("error", {"message": "Game not active or room not found."}, room=sid)
            return

        duels = game_state.get("duels", {})
        duel_data = duels.get(duel_id)
        if not duel_data or duel_data.get("status") not in ["waiting_cards", "waiting_p1", "waiting_p2"]:
            emit("error", {"message": "Invalid or finished duel."}, room=sid)
            return

        player1_id = duel_data.get("player1_id")
        player2_id = duel_data.get("player2_id")

        # Determine if user is player1 or player2
        is_player1 = (user_id == player1_id)
        is_player2 = (user_id == player2_id)

        if not is_player1 and not is_player2:
            emit("error", {"message": "You are not part of this duel."}, room=sid)
            return

        players_state = game_state.get("players", {})
        player_data = players_state.get(str(user_id))
        if not player_data or not isinstance(player_data.get("hand"), list):
             emit("error", {"message": "Player data or hand not found."}, room=sid)
             return

        try:
            card_value = int(card)
            if card_value not in player_data["hand"]:
                emit("error", {"message": f"Card {card_value} not in your hand."}, room=sid)
                return
        except (ValueError, TypeError):
            emit("error", {"message": "Invalid card value."}, room=sid)
            return

        # Check if card already played by this player
        if (is_player1 and duel_data.get("card1") is not None) or \
           (is_player2 and duel_data.get("card2") is not None):
            emit("error", {"message": "You have already played a card for this duel."}, room=sid)
            return

        # Update duel state with played card
        if is_player1:
            duel_data["card1"] = card_value
            duel_data["status"] = "waiting_p2" if duel_data.get("card2") is None else "revealing"
        else: # is_player2
            duel_data["card2"] = card_value
            duel_data["status"] = "waiting_p1" if duel_data.get("card1") is None else "revealing"

        # Remove card from player's hand and add to used cards
        player_data["hand"].remove(card_value)
        player_data.setdefault("cards_used", []).append(card_value)
        logger.info(f"[{GAME_NAME}] User {user_id} played card {card_value}. Hand: {player_data['hand']}")

        emit(f"{GAME_NAME}_card_played", {"duel_id": duel_id}, room=sid) # Confirm card played

        # If both players have played, resolve the duel
        if duel_data["status"] == "revealing":
            card1 = duel_data["card1"]
            card2 = duel_data["card2"]
            winner_id, loser_id = None, None
            result_text = ""

            if card1 > card2:
                winner_id, loser_id = player1_id, player2_id
                result_text = f'Player {player1_id} wins ({card1} > {card2})'
            elif card2 > card1:
                winner_id, loser_id = player2_id, player1_id
                result_text = f'Player {player2_id} wins ({card2} > {card1})'
            else: # Tie
                # Both lose? Or replay? Rules unclear. Assume both lose points/cards?
                # For now, let's say no score change on tie, but cards are lost.
                winner_id, loser_id = None, None # Indicate tie
                result_text = f"Tie ({card1} == {card2})"
                duel_data["status"] = "tie"

            if winner_id and loser_id:
                duel_data["status"] = "finished"
                duel_data["winner_id"] = winner_id
                duel_data["loser_id"] = loser_id
                # Update scores
                winner_data = players_state.get(str(winner_id))
                loser_data = players_state.get(str(loser_id))
                if winner_data:
                    winner_data["score"] = winner_data.get("score", 0) + 1
                # No points deducted for loser in this version
                logger.info(f"[{GAME_NAME}] Duel {duel_id} finished. {result_text}. Winner: {winner_id}, Loser: {loser_id}")
            else: # Tie
                 logger.info(f"[{GAME_NAME}] Duel {duel_id} finished. {result_text}.")

            # Notify both players of the result
            result_data = {
                "duel_id": duel_id,
                "status": duel_data["status"],
                "your_card": card1 if is_player1 else card2,
                "opponent_card": card2 if is_player1 else card1,
                "winner_id": winner_id,
                "loser_id": loser_id
            }
            # Find SIDs to emit results
            p1_obj = Player.query.filter_by(user_id=player1_id, room_id=room.id).first()
            p2_obj = Player.query.filter_by(user_id=player2_id, room_id=room.id).first()
            if p1_obj and p1_obj.sid:
                 emit(f"{GAME_NAME}_duel_result", result_data, room=p1_obj.sid)
            if p2_obj and p2_obj.sid:
                 emit(f"{GAME_NAME}_duel_result", result_data, room=p2_obj.sid)

        update_and_emit_state(socketio, room_code, game_state)

    # --- Trade Handlers --- 
    @socketio.on(f"{GAME_NAME}_propose_trade")
    def handle_propose_trade(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        receiver_id = data.get("receiver_id")
        offered_card = data.get("offered_card")
        requested_card = data.get("requested_card")

        logger.info(f"[{GAME_NAME}] User {user_id} proposing trade with {receiver_id} in room {room_code}: Offer {offered_card} for {requested_card}.")

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "in_progress":
            emit("error", {"message": "Game not active or room not found."}, room=sid)
            return

        try: # Validate IDs and cards
            receiver_id = int(receiver_id)
            offered_card = int(offered_card)
            requested_card = int(requested_card)
            if offered_card not in [1, 2, 3] or requested_card not in [1, 2, 3]:
                 raise ValueError("Invalid card value")
        except (ValueError, TypeError):
             emit("error", {"message": "Invalid player ID or card value format."}, room=sid)
             return

        players_state = game_state.get("players", {})
        sender_data = players_state.get(str(user_id))
        receiver_data = players_state.get(str(receiver_id))

        if str(user_id) not in players_state:
             emit("error", {"message": "Invalid action: You are not part of this game."}, room=sid)
             return
        if not sender_data or sender_data.get("status") != "active":
            emit("error", {"message": "Invalid sender or sender not active."}, room=sid)
            return
        if not receiver_data or receiver_data.get("status") != "active":
            emit("error", {"message": "Invalid receiver or receiver not active."}, room=sid)
            return
        if user_id == receiver_id:
            emit("error", {"message": "Cannot trade with yourself."}, room=sid)
            return
        if offered_card not in sender_data.get("hand", []):
             emit("error", {"message": f"Offered card {offered_card} not in your hand."}, room=sid)
             return
             
        trade_id = str(uuid.uuid4())
        game_state.setdefault("trades", {})[trade_id] = {
            "sender_id": user_id,
            "receiver_id": receiver_id,
            "offered_card": offered_card,
            "requested_card": requested_card,
            "status": "pending"
        }

        update_and_emit_state(socketio, room_code, game_state)

        receiver_player_obj = Player.query.filter_by(user_id=receiver_id, room_id=room.id).first()
        if receiver_player_obj and receiver_player_obj.sid:
            emit(f"{GAME_NAME}_trade_received", {
                "trade_id": trade_id,
                "sender_id": user_id,
                "sender_username": sender_data.get("username"),
                "offered_card": offered_card,
                "requested_card": requested_card
            }, room=receiver_player_obj.sid)
            logger.info(f"[{GAME_NAME}] Trade {trade_id} sent to receiver {receiver_id}.")
        else:
            logger.warning(f"[{GAME_NAME}] Trade receiver {receiver_id} not found or not connected. Trade {trade_id} pending.")

        emit(f"{GAME_NAME}_trade_sent", {"trade_id": trade_id, "receiver_id": receiver_id}, room=sid)
        logger.info(f"[{GAME_NAME}] Trade {trade_id} confirmed sent to sender {user_id}.")

    @socketio.on(f"{GAME_NAME}_respond_trade")
    def handle_respond_trade(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        trade_id = data.get("trade_id")
        response = data.get("response") # "accept" or "reject"

        logger.info(f"[{GAME_NAME}] User {user_id} responding \'{response}\' to trade {trade_id} in room {room_code}.")

        room, game_state = get_room_and_game_state(room_code)
        if not room or not game_state or game_state.get("status") != "in_progress":
            emit("error", {"message": "Game not active or room not found."}, room=sid)
            return

        trades = game_state.get("trades", {})
        trade_data = trades.get(trade_id)
        if not trade_data or trade_data.get("status") != "pending":
            emit("error", {"message": "Invalid or expired trade."}, room=sid)
            return

        receiver_id = trade_data.get("receiver_id")
        sender_id = trade_data.get("sender_id")

        # Check if the authenticated user is the receiver
        if user_id != receiver_id:
            emit("error", {"message": "You are not the receiver of this trade."}, room=sid)
            return

        sender_player_obj = Player.query.filter_by(user_id=sender_id, room_id=room.id).first()
        players_state = game_state.get("players", {})
        sender_data = players_state.get(str(sender_id))
        receiver_data = players_state.get(str(receiver_id))

        if not sender_data or not receiver_data:
             emit("error", {"message": "Sender or receiver data not found."}, room=sid)
             trade_data["status"] = "failed"
             update_and_emit_state(socketio, room_code, game_state)
             return

        offered_card = trade_data.get("offered_card")
        requested_card = trade_data.get("requested_card")

        if response == "accept":
            # Verify both players still have the cards
            if offered_card not in sender_data.get("hand", []):
                emit("error", {"message": f"Sender no longer has the offered card ({offered_card})."}, room=sid)
                trade_data["status"] = "failed"
                if sender_player_obj and sender_player_obj.sid:
                    emit(f"{GAME_NAME}_trade_result", {"trade_id": trade_id, "status": "failed", "reason": "Offered card missing"}, room=sender_player_obj.sid)
            elif requested_card not in receiver_data.get("hand", []):
                emit("error", {"message": f"You no longer have the requested card ({requested_card})."}, room=sid)
                trade_data["status"] = "failed"
                if sender_player_obj and sender_player_obj.sid:
                    emit(f"{GAME_NAME}_trade_result", {"trade_id": trade_id, "status": "failed", "reason": "Requested card missing"}, room=sender_player_obj.sid)
            else:
                # Perform the trade
                sender_data["hand"].remove(offered_card)
                sender_data["hand"].append(requested_card)
                receiver_data["hand"].remove(requested_card)
                receiver_data["hand"].append(offered_card)
                trade_data["status"] = "accepted"
                logger.info(f"[{GAME_NAME}] Trade {trade_id} accepted and completed between {sender_id} and {receiver_id}.")
                # Notify both players
                trade_result = {"trade_id": trade_id, "status": "accepted"}
                emit(f"{GAME_NAME}_trade_result", trade_result, room=sid)
                if sender_player_obj and sender_player_obj.sid:
                    emit(f"{GAME_NAME}_trade_result", trade_result, room=sender_player_obj.sid)

        elif response == "reject":
            trade_data["status"] = "rejected"
            logger.info(f"[{GAME_NAME}] Trade {trade_id} rejected by {user_id}.")
            # Notify sender
            if sender_player_obj and sender_player_obj.sid:
                emit(f"{GAME_NAME}_trade_result", {"trade_id": trade_id, "status": "rejected"}, room=sender_player_obj.sid)
        else:
            emit("error", {"message": "Invalid response."}, room=sid)
            return

        update_and_emit_state(socketio, room_code, game_state)

    # Add more handlers as needed for game progression, ending, etc.

