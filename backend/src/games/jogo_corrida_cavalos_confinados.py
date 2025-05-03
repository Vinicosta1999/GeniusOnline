# -*- coding: utf-8 -*-
import logging
import random
from flask import request # Import request
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# --- Constants ---
NUM_HORSES_CCC = 4 # Same number of horses as confined
TOTAL_ROUNDS_CCC = 10 # Same number of rounds
INITIAL_CHIPS_CCC = 20 # Same initial chips
CLUE_ROUNDS_CCC = [3, 6, 9] # Same clue rounds
PAYOUT_MULTIPLIER_CCC = NUM_HORSES_CCC - 1 # Same payout

# --- Game State Structure (Similar to CCC) ---
game_states = {}

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(socketio, room_code, state):
    # Consider filtering state before emitting
    emit("update_state_ccc", state, room=room_code) # Use the same event name for simplicity?
    logger.debug(f"Jogo Corrida Cavalos Confinados state updated for room {room_code}")

# --- Helper Functions (Mostly reused from CCC, check for differences if any) ---
def assign_pairs_ccc(players_in_room):
    """Assigns players into pairs (player, guest). Assumes even number."""
    participants = list(players_in_room)
    random.shuffle(participants)
    pairs = {}
    guests_map = {}
    num_participants = len(participants)
    
    if num_participants % 2 != 0:
        logger.warning("Odd number of participants, cannot form pairs perfectly.")
        num_participants -= 1 

    for i in range(0, num_participants, 2):
        player_p = participants[i]
        guest_p = participants[i+1]
        player_user_id = player_p.user_id
        guest_user_id = guest_p.user_id

        pairs[player_user_id] = { # Key by player user_id
            "player_username": player_p.user.username,
            "player_user_id": player_user_id,
            "guest_user_id": guest_user_id,
            "guest_username": guest_p.user.username,
            "player_sid": player_p.sid, # Store current SIDs
            "guest_sid": guest_p.sid,
            "chips": INITIAL_CHIPS_CCC,
            "bets": {} # { round_num: { horse_num: amount } }
        }
        guests_map[guest_user_id] = player_user_id # Map guest_id back to player_id
        logger.info(f"CCC Pair created: Player {player_p.user.username} ({player_user_id}) with Guest {guest_p.user.username} ({guest_user_id})")

    return pairs, guests_map

def get_clue_ccc(winning_horse, round_num, clues_already_given):
    """Generates a clue based on the winning horse and round."""
    possible_horses = list(range(1, NUM_HORSES_CCC + 1))
    wrong_horses = [h for h in possible_horses if h != winning_horse]
    random.shuffle(wrong_horses)

    horses_to_eliminate = []
    if round_num in CLUE_ROUNDS_CCC:
        clue_index = CLUE_ROUNDS_CCC.index(round_num)
        # Find a horse not already eliminated by previous clues
        eliminated_in_clues = set()
        for clue in clues_already_given:
            try:
                eliminated_horse = int(clue.split("Cavalo ")[1].split(" não")[0])
                eliminated_in_clues.add(eliminated_horse)
            except:
                pass # Ignore malformed clues
                
        for horse in wrong_horses:
            if horse not in eliminated_in_clues:
                horses_to_eliminate.append(horse)
                break # Eliminate one per clue round
    
    if horses_to_eliminate:
        clue_text = f"Dica Rodada {round_num}: Cavalo {horses_to_eliminate[0]} não vencerá."
        return clue_text
    return None

def calculate_final_payouts_ccc(state):
    winning_horse = state["winning_horse"]
    for player_user_id, pair_info in state["pairs"].items():
        total_payout = 0
        for round_num, round_bets in pair_info.get("bets", {}).items():
            bet_on_winner = round_bets.get(winning_horse, 0)
            if bet_on_winner > 0:
                payout = bet_on_winner * PAYOUT_MULTIPLIER_CCC
                total_payout += payout
                player_username = pair_info["player_username"]
                guest_username = pair_info["guest_username"]
                logger.info(f"CCC Payout for {player_username}/{guest_username} in round {round_num}: Bet {bet_on_winner} on {winning_horse}, Payout {payout}")
        
        pair_info["chips"] = pair_info.get("chips", 0) + total_payout # Add winnings
        player_username = pair_info["player_username"]
        guest_username = pair_info["guest_username"]
        final_chips = pair_info["chips"]
        logger.info(f"CCC Final chips for {player_username}/{guest_username}: {final_chips}")

