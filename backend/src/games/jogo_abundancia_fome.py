# -*- coding: utf-8 -*-
import logging
import math
from flask import request # Import request
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# --- Constants ---
TOTAL_ROUNDS = 10
BREAD_PER_ROUND_ABUNDANCIA = lambda num_players: 2 * num_players if num_players > 0 else 0 # Total bread for Abundancia area
COUPONS_PER_ROUND_FOME = 1 # Coupons awarded per player in Fome area

# --- Game State Structure ---
# game_states = {
#     "room_code": {
#         "game_type": "abundancia_fome",
#         "players": {
#             "user_id1": {
#                 "username": "Alice",
#                 "user_id": user_id1,
#                 "sid": "sid1", # Current SID
#                 "bread": 0,
#                 "coupons": 0,
#                 "choices": {}, # {1: "abundancia", 2: "fome", ...}
#                 "round_results": {} # {1: {"area": "abundancia", "bread_received": 1.5, "coupons_received": 0}, ...}
#             },
#             "user_id2": { ... }
#         },
#         "current_round": 1,
#         "round_choices": {}, # { user_id1: "abundancia", user_id2: "fome", ... } - Temporary for current round
#         "status": "choosing" | "calculating" | "finished",
#         "round_summary": None, # { "round": r, "abundancia_players": ["Alice"], "fome_players": ["Bob"], "bread_per_abundancia": 1.5, "coupons_per_fome": 1 }
#         "winner": None, # { "type": "bread"/"coupons"/"draw", "winners": ["Alice", "Bob"], "score": value }
#         "last_event": ""
#     }
# }
game_states = {}

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(socketio, room_code, state):
    # Avoid sending huge nested dicts repeatedly if possible, but fine for now
    # Consider filtering state before emitting if needed
    emit("update_state_abundancia_fome", state, room=room_code)
    logger.debug(f"Jogo Abundância/Fome state updated and emitted for room {room_code}")

# --- Helper Functions ---
def calculate_round_results(state):
    round_num = state["current_round"]
    choices = state["round_choices"] # {user_id: choice}
    players_state = state["players"] # {user_id: player_info}
    
    players_in_abundancia_ids = [uid for uid, choice in choices.items() if choice == "abundancia"]
    players_in_fome_ids = [uid for uid, choice in choices.items() if choice == "fome"]

    num_abundancia = len(players_in_abundancia_ids)
    num_fome = len(players_in_fome_ids)

    total_players = len(players_state)
    total_bread_abundancia = BREAD_PER_ROUND_ABUNDANCIA(total_players)
    bread_per_player_abundancia = math.floor(total_bread_abundancia / num_abundancia) if num_abundancia > 0 else 0

    coupons_per_player_fome = COUPONS_PER_ROUND_FOME

    round_summary = {
        "round": round_num,
        "abundancia_players": [players_state[uid]["username"] for uid in players_in_abundancia_ids if uid in players_state],
        "fome_players": [players_state[uid]["username"] for uid in players_in_fome_ids if uid in players_state],
        "bread_per_abundancia": bread_per_player_abundancia,
        "coupons_per_fome": coupons_per_player_fome,
        "num_abundancia": num_abundancia,
        "num_fome": num_fome
    }
    state["round_summary"] = round_summary

    # Update player states
    for user_id, player_info in players_state.items():
        choice = choices.get(user_id)
        bread_received = 0
        coupons_received = 0
        if choice == "abundancia":
            bread_received = bread_per_player_abundancia
            player_info["bread"] += bread_received
        elif choice == "fome":
            coupons_received = coupons_per_player_fome
            player_info["coupons"] += coupons_received
        
        player_info.setdefault("choices", {})[round_num] = choice
        player_info.setdefault("round_results", {})[round_num] = {
            "area": choice,
            "bread_received": bread_received,
            "coupons_received": coupons_received
        }
    room_code_str = state.get("room_code", "N/A")
    logger.info(f"Round {round_num} calculated for room {room_code_str}: Abundancia({num_abundancia}) got {bread_per_player_abundancia} bread each. Fome({num_fome}) got {coupons_per_player_fome} coupons each.")
    state["last_event"] = f"Rodada {round_num}: {num_abundancia} na Abundância ({bread_per_player_abundancia} pães cada), {num_fome} na Fome ({coupons_per_player_fome} cupons cada)."

