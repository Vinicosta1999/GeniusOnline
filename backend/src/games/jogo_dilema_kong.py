# -*- coding: utf-8 -*-
import logging
import random
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# --- Constants ---
NUM_PLAYERS_DK = 6
TEAM_SIZE_DK = 3
INITIAL_BEANS_DK = 10
ROUNDS_TO_WIN_DK = 3
# MAX_ROUNDS_DK = 5 # Optional: Limit rounds if first-to-3 takes too long

# --- Game State Structure ---
# game_states = {
#     "room_code": {
#         "game_type": "dilema_kong",
#         "teams": {
#             "A": {
#                 "players": { # sid: { username, beans }
#                     "sid1": { "username": "Alice", "beans": INITIAL_BEANS_DK },
#                     "sid2": { "username": "Bob", "beans": INITIAL_BEANS_DK },
#                     "sid3": { "username": "Charlie", "beans": INITIAL_BEANS_DK }
#                 },
#                 "round_wins": 0,
#                 "round_deposits": {} # { round_num: total_deposited }
#             },
#             "B": {
#                 "players": { ... },
#                 "round_wins": 0,
#                 "round_deposits": {}
#             }
#         },
#         "player_to_team": { # sid: "A" or "B"
#             "sid1": "A",
#             "sid4": "B", ...
#         },
#         "current_round": 1,
#         "round_player_deposits": {}, # { sid: amount } - Temporary, secret deposits for current round
#         "status": "depositing" | "round_reveal" | "finished",
#         "last_round_winner": None, # "A", "B", or "draw"
#         "last_round_summary": None, # { "round": r, "team_A_total": x, "team_B_total": y, "winner": "A"/"B"/"draw" }
#         "game_winner": None, # "A" or "B"
#         "last_event": ""
#     }
# }
game_states = {}

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(room_code, state, broadcast=True):
    # Separate public and private state
    public_state = {
        "game_type": state["game_type"],
        "teams": {
            team_id: {
                "players": { sid: { "username": p_info["username"], "beans": p_info["beans"] } for sid, p_info in team_data["players"].items() },
                "round_wins": team_data["round_wins"]
            } for team_id, team_data in state["teams"].items()
        },
        "player_to_team": state["player_to_team"],
        "current_round": state["current_round"],
        "status": state["status"],
        "last_round_winner": state.get("last_round_winner"),
        "last_round_summary": state.get("last_round_summary"),
        "game_winner": state.get("game_winner"),
        "last_event": state["last_event"],
        # Only reveal deposits after the round
        "round_player_deposits_revealed": state.get("round_player_deposits") if state["status"] in ["round_reveal", "finished"] else None
    }

    if broadcast:
        emit("update_state_dk", public_state, room=room_code)
        logger.debug(f"Jogo DK public state updated for room {room_code}")
    # No specific private state needed besides initial team assignment (implicit in public state)

# --- Helper Functions ---
def assign_teams_dk(players_in_room):
    participants = list(players_in_room)
    random.shuffle(participants)
    teams = {"A": {"players": {}, "round_wins": 0, "round_deposits": {}}, "B": {"players": {}, "round_wins": 0, "round_deposits": {}}}
    player_to_team = {}

    for i, p in enumerate(participants):
        team_id = "A" if i < TEAM_SIZE_DK else "B"
        teams[team_id]["players"][p.sid] = {"username": p.user.username, "beans": INITIAL_BEANS_DK}
        player_to_team[p.sid] = team_id
        logger.info(f"Assigned {p.user.username} ({p.sid}) to Team {team_id}")
        
    return teams, player_to_team

