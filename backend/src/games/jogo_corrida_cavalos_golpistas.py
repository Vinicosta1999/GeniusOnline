# -*- coding: utf-8 -*-
import logging
import random
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# --- Constants ---
NUM_HORSES_CCG = 4
TOTAL_ROUNDS_CCG = 12
MAX_BET_PER_ROUND_CCG = 3
INITIAL_CHIPS_CCG = 10
INITIAL_GRENADES_CCG = 5
CLUE_COST_CCG = 3 # Grenades
PAYOUT_MULTIPLIER_CCG = 10 # Payout is 10x the bet amount on the winner
INITIAL_CLUES_COUNT = 2

# --- Game State Structure ---
# game_states = {
#     "room_code": {
#         "game_type": "corrida_cavalos_golpistas",
#         "players": {
#             "sid1": {
#                 "username": "Alice",
#                 "sid": "sid1",
#                 "chips": INITIAL_CHIPS_CCG,
#                 "grenades": INITIAL_GRENADES_CCG,
#                 "clues": ["Cavalo 3 não vencerá.", "Cavalo 1 não vencerá."], # List of clues received
#                 "bets": {}, # { round_num: { horse_num: amount } }
#                 "has_bet_this_round": False
#             },
#             "sid2": { ... }
#         },
#         "winning_horse": 2, # The actual winner, determined at start
#         "current_round": 1,
#         "status": "betting" | "round_end" | "finished",
#         "last_event": "",
#         "final_results": None # { "winner_username": "Alice", "max_chips": 150, "payouts": {"sid1": 140, "sid2": 0} }
#     }
# }
game_states = {}

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(room_code, state, broadcast=True):
    # Decide what parts of the state are public vs private
    public_state = {
        "game_type": state["game_type"],
        "players": {sid: {"username": p["username"], "chips": p["chips"], "grenades": p["grenades"], "has_bet_this_round": p["has_bet_this_round"]} for sid, p in state["players"].items()},
        "current_round": state["current_round"],
        "status": state["status"],
        "last_event": state["last_event"],
        "final_results": state.get("final_results"),
        # Don't broadcast winning_horse until the end
        # Don't broadcast individual clues or bets
    }
    if state["status"] == "finished":
        public_state["winning_horse"] = state["winning_horse"]
        # Optionally include full bet history in final results if needed

    if broadcast:
        emit("update_state_ccg", public_state, room=room_code)
        logger.debug(f"Jogo CCG public state updated for room {room_code}")
    # We might need to send private updates too (e.g., for clues)

# --- Helper Functions ---
def generate_initial_clues(winning_horse, num_clues):
    """Generates a list of initial clues (horses that won't win)."""
    possible_horses = list(range(1, NUM_HORSES_CCG + 1))
    losing_horses = [h for h in possible_horses if h != winning_horse]
    random.shuffle(losing_horses)
    clues = []
    for i in range(min(num_clues, len(losing_horses))):
        clues.append(f"Cavalo {losing_horses[i]} não vencerá.")
    return clues

def generate_new_clue(winning_horse, existing_clues):
    """Generates a new clue, different from existing ones."""
    possible_horses = list(range(1, NUM_HORSES_CCG + 1))
    losing_horses = [h for h in possible_horses if h != winning_horse]
    revealed_losing_horses = set()
    for clue in existing_clues:
        try:
            # Extract horse number from clue like "Cavalo X não vencerá."
            horse_num = int(clue.split(" ")[1])
            revealed_losing_horses.add(horse_num)
        except (IndexError, ValueError):
            continue # Ignore malformed clues

    available_losing_horses = [h for h in losing_horses if h not in revealed_losing_horses]
    
    if not available_losing_horses:
        return None # No more clues to give
        
    random.shuffle(available_losing_horses)
    new_clue_horse = available_losing_horses[0]
    return f"Cavalo {new_clue_horse} não vencerá."

def calculate_final_payouts_and_winner(state):
    winning_horse = state["winning_horse"]
    payouts = {}
    max_chips = -1
    winners = []

    for sid, player_info in state["players"].items():
        total_bet_on_winner = 0
        for round_num, round_bets in player_info["bets"].items():
            bet_on_winner = round_bets.get(winning_horse, 0)
            total_bet_on_winner += bet_on_winner
        
        payout = total_bet_on_winner * PAYOUT_MULTIPLIER_CCG
        payouts[sid] = payout
        final_chips = player_info["chips"] + payout # Chips were deducted during betting
        player_info["chips"] = final_chips # Update final chip count

        logger.info(f"Player {player_info['username']} ({sid}): Bet {total_bet_on_winner} on winner ({winning_horse}), Payout {payout}, Final Chips {final_chips}")

        if final_chips > max_chips:
            max_chips = final_chips
            winners = [player_info["username"]]
        elif final_chips == max_chips:
            winners.append(player_info["username"])

    winner_username = ", ".join(winners) if winners else "Ninguém"
    return {"winner_username": winner_username, "max_chips": max_chips, "payouts": payouts}