def determine_winner(state):
    players = state["players"] # {user_id: player_info}
    if not players:
        return {"type": "draw", "winners": [], "score": 0, "reason": "Sem jogadores."} 

    max_bread = -1
    bread_winners = [] # List of usernames
    max_coupons = -1
    coupon_winners = [] # List of usernames

    for user_id, p_info in players.items():
        username = p_info.get("username", f"User {user_id}")
        # Bread winner
        if p_info.get("bread", 0) > max_bread:
            max_bread = p_info["bread"]
            bread_winners = [username]
        elif p_info.get("bread", 0) == max_bread:
            bread_winners.append(username)
        
        # Coupon winner
        if p_info.get("coupons", 0) > max_coupons:
            max_coupons = p_info["coupons"]
            coupon_winners = [username]
        elif p_info.get("coupons", 0) == max_coupons:
            coupon_winners.append(username)

    # Prioritize bread winner
    if max_bread > 0:
         return {"type": "bread", "winners": bread_winners, "score": max_bread, "reason": f"Maior quantidade de pão ({max_bread})."}
    elif max_coupons > 0:
         return {"type": "coupons", "winners": coupon_winners, "score": max_coupons, "reason": f"Maior quantidade de cupons ({max_coupons}), nenhum pão foi distribuído."}
    else:
         return {"type": "draw", "winners": [p.get("username", f"User {uid}") for uid, p in players.items()], "score": 0, "reason": "Ninguém acumulou pães ou cupons."}