def calculate_round_dk(state):
    round_num = state["current_round"]
    player_deposits = state["round_player_deposits"]
    team_totals = {"A": 0, "B": 0}

    # Calculate totals and deduct beans
    for sid, amount in player_deposits.items():
        team_id = state["player_to_team"].get(sid)
        if team_id:
            team_totals[team_id] += amount
            # Deduct beans from player
            if sid in state["teams"][team_id]["players"]:
                 state["teams"][team_id]["players"][sid]["beans"] -= amount
                 # Ensure beans don't go negative (should be validated on deposit)
                 state["teams"][team_id]["players"][sid]["beans"] = max(0, state["teams"][team_id]["players"][sid]["beans"])
            else:
                 logger.error(f"Player {sid} not found in team {team_id} during calculation.")
        else:
            logger.error(f"Team not found for player {sid} during calculation.")

    state["teams"]["A"]["round_deposits"][round_num] = team_totals["A"]
    state["teams"]["B"]["round_deposits"][round_num] = team_totals["B"]

    # Determine round winner
    round_winner = None
    if team_totals["A"] > team_totals["B"]:
        round_winner = "A"
        state["teams"]["A"]["round_wins"] += 1
    elif team_totals["B"] > team_totals["A"]:
        round_winner = "B"
        state["teams"]["B"]["round_wins"] += 1
    else:
        round_winner = "draw"

    state["last_round_winner"] = round_winner
    state["last_round_summary"] = {
        "round": round_num,
        "team_A_total": team_totals["A"],
        "team_B_total": team_totals["B"],
        "winner": round_winner
    }

    winner_text = f"Equipe {round_winner} venceu a rodada!" if round_winner != "draw" else "Empate na rodada!"
    state["last_event"] = f"Rodada {round_num}: Equipe A depositou {team_totals['A']}. Equipe B depositou {team_totals['B']}. {winner_text}"
    logger.info(f"DK Round {round_num} results for room {state.get('room_code', 'N/A')}: A={team_totals['A']}. B={team_totals['B']}. Winner: {round_winner}")

    # Check for game winner
    if state["teams"]["A"]["round_wins"] >= ROUNDS_TO_WIN_DK:
        state["game_winner"] = "A"
        state["status"] = "finished"
        state["last_event"] += f" Equipe A venceu o jogo!"
    elif state["teams"]["B"]["round_wins"] >= ROUNDS_TO_WIN_DK:
        state["game_winner"] = "B"
        state["status"] = "finished"
        state["last_event"] += f" Equipe B venceu o jogo!"
    # Optional: Check for max rounds
    # elif round_num >= MAX_ROUNDS_DK:
    #     state["status"] = "finished"
    #     # Determine winner based on round wins or remaining beans?
    #     if state["teams"]["A"]["round_wins"] > state["teams"]["B"]["round_wins"]:
    #         state["game_winner"] = "A"
    #     elif state["teams"]["B"]["round_wins"] > state["teams"]["A"]["round_wins"]:
    #          state["game_winner"] = "B"
    #     else:
    #          state["game_winner"] = "draw" # Or decide by beans
    #     state["last_event"] += f" Jogo terminou após {MAX_ROUNDS_DK} rodadas."

