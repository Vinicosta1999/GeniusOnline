# -*- coding: utf-8 -*-
import logging
import random
from flask import request # Import request
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# --- Constants ---
NUMBERS = list(range(1, 11)) # Numbers 1 to 10
OPERATORS = ["+", "-", "*", "/"]
INITIAL_CARDS_PER_TYPE = 5 # 5 numbers, 5 operators initially
DECK_SIZE = 10 # Final deck size for calculation
MAX_SHUFFLES = 3

# --- Game State Structure ---
game_states = {}

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(socketio, room_code, state):
    game_states[room_code] = state
    # Emit public state (consider filtering sensitive info)
    emit("update_state_abrir_passar", state, room=room_code)
    logger.debug(f"Jogo Abrir/Passar state updated and emitted for room {room_code}")

# --- Helper Functions (No auth changes needed here) ---
def deal_initial_cards():
    """Deals 5 random numbers and 5 random operators."""
    numbers = random.sample(NUMBERS * 2, INITIAL_CARDS_PER_TYPE) # Sample with replacement conceptually
    operators = random.sample(OPERATORS * 3, INITIAL_CARDS_PER_TYPE) # Sample with replacement conceptually
    hand = numbers + operators
    random.shuffle(hand)
    return hand

def validate_deck(deck):
    """Checks if the deck has the required size."""
    if not isinstance(deck, list) or len(deck) != DECK_SIZE:
        return False
    # Basic validation: check if elements are numbers or operators (can be enhanced)
    for card in deck:
        if not (isinstance(card, int) or card in OPERATORS):
            return False
    return True

def calculate_deck_total(deck):
    """Calculates the total value of a deck using left-to-right evaluation.
       Handles potential division by zero.
       Assumes deck alternates number, operator, number, ... or starts with number.
       Filters deck to start with a number and alternate.
    """
    
    # Ensure alternating pattern starting with a number
    filtered_deck = []
    expect_number = True
    for card in deck:
        is_number = isinstance(card, int)
        is_operator = card in OPERATORS
        if expect_number and is_number:
            filtered_deck.append(card)
            expect_number = False
        elif not expect_number and is_operator:
            filtered_deck.append(card)
            expect_number = True
        # Skip cards that break the pattern

    # Remove trailing operator if present
    if filtered_deck and filtered_deck[-1] in OPERATORS:
        filtered_deck.pop()

    if not filtered_deck or not isinstance(filtered_deck[0], int):
        return 0 # Cannot calculate if deck is empty or doesn't start with a number

    total = float(filtered_deck[0])
    i = 1
    while i < len(filtered_deck) - 1:
        operator = filtered_deck[i]
        try:
            number = float(filtered_deck[i+1])
            if operator == "+":
                total += number
            elif operator == "-":
                total -= number
            elif operator == "*":
                total *= number
            elif operator == "/":
                if number == 0:
                    # Handle division by zero - treat as adding 0 or a large penalty?
                    # Let's add 0 for simplicity, preventing crashes.
                    total += 0
                    logger.warning("Division by zero encountered in calculation, treated as +0.")
                else:
                    total /= number
        except (ValueError, TypeError, IndexError) as e:
             logger.error(f"Error calculating deck total: {e} with deck part {filtered_deck[i-1:i+2]}")
             # Decide how to handle calculation errors - return current total? return 0?
             return total # Return current total before error
        i += 2

    # Return integer if the result is a whole number, else float
    return int(total) if total == int(total) else round(total, 2)


def determine_winner(player1_choice, player1_total, player2_choice, player2_total):
    """Determines the winner based on choices and totals."""
    if player1_choice == "passar" and player2_choice == "passar":
        return None, "Ambos passaram." # Draw
    elif player1_choice == "abrir" and player2_choice == "passar":
        return "player1", f"Jogador 2 passou. Jogador 1 vence com {player1_total}."
    elif player1_choice == "passar" and player2_choice == "abrir":
        return "player2", f"Jogador 1 passou. Jogador 2 vence com {player2_total}."
    elif player1_choice == "abrir" and player2_choice == "abrir":
        if player1_total > player2_total:
            return "player1", f"Ambos abriram. Jogador 1 vence com {player1_total} vs {player2_total}."
        elif player2_total > player1_total:
            return "player2", f"Ambos abriram. Jogador 2 vence com {player2_total} vs {player1_total}."
        else:
            return None, f"Ambos abriram e empataram com {player1_total}." # Draw
    else:
        # Should not happen with validation
        logger.error(f"Invalid choices for determining winner: P1={player1_choice}, P2={player2_choice}")
        return None, "Erro ao determinar vencedor."