# --- SocketIO Event Handlers ---
def register_corrida_cavalos_golpistas_events(socketio, get_authenticated_user_id):
    logger.info("Registering Corrida de Cavalos Golpistas events...")

    @socketio.on("start_corrida_cavalos_golpistas_game")
    def handle_start_horse_race_scam(data):
        room_code = data.get("room_code")
        host_sid = data.get("host_sid")
        logger.info(f"Attempting to start CCG in room {room_code} by host {host_sid}")

        room = GameRoom.query.filter_by(code=room_code).first()
        if not room:
            logger.error(f"Room {room_code} not found.")
            emit("error", {"message": f"Sala {room_code} não encontrada."}, room=host_sid)
            return

        players_in_room = room.players
        if len(players_in_room) < 2: # Need at least 2 players
            logger.warning(f"Not enough players for CCG in room {room_code}. Need >= 2, have {len(players_in_room)}.")
            emit("error", {"message": "Corrida de Cavalos Golpistas requer pelo menos 2 jogadores."}, room=host_sid)
            return

        winning_horse = random.randint(1, NUM_HORSES_CCG)
        logger.info(f"CCG Winning horse for room {room_code} is {winning_horse}")

        game_players = {}
        for p in players_in_room:
            initial_clues = generate_initial_clues(winning_horse, INITIAL_CLUES_COUNT)
            game_players[p.sid] = {
                "username": p.user.username,
                "sid": p.sid,
                "chips": INITIAL_CHIPS_CCG,
                "grenades": INITIAL_GRENADES_CCG,
                "clues": initial_clues,
                "bets": {},
                "has_bet_this_round": False
            }

        initial_state = {
            "game_type": "corrida_cavalos_golpistas",
            "players": game_players,
            "winning_horse": winning_horse,
            "current_round": 1,
            "status": "betting",
            "last_event": f"Jogo iniciado! Rodada 1 de {TOTAL_ROUNDS_CCG}. Façam suas apostas!",
            "final_results": None
        }

        game_states[room_code] = initial_state
        logger.info(f"Corrida Cavalos Golpistas started in room {room_code}. Initial State (partial): { {k:v for k,v in initial_state.items() if k != 'players'} }")
        
        # Emit public state
        emit("game_started", {"game_type": "corrida_cavalos_golpistas", "initial_state": {k:v for k,v in initial_state.items() if k != 'winning_horse' and k != 'players'}}, room=room_code)
        update_game_state(room_code, initial_state, broadcast=True)

        # Emit private initial info (clues) to each player
        for sid, player_data in game_players.items():
            emit("initial_info_ccg", {"clues": player_data["clues"] }, room=sid)

    @socketio.on("place_bet_ccg")
    def handle_place_bet_ccg(data):
        room_code = data.get("room_code")
        player_sid = data.get("player_sid")
        horse_number = data.get("horse")
        amount = data.get("amount")

        state = get_game_state(room_code)
        if not state or state["status"] != "betting" or player_sid not in state["players"]:
            emit("error", {"message": "Não é possível apostar agora."}, room=player_sid)
            return

        player_info = state["players"][player_sid]
        current_round = state["current_round"]

        # --- Validations ---
        if player_info["has_bet_this_round"]:
            emit("error", {"message": f"Você já apostou na rodada {current_round}."}, room=player_sid)
            return
        try:
            horse_number = int(horse_number)
            amount = int(amount)
            if not (1 <= horse_number <= NUM_HORSES_CCG):
                raise ValueError("Número do cavalo inválido.")
            if not (1 <= amount <= MAX_BET_PER_ROUND_CCG):
                 raise ValueError(f"A aposta deve ser entre 1 e {MAX_BET_PER_ROUND_CCG} fichas.")
            if amount > player_info["chips"]:
                raise ValueError("Fichas insuficientes.")
        except (ValueError, TypeError) as e:
            emit("error", {"message": f"Aposta inválida: {e}"}, room=player_sid)
            return

        # --- Process Bet ---
        player_info["chips"] -= amount # Deduct chips
        player_info["has_bet_this_round"] = True

        # Store bet in persistent history
        if current_round not in player_info["bets"]:
            player_info["bets"][current_round] = {}
        # Overwrite bet if they somehow bet twice? Or add? Let's overwrite.
        player_info["bets"][current_round] = {horse_number: amount}

        state["last_event"] = f"{player_info['username']} apostou {amount} fichas no cavalo {horse_number} para a rodada {current_round}."
        logger.info(f"Player {player_info['username']} ({player_sid}) bet {amount} on horse {horse_number} in round {current_round} for room {room_code}. Chips left: {player_info['chips']}")

        # --- Check if Round Ends ---
        all_players_have_bet = all(p["has_bet_this_round"] for p in state["players"].values())

        if all_players_have_bet:
            logger.info(f"All players have bet for round {current_round} in room {room_code}. Ending round.")
            state["status"] = "round_end" # Indicate round calculations happen (though none needed here)
            update_game_state(room_code, state, broadcast=True) # Show bets are locked

            # Check for game end
            if current_round >= TOTAL_ROUNDS_CCG:
                state["status"] = "finished"
                logger.info(f"Game reached final round ({current_round}). Calculating final payouts for room {room_code}.")
                state["final_results"] = calculate_final_payouts_and_winner(state)
                winner_info = state["final_results"]
                state["last_event"] = f"Fim de jogo! Vencedor(es): {winner_info['winner_username']} com {winner_info['max_chips']} fichas! O cavalo vencedor era o {state['winning_horse']}."
                logger.info(f"Game finished for room {room_code}. Results: {winner_info}")
            else:
                # Prepare for next round
                state["current_round"] += 1
                for p_sid in state["players"]:
                    state["players"][p_sid]["has_bet_this_round"] = False # Reset for next round
                state["status"] = "betting"
                state["last_event"] = f"Rodada {current_round} concluída. Iniciando Rodada {state['current_round']}! Façam suas apostas."
                logger.info(f"Proceeding to round {state['current_round']} in room {room_code}.")

        # Emit final state update for the round/game end
        update_game_state(room_code, state, broadcast=True)
        emit("bet_confirmed_ccg", {"success": True, "horse": horse_number, "amount": amount, "chips_remaining": player_info["chips"]}, room=player_sid)

    @socketio.on("buy_clue_ccg")
    def handle_buy_clue_ccg(data):
        room_code = data.get("room_code")
        player_sid = data.get("player_sid")

        state = get_game_state(room_code)
        # Allow buying clues anytime before the game ends?
        # Let's restrict to betting phase for simplicity.
        if not state or state["status"] != "betting" or player_sid not in state["players"]:
            emit("error", {"message": "Não é possível comprar pista agora."}, room=player_sid)
            return

        player_info = state["players"][player_sid]

        if player_info["grenades"] < CLUE_COST_CCG:
            emit("error", {"message": f"Granadas insuficientes. Custo: {CLUE_COST_CCG}"}, room=player_sid)
            return

        new_clue = generate_new_clue(state["winning_horse"], player_info["clues"])

        if not new_clue:
            emit("error", {"message": "Não há mais pistas disponíveis para comprar."}, room=player_sid)
            return

        # Process purchase
        player_info["grenades"] -= CLUE_COST_CCG
        player_info["clues"].append(new_clue)

        state["last_event"] = f"{player_info['username']} comprou uma nova pista."
        logger.info(f"Player {player_info['username']} ({player_sid}) bought clue in room {room_code}. Grenades left: {player_info['grenades']}. New clue: {new_clue}")

        # Emit private update with the new clue
        emit("new_clue_ccg", {"clue": new_clue, "grenades_remaining": player_info["grenades"]}, room=player_sid)
        
        # Emit public state update (showing reduced grenades)
        update_game_state(room_code, state, broadcast=True)

    @socketio.on("get_game_state_ccg")
    def handle_get_game_state_ccg(data):
        room_code = data.get("room_code")
        player_sid = data.get("sid")
        state = get_game_state(room_code)
        if state:
            # Send public state initially
            public_state = {
                "game_type": state["game_type"],
                "players": {sid: {"username": p["username"], "chips": p["chips"], "grenades": p["grenades"], "has_bet_this_round": p["has_bet_this_round"]} for sid, p in state["players"].items()},
                "current_round": state["current_round"],
                "status": state["status"],
                "last_event": state["last_event"],
                "final_results": state.get("final_results"),
            }
            if state["status"] == "finished":
                 public_state["winning_horse"] = state["winning_horse"]
                 
            emit("update_state_ccg", public_state, room=player_sid)
            # Send private info if the requester is a player in the game
            if player_sid in state["players"]:
                 emit("initial_info_ccg", {"clues": state["players"][player_sid]["clues"] }, room=player_sid)
            logger.debug(f"Sent CCG state (public + private if applicable) to {player_sid} for room {room_code}")
        else:
            logger.warning(f"No CCG state found for room {room_code} on request from {player_sid}")
            emit("error", {"message": "Nenhum jogo Corrida de Cavalos Golpistas ativo nesta sala."}, room=player_sid)

    logger.info("Corrida de Cavalos Golpistas events registered.")