# --- SocketIO Event Handlers ---
def register_dilema_kong_events(socketio, get_authenticated_user_id):
    logger.info("Registering O Dilema de Kong events...")

    @socketio.on("start_dilema_kong_game")
    def handle_start_kong_dilemma(data):
        room_code = data.get("room_code")
        host_sid = data.get("host_sid")
        logger.info(f"Attempting to start Dilema de Kong in room {room_code} by host {host_sid}")

        room = GameRoom.query.filter_by(code=room_code).first()
        if not room:
            logger.error(f"Room {room_code} not found.")
            emit("error", {"message": f"Sala {room_code} não encontrada."}, room=host_sid)
            return

        players_in_room = room.players
        if len(players_in_room) != NUM_PLAYERS_DK:
            logger.warning(f"Incorrect number of players for DK in room {room_code}. Need {NUM_PLAYERS_DK}, have {len(players_in_room)}.")
            emit("error", {"message": f"O Dilema de Kong requer exatamente {NUM_PLAYERS_DK} jogadores."}, room=host_sid)
            return

        teams, player_to_team = assign_teams_dk(players_in_room)

        initial_state = {
            "game_type": "dilema_kong",
            "teams": teams,
            "player_to_team": player_to_team,
            "current_round": 1,
            "round_player_deposits": {},
            "status": "depositing",
            "last_round_winner": None,
            "last_round_summary": None,
            "game_winner": None,
            "last_event": f"Jogo iniciado! Rodada 1. Depositem seus feijões secretamente.",
            "room_code": room_code
        }

        game_states[room_code] = initial_state
        logger.info(f"Dilema de Kong started in room {room_code}. State (teams assigned)." )
        
        emit("game_started", {"game_type": "dilema_kong", "initial_state": initial_state}, room=room_code)
        update_game_state(room_code, initial_state, broadcast=True)

    @socketio.on("deposit_beans_dk")
    def handle_deposit_beans(data):
        room_code = data.get("room_code")
        player_sid = data.get("player_sid")
        amount = data.get("amount")

        state = get_game_state(room_code)
        if not state or state["status"] != "depositing" or player_sid not in state["player_to_team"]:
            emit("error", {"message": "Não é possível depositar agora."}, room=player_sid)
            return

        team_id = state["player_to_team"][player_sid]
        player_info = state["teams"][team_id]["players"].get(player_sid)
        if not player_info:
             emit("error", {"message": "Jogador não encontrado na equipe."}, room=player_sid)
             return
             
        current_round = state["current_round"]

        # --- Validations ---
        if player_sid in state["round_player_deposits"]:
            emit("error", {"message": f"Você já depositou na rodada {current_round}."}, room=player_sid)
            return
        try:
            amount = int(amount)
            if not (0 <= amount <= player_info["beans"]):
                 current_beans = player_info["beans"]
                 raise ValueError(f"Valor inválido. Deposite entre 0 e {current_beans} (seus feijões atuais).")
        except (ValueError, TypeError) as e:
            emit("error", {"message": f"Depósito inválido: {e}"}, room=player_sid)
            return

        # --- Process Deposit (Secretly) ---
        state["round_player_deposits"][player_sid] = amount
        state["last_event"] = f"{player_info['username']} depositou seus feijões."
        logger.info(f"Player {player_info['username']} ({player_sid}) deposited beans (amount hidden) in round {current_round} for room {room_code}.")

        # --- Check if Round Ends ---
        all_players_deposited = len(state["round_player_deposits"]) == NUM_PLAYERS_DK

        if all_players_deposited:
            logger.info(f"All players have deposited for round {current_round} in room {room_code}. Calculating results.")
            state["status"] = "round_reveal" # Indicate round calculations happen
            update_game_state(room_code, state, broadcast=True) # Show deposits are locked

            # Perform calculations
            calculate_round_dk(state) # This updates status to finished if game ends

            if state["status"] != "finished":
                # Prepare for next round
                state["current_round"] += 1
                state["round_player_deposits"] = {}
                state["status"] = "depositing"
                next_round = state["current_round"]
                state["last_event"] += f" Iniciando Rodada {next_round}! Depositem seus feijões."
                logger.info(f"Proceeding to round {next_round} in room {room_code}.")

        # Emit final state update for the round/game end
        update_game_state(room_code, state, broadcast=True)
        # Confirm deposit privately
        emit("deposit_confirmed_dk", {"success": True, "amount": amount}, room=player_sid)

    @socketio.on("get_game_state_dk")
    def handle_get_game_state_dk(data):
        room_code = data.get("room_code")
        player_sid = data.get("sid")
        state = get_game_state(room_code)
        if state:
            # Send public state
            public_state = {
                "game_type": state["game_type"],
                "teams": {
                    team_id: {
                        "players": { sid: { "username": p_info["username"], "beans": p_info["beans"] } for sid, p_info in team_data["players"].items() },
                        "round_wins": team_data["round_wins"]
                    } for team_id, team_data in state["teams"].items()
                },
                "player_to_team": state["player_to_team"],
                "current_round": state["current_round"],
                "status": state["status"],
                "last_round_winner": state.get("last_round_winner"),
                "last_round_summary": state.get("last_round_summary"),
                "game_winner": state.get("game_winner"),
                "last_event": state["last_event"],
                "round_player_deposits_revealed": state.get("round_player_deposits") if state["status"] in ["round_reveal", "finished"] else None
            }
            emit("update_state_dk", public_state, room=player_sid)
            logger.debug(f"Sent DK state to {player_sid} for room {room_code}")
        else:
            logger.warning(f"No DK state found for room {room_code} on request from {player_sid}")
            emit("error", {"message": "Nenhum jogo Dilema de Kong ativo nesta sala."}, room=player_sid)

    logger.info("O Dilema de Kong events registered.")