# --- SocketIO Event Handlers ---
def register_abrir_passar_events(socketio, get_authenticated_user_id):
    logger.info("Registering Abrir, Passar events...")

    @socketio.on("start_abrir_passar_game")
    def handle_start_abrir_passar_game(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        logger.info(f"Attempting to start Abrir/Passar in room {room_code} by host user {user_id}")

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
        
        if len(active_players_obj) != 2:
            logger.warning(f"Incorrect number of active players for Abrir/Passar in room {room_code}. Need 2, have {len(active_players_obj)}.")
            emit("error", {"message": "O jogo Abrir/Passar requer exatamente 2 jogadores ativos."}, room=sid)
            return

        game_players = {}
        for p in active_players_obj:
            game_players[p.user_id] = { # Use user_id as key
                "username": p.user.username,
                "user_id": p.user_id,
                "sid": p.sid, # Store current SID for emitting
                "initial_hand": deal_initial_cards(),
                "built_deck": None,
                "shuffles_remaining": MAX_SHUFFLES,
                "choice": None,
                "calculated_total": None,
                "is_ready": False
            }

        initial_state = {
            "game_type": "abrir_passar",
            "players": game_players, # Dict {user_id: info}
            "status": "building",
            "round_results": None,
            "last_event": "Jogo iniciado! Construa seu deck."
        }

        game_states[room_code] = initial_state
        logger.info(f"Abrir/Passar started in room {room_code}. Players: {list(game_players.keys())}")
        emit("game_started", {"game_type": "abrir_passar", "initial_state": initial_state}, room=room_code)
        
        # Send individual hands to each player
        for p_id, player_data in game_players.items():
            player_sid = player_data.get("sid")
            if player_sid:
                emit("update_player_hand_abrir_passar", {"hand": player_data["initial_hand"]}, room=player_sid)
                
        update_game_state(socketio, room_code, initial_state) # Emit full state update

    @socketio.on("build_deck_abrir_passar")
    def handle_build_deck(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return
            
        room_code = data.get("room_code")
        deck = data.get("deck")

        state = get_game_state(room_code)
        if not state or state["status"] != "building" or user_id not in state["players"]:
            emit("error", {"message": "Não é possível construir o deck agora ou você não é um jogador ativo."}, room=sid)
            return

        player_info = state["players"][user_id]
        if player_info["is_ready"]:
             emit("error", {"message": "Você já montou seu deck."}, room=sid)
             return

        if not validate_deck(deck):
            emit("error", {"message": f"Deck inválido. Deve conter {DECK_SIZE} cartas (números ou operadores válidos)."}, room=sid)
            return

        # Optional: Check if deck cards are from the initial hand
        # initial_hand = player_info.get("initial_hand", [])
        # if not all(card in initial_hand for card in deck):
        #     emit("error", {"message": "Deck contém cartas que não estavam na sua mão inicial."}, room=sid)
        #     return
        # if len(deck) != len(set(deck)) and not allow_duplicates: # Check for duplicates if needed
        #     emit("error", {"message": "Deck não pode conter cartas duplicadas da mão inicial (se aplicável)."}, room=sid)
        #     return

        player_info["built_deck"] = list(deck) # Store a copy
        player_info["is_ready"] = True
        state["last_event"] = f"{player_info['username']} montou o deck."
        logger.info(f"Player {player_info['username']} (User ID: {user_id}) built deck in room {room_code}")

        # Check if all players are ready
        all_ready = all(p["is_ready"] for p in state["players"].values())
        if all_ready:
            state["status"] = "choosing"
            state["last_event"] = "Todos os jogadores montaram seus decks. Façam suas escolhas: Abrir ou Passar."
            logger.info(f"All players ready in room {room_code}. Moving to choosing phase.")

        update_game_state(socketio, room_code, state)
        emit("deck_built_confirmation", {"success": True}, room=sid)

    @socketio.on("shuffle_deck_abrir_passar")
    def handle_shuffle_deck(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return
            
        room_code = data.get("room_code")

        state = get_game_state(room_code)
        if not state or state["status"] != "building" or user_id not in state["players"]:
            emit("error", {"message": "Não é possível embaralhar agora ou você não é um jogador ativo."}, room=sid)
            return

        player_info = state["players"][user_id]
        if player_info["is_ready"]:
             emit("error", {"message": "Não pode embaralhar após montar o deck."}, room=sid)
             return
        if player_info["shuffles_remaining"] <= 0:
            emit("error", {"message": "Você não tem mais embaralhamentos."}, room=sid)
            return
        if not player_info["built_deck"]:
             # Allow shuffling initial hand if deck not built?
             # Or require deck to be built first? Let's require deck built.
             emit("error", {"message": "Monte seu deck antes de embaralhar."}, room=sid)
             return

        random.shuffle(player_info["built_deck"])
        player_info["shuffles_remaining"] -= 1
        state["last_event"] = f"{player_info['username']} embaralhou o deck."
        logger.info(f"Player {player_info['username']} (User ID: {user_id}) shuffled deck in room {room_code}. {player_info['shuffles_remaining']} shuffles left.")

        update_game_state(socketio, room_code, state)
        # Send back the shuffled deck and remaining shuffles
        emit("deck_shuffled", {"shuffled_deck": player_info["built_deck"], "shuffles_remaining": player_info["shuffles_remaining"]}, room=sid)

    @socketio.on("choose_action_abrir_passar")
    def handle_choose_action(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return
            
        room_code = data.get("room_code")
        choice = data.get("choice") # "abrir" or "passar"

        state = get_game_state(room_code)
        if not state or state["status"] != "choosing" or user_id not in state["players"]:
            emit("error", {"message": "Não é possível escolher agora ou você não é um jogador ativo."}, room=sid)
            return

        player_info = state["players"][user_id]
        if player_info["choice"]:
            emit("error", {"message": "Você já fez sua escolha."}, room=sid)
            return

        if choice not in ["abrir", "passar"]:
            emit("error", {"message": "Escolha inválida. Use 'abrir' ou 'passar'."}, room=sid)
            return

        player_info["choice"] = choice
        state["last_event"] = f"{player_info['username']} fez sua escolha."
        logger.info(f"Player {player_info['username']} (User ID: {user_id}) chose {choice} in room {room_code}")

        # Check if all players have chosen
        all_chosen = all(p["choice"] is not None for p in state["players"].values())
        if all_chosen:
            state["status"] = "reveal"
            state["last_event"] = "Todos escolheram. Revelando resultados..."
            logger.info(f"All players chose in room {room_code}. Moving to reveal phase.")

            # Calculate totals for those who chose "abrir"
            player_ids = list(state["players"].keys())
            p1_id, p2_id = player_ids[0], player_ids[1]
            p1 = state["players"][p1_id]
            p2 = state["players"][p2_id]

            if p1["choice"] == "abrir":
                p1["calculated_total"] = calculate_deck_total(p1["built_deck"])
            if p2["choice"] == "abrir":
                p2["calculated_total"] = calculate_deck_total(p2["built_deck"])

            # Determine winner
            winner_key, reason = determine_winner(
                p1["choice"], p1.get("calculated_total"), # Use .get for safety
                p2["choice"], p2.get("calculated_total")
            )

            winner_user_id = None
            if winner_key == "player1":
                winner_user_id = p1_id
            elif winner_key == "player2":
                winner_user_id = p2_id
            elif winner_key is None:
                 winner_user_id = "draw" # Indicate a draw explicitly

            state["round_results"] = {
                "winner_user_id": winner_user_id, # Store user_id or "draw"
                "reason": reason,
                "p1_id": p1_id, "p1_choice": p1["choice"], "p1_total": p1.get("calculated_total"), "p1_deck": p1.get("built_deck"),
                "p2_id": p2_id, "p2_choice": p2["choice"], "p2_total": p2.get("calculated_total"), "p2_deck": p2.get("built_deck")
            }
            state["status"] = "finished"
            state["last_event"] = f"Jogo terminado! {reason}"
            logger.info(f"Game finished in room {room_code}. Winner ID: {winner_user_id}. Reason: {reason}")
            
            # TODO: Award prizes based on winner_user_id
            if winner_user_id != "draw":
                 winner_user = User.query.get(winner_user_id)
                 if winner_user:
                     # Define prize
                     tokens_prize = 1 # Example
                     grenades_prize = 5 # Example
                     winner_user.tokens_of_life = (winner_user.tokens_of_life or 0) + tokens_prize
                     winner_user.grenades = (winner_user.grenades or 0) + grenades_prize
                     db.session.commit()
                     logger.info(f"User {winner_user.username} (ID: {winner_user_id}) awarded {tokens_prize} tokens and {grenades_prize} grenades.")
                 else:
                     logger.error(f"Winner user with ID {winner_user_id} not found in DB for prize awarding.")

        update_game_state(socketio, room_code, state)
        emit("choice_confirmed", {"success": True}, room=sid)

    @socketio.on("get_game_state_abrir_passar")
    def handle_get_game_state_abrir_passar(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
             logger.warning(f"Unauthenticated user with SID {sid} tried to get Abrir/Passar game state.")
             emit("error", {"message": "Autenticação necessária."}, room=sid)
             return
             
        room_code = data.get("room_code")
        if not room_code:
             emit("error", {"message": "Código da sala não fornecido."}, room=sid)
             return
             
        state = get_game_state(room_code)
        if state:
            # Filter sensitive info before sending?
            # e.g., opponent's initial hand, built deck before reveal?
            # For now, send full state.
            emit("update_state_abrir_passar", state, room=sid)
            logger.debug(f"Sent Abrir/Passar state to user {user_id} (SID: {sid}) for room {room_code}")
        else:
            logger.warning(f"No Abrir/Passar state found for room {room_code} on request from user {user_id} (SID: {sid})")
            emit("error", {"message": "Nenhum jogo Abrir/Passar ativo nesta sala."}, room=sid)

    logger.info("Abrir, Passar events registered.")