# --- SocketIO Event Handlers ---
def register_jogo_abundancia_fome_events(socketio, get_authenticated_user_id):
    logger.info("Registering Abundância e Fome events...")

    @socketio.on("start_abundancia_fome_game")
    def handle_start_abundancia_fome_game(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        logger.info(f"Attempting to start Abundância/Fome in room {room_code} by host user {user_id}")

        room = GameRoom.query.filter_by(room_code=room_code).first()
        if not room:
            logger.error(f"Room {room_code} not found.")
            emit("error", {"message": f"Sala {room_code} não encontrada."}, room=sid)
            return

        # Check if the authenticated user is the host
        if room.host_id != user_id:
            emit("error", {"message": "Apenas o host pode iniciar o jogo."}, room=sid)
            return

        players_in_room = room.players # Get Player objects
        active_players_obj = [p for p in players_in_room if p.sid is not None]
        
        if len(active_players_obj) < 2: # Need at least 2 players
            logger.warning(f"Not enough active players for Abundância/Fome in room {room_code}. Need >= 2, have {len(active_players_obj)}.")
            emit("error", {"message": "O jogo Abundância/Fome requer pelo menos 2 jogadores ativos."}, room=sid)
            return

        game_players = {}
        for p in active_players_obj:
            game_players[p.user_id] = { # Use user_id as key
                "username": p.user.username,
                "user_id": p.user_id,
                "sid": p.sid, # Store current SID
                "bread": 0,
                "coupons": 0,
                "choices": {},
                "round_results": {}
            }

        initial_state = {
            "game_type": "abundancia_fome",
            "players": game_players, # Dict {user_id: info}
            "current_round": 1,
            "round_choices": {},
            "status": "choosing",
            "round_summary": None,
            "winner": None,
            "last_event": f"Jogo iniciado! Rodada 1 de {TOTAL_ROUNDS}. Escolham sua área.",
            "room_code": room_code # Include room code for context
        }

        game_states[room_code] = initial_state
        logger.info(f"Abundância/Fome started in room {room_code}. Players: {list(game_players.keys())}")
        emit("game_started", {"game_type": "abundancia_fome", "initial_state": initial_state}, room=room_code)
        update_game_state(socketio, room_code, initial_state) # Emit full state update

    @socketio.on("choose_area_abundancia_fome")
    def handle_choose_area(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return
            
        room_code = data.get("room_code")
        area = data.get("area") # "abundancia" or "fome"

        state = get_game_state(room_code)
        if not state or state["status"] != "choosing" or user_id not in state["players"]:
            emit("error", {"message": "Não é possível escolher a área agora ou você não é um jogador ativo."}, room=sid)
            return

        if area not in ["abundancia", "fome"]:
            emit("error", {"message": "Área inválida. Escolha \'abundancia\' ou \'fome\'."}, room=sid)
            return

        current_round = state["current_round"]
        if user_id in state.get("round_choices", {}):
            emit("error", {"message": f"Você já escolheu uma área para a rodada {current_round}."}, room=sid)
            return

        state.setdefault("round_choices", {})[user_id] = area
        player_username = state["players"][user_id]["username"]
        state["last_event"] = f"{player_username} fez sua escolha para a rodada {current_round}."
        logger.info(f"Player {player_username} (User ID: {user_id}) chose {area} in round {current_round} for room {room_code}")

        # Check if all players have chosen for the current round
        all_chosen = len(state["round_choices"]) == len(state["players"])

        if all_chosen:
            logger.info(f"All players have chosen for round {current_round} in room {room_code}. Calculating results.")
            state["status"] = "calculating" # Indicate calculation is in progress
            update_game_state(socketio, room_code, state) # Update state to show choices are locked

            # Perform calculations
            calculate_round_results(state)

            # Check for game end
            if state["current_round"] >= TOTAL_ROUNDS:
                state["status"] = "finished"
                state["winner"] = determine_winner(state)
                winner_reason = state["winner"].get("reason", "")
                state["last_event"] = f"Fim de jogo após {TOTAL_ROUNDS} rodadas! {winner_reason}"
                winner_details = state["winner"]
                logger.info(f"Game finished in room {room_code}. Winner details: {winner_details}")
                
                # TODO: Award prizes based on winner user_ids
                winner_info = state["winner"]
                if winner_info and winner_info["type"] != "draw":
                    # Find user_ids corresponding to winner usernames
                    winner_usernames = winner_info.get("winners", [])
                    winner_ids = [uid for uid, pdata in state["players"].items() if pdata.get("username") in winner_usernames]
                    
                    if winner_ids:
                        # Define prize based on win type?
                        tokens_prize = 2 if winner_info["type"] == "bread" else 1 # Example
                        grenades_prize = 10 if winner_info["type"] == "bread" else 5 # Example
                        
                        for winner_id in winner_ids:
                            winner_user = User.query.get(winner_id)
                            if winner_user:
                                winner_user.tokens_of_life = (winner_user.tokens_of_life or 0) + tokens_prize
                                winner_user.grenades = (winner_user.grenades or 0) + grenades_prize
                                db.session.commit()
                                logger.info(f"User {winner_user.username} (ID: {winner_id}) awarded {tokens_prize} tokens and {grenades_prize} grenades.")
                            else:
                                logger.error(f"Winner user with ID {winner_id} not found in DB for prize awarding.")
                    else:
                         logger.warning(f"Could not find user IDs for winner usernames: {winner_usernames}")

            else:
                # Prepare for next round
                state["current_round"] += 1
                state["round_choices"] = {}
                state["status"] = "choosing"
                next_round = state["current_round"]
                state["last_event"] += f" Iniciando Rodada {next_round}! Façam suas escolhas."
                logger.info(f"Proceeding to round {next_round} in room {room_code}.")

        # Emit final state update for the round/game end
        update_game_state(socketio, room_code, state)
        emit("choice_confirmed_abundancia_fome", {"success": True, "area": area}, room=sid)

    @socketio.on("get_game_state_abundancia_fome")
    def handle_get_game_state_abundancia_fome(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
             logger.warning(f"Unauthenticated user with SID {sid} tried to get Abundância/Fome game state.")
             emit("error", {"message": "Autenticação necessária."}, room=sid)
             return
             
        room_code = data.get("room_code")
        if not room_code:
             emit("error", {"message": "Código da sala não fornecido."}, room=sid)
             return
             
        state = get_game_state(room_code)
        if state:
            # Filter state if needed before sending to individual user
            emit("update_state_abundancia_fome", state, room=sid)
            logger.debug(f"Sent Abundância/Fome state to user {user_id} (SID: {sid}) for room {room_code}")
        else:
            logger.warning(f"No Abundância/Fome state found for room {room_code} on request from user {user_id} (SID: {sid})")
            emit("error", {"message": "Nenhum jogo Abundância/Fome ativo nesta sala."}, room=sid)

    logger.info("Abundância e Fome events registered.")