def determine_winner_pair_ccc(state):
    max_chips = -1
    winner = None
    winners = [] # Handle ties
    for player_user_id, pair_info in state["pairs"].items():
        chips = pair_info.get("chips", 0)
        if chips > max_chips:
            max_chips = chips
            winners = [{
                "player_username": pair_info["player_username"],
                "guest_username": pair_info["guest_username"],
                "player_user_id": player_user_id,
                "guest_user_id": pair_info["guest_user_id"],
                "chips": max_chips
            }]
        elif chips == max_chips:
             winners.append({
                "player_username": pair_info["player_username"],
                "guest_username": pair_info["guest_username"],
                "player_user_id": player_user_id,
                "guest_user_id": pair_info["guest_user_id"],
                "chips": max_chips
            })
            
    if len(winners) == 1:
        return winners[0]
    elif len(winners) > 1:
        # Tie - return list of winners or a specific tie indicator?
        return winners # Return list of tied winners
    else:
        return None # No winner

# --- SocketIO Event Handlers ---
def register_corrida_cavalos_confinados_events(socketio, get_authenticated_user_id):
    logger.info("Registering Corrida de Cavalos Confinados events...")

    @socketio.on("start_corrida_cavalos_confinados_game")
    def handle_start_confined_horse_race(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        logger.info(f"Attempting to start Corrida Cavalos Confinados in room {room_code} by host user {user_id}")

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
        
        if len(active_players_obj) < 2 or len(active_players_obj) % 2 != 0:
            logger.warning(f"Incorrect number of active players for CCC in room {room_code}. Need even >= 2, have {len(active_players_obj)}.")
            emit("error", {"message": "Corrida de Cavalos Confinados requer um número par de participantes ativos (>= 2)."}, room=sid)
            return

        pairs, guests_map = assign_pairs_ccc(active_players_obj)
        if not pairs:
             emit("error", {"message": "Falha ao formar duplas de jogador/convidado."}, room=sid)
             return

        winning_horse = random.randint(1, NUM_HORSES_CCC)
        logger.info(f"CCC Winning horse for room {room_code} is {winning_horse}")

        initial_state = {
            "game_type": "corrida_cavalos_confinados",
            "pairs": pairs, # {player_user_id: pair_info}
            "guests_map": guests_map, # {guest_user_id: player_user_id}
            "winning_horse": winning_horse,
            "clues_given": [],
            "current_round": 1,
            "round_bets": {guest_id: {} for guest_id in guests_map.keys()}, # Initialize empty bets {guest_user_id: {horse: amount}}
            "status": "betting",
            "last_event": f"Jogo iniciado! Rodada 1 de {TOTAL_ROUNDS_CCC}. Convidados, façam suas apostas!",
            "winner_pair": None
        }

        game_states[room_code] = initial_state
        logger.info(f"Corrida Cavalos Confinados started in room {room_code}. Players: {list(pairs.keys())}, Guests: {list(guests_map.keys())}")
        emit("game_started", {"game_type": "corrida_cavalos_confinados", "initial_state": initial_state}, room=room_code)
        update_game_state(socketio, room_code, initial_state) # Emit full state update

    @socketio.on("place_bet_ccc")
    def handle_guest_place_bet(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid) # This is the guest user_id
        if not user_id:
            return

        room_code = data.get("room_code")
        horse_number = data.get("horse")
        amount = data.get("amount")

        state = get_game_state(room_code)
        # Check if game exists and is in betting phase
        if not state or state["status"] != "betting":
            emit("error", {"message": "Não é possível apostar agora."}, room=sid)
            return
            
        # Check if the user is a guest in this game
        if user_id not in state.get("guests_map", {}):
            emit("error", {"message": "Você não é um convidado neste jogo ou o jogo não iniciou corretamente."}, room=sid)
            return

        player_user_id = state["guests_map"].get(user_id)
        if not player_user_id or player_user_id not in state.get("pairs", {}):
             emit("error", {"message": "Convidado ou dupla inválida."}, room=sid)
             return

        pair_info = state["pairs"][player_user_id]
        guest_username = pair_info.get("guest_username", f"Guest {user_id}")
        current_round = state["current_round"]

        # --- Validations ---
        # Check if guest already bet this round
        if user_id in state.get("round_bets", {}) and state["round_bets"][user_id]:
            emit("error", {"message": f"Você já apostou na rodada {current_round}."}, room=sid)
            return
        try:
            horse_number = int(horse_number)
            amount = int(amount)
            if not (1 <= horse_number <= NUM_HORSES_CCC):
                raise ValueError("Número do cavalo inválido.")
            if amount <= 0:
                raise ValueError("Valor da aposta deve ser positivo.")
            if amount > pair_info.get("chips", 0):
                raise ValueError("Fichas insuficientes.")
        except (ValueError, TypeError) as e:
            emit("error", {"message": f"Aposta inválida: {e}"}, room=sid)
            return

        # --- Process Bet ---
        state.setdefault("round_bets", {})[user_id] = {horse_number: amount}
        pair_info["chips"] = pair_info.get("chips", 0) - amount # Deduct chips

        # Store bet in persistent history for the pair
        round_bets_history = pair_info.setdefault("bets", {}).setdefault(current_round, {})
        current_bet_on_horse = round_bets_history.get(horse_number, 0)
        round_bets_history[horse_number] = current_bet_on_horse + amount

        player_username_str = pair_info.get("player_username", "Jogador")
        state["last_event"] = f"{guest_username} (para {player_username_str}) apostou {amount} fichas no cavalo {horse_number} para a rodada {current_round}."
        chips_left = pair_info["chips"]
        logger.info(f"CCC Guest {guest_username} (User ID: {user_id}) bet {amount} on horse {horse_number} in round {current_round} for room {room_code}. Chips left: {chips_left}")

        # --- Check if Round Ends ---
        all_guests_have_bet = all(state["round_bets"].get(g_id) for g_id in state["guests_map"].keys())

        if all_guests_have_bet:
            logger.info(f"CCC All guests have bet for round {current_round} in room {room_code}. Ending round.")
            state["status"] = "round_end" # Indicate round calculations happen
            update_game_state(socketio, room_code, state) # Show bets are locked

            # Give clue if applicable
            clue = None
            if current_round in CLUE_ROUNDS_CCC:
                clue = get_clue_ccc(state["winning_horse"], current_round, state.get("clues_given", []))
                if clue:
                    state.setdefault("clues_given", []).append(clue)
                    state["last_event"] += f" | {clue}"
                    logger.info(f"CCC Clue given in round {current_round}: {clue}")

            # Check for game end
            if current_round >= TOTAL_ROUNDS_CCC:
                state["status"] = "finished"
                logger.info(f"CCC Game reached final round ({current_round}). Calculating final payouts for room {room_code}.")
                calculate_final_payouts_ccc(state)
                state["winner_pair"] = determine_winner_pair_ccc(state)
                winner_info = state["winner_pair"]
                
                winner_text = "Não houve vencedor claro"
                if isinstance(winner_info, dict): # Single winner
                    winner_player = winner_info["player_username"]
                    winner_guest = winner_info["guest_username"]
                    winner_chips = winner_info["chips"]
                    winner_text = f"Dupla vencedora: {winner_player} e {winner_guest} com {winner_chips} fichas!"
                    # TODO: Award prize to winner_info["player_user_id"] and winner_info["guest_user_id"]
                elif isinstance(winner_info, list): # Tie
                    winner_names_list = []
                    for w in winner_info:
                        player_name = w["player_username"]
                        guest_name = w["guest_username"]
                        winner_names_list.append(f"{player_name}/{guest_name}")
                    winner_names = " e ".join(winner_names_list)
                    tie_chips = winner_info[0]["chips"]
                    winner_text = f"Empate entre {winner_names} com {tie_chips} fichas!"
                    # TODO: Award prizes to all tied winners
                    
                winning_horse_val = state["winning_horse"]
                state["last_event"] = f"Fim de jogo! {winner_text} O cavalo vencedor era o {winning_horse_val}."
                logger.info(f"CCC Game finished for room {room_code}. Winner(s): {winner_info}")
            else:
                # Prepare for next round
                state["current_round"] += 1
                state["round_bets"] = {guest_id: {} for guest_id in state["guests_map"].keys()} # Reset bets
                state["status"] = "betting"
                next_round = state["current_round"]
                state["last_event"] += f" | Iniciando Rodada {next_round}! Convidados, façam suas apostas."
                logger.info(f"CCC Proceeding to round {next_round} in room {room_code}.")

        # Emit final state update for the round/game end
        update_game_state(socketio, room_code, state)
        emit("bet_confirmed_ccc", {"success": True, "horse": horse_number, "amount": amount, "chips_remaining": pair_info["chips"]}, room=sid)

    @socketio.on("get_game_state_ccc")
    def handle_get_game_state_ccc(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
             logger.warning(f"Unauthenticated user with SID {sid} tried to get CCC game state.")
             emit("error", {"message": "Autenticação necessária."}, room=sid)
             return
             
        room_code = data.get("room_code")
        if not room_code:
             emit("error", {"message": "Código da sala não fornecido."}, room=sid)
             return
             
        state = get_game_state(room_code)
        if state:
            # Filter state if needed?
            emit("update_state_ccc", state, room=sid)
            logger.debug(f"Sent CCC state to user {user_id} (SID: {sid}) for room {room_code}")
        else:
            logger.warning(f"No CCC state found for room {room_code} on request from user {user_id} (SID: {sid})")
            emit("error", {"message": "Nenhum jogo Corrida de Cavalos Confinados ativo nesta sala."}, room=sid)

    logger.info("Corrida de Cavalos Confinados events registered.")

