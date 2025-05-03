# -*- coding: utf-8 -*-
import logging
import random
from flask import request # Import request
from flask_socketio import emit, join_room, leave_room
from src.models.user import db, User
from src.models.game import GameRoom, Player

logger = logging.getLogger(__name__)

# Game state storage
game_states = {}
MAX_GUESTS = 10
MAX_PLAYERS = 3
QUESTIONS_PER_ROUND = 3
POINTS_FOR_5_5 = 10

def get_game_state(room_code):
    return game_states.get(room_code)

def update_game_state(socketio, room_code, state):
    game_states[room_code] = state
    # Emit public state (consider filtering sensitive info if needed)
    emit("update_state_5_5", state, room=room_code)
    logger.debug(f"Jogo 5:5 state updated and emitted for room {room_code}")

def register_jogo_5_5_events(socketio, get_authenticated_user_id):
    logger.info("Registering Jogo 5:5 events...")

    @socketio.on("start_5_5_game")
    def handle_start_5_5_game(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return # Error emitted by get_authenticated_user_id

        room_code = data.get("room_code")
        logger.info(f"Attempting to start Jogo 5:5 in room {room_code} by host user {user_id}")

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
        
        if len(active_players_obj) < MAX_PLAYERS:
            logger.warning(f"Not enough active players to start Jogo 5:5 in room {room_code}. Need {MAX_PLAYERS}, have {len(active_players_obj)}.")
            emit("error", {"message": f"Não há jogadores ativos suficientes. São necessários {MAX_PLAYERS} jogadores."}, room=sid)
            return

        # Assign roles: first 3 are players, rest are guests (up to MAX_GUESTS)
        participants = list(active_players_obj)
        random.shuffle(participants) # Shuffle to randomize roles

        game_players = {}
        game_guests = {}
        all_participants = {}
        player_sids_turn_order = []

        for i, p in enumerate(participants):
            role = "player" if i < MAX_PLAYERS else "guest"
            if role == "guest" and len(game_guests) >= MAX_GUESTS:
                continue # Skip if guest limit reached

            participant_info = {
                "username": p.user.username,
                "user_id": p.user_id, # Store user_id
                "sid": p.sid, # Store current SID
                "role": role,
            }
            if role == "player":
                participant_info.update({
                    "score": 0,
                    "questions_asked_round1": 0,
                    "questions_asked_round2": 0
                })
                game_players[p.user_id] = participant_info # Use user_id as key
                player_sids_turn_order.append(p.user_id) # Store user_id for turn order
            else:
                game_guests[p.user_id] = participant_info # Use user_id as key

            all_participants[p.user_id] = participant_info # Use user_id as key

        if len(game_players) != MAX_PLAYERS:
             logger.warning(f"Could not assign exactly {MAX_PLAYERS} players for room {room_code}.")
             emit("error", {"message": f"Erro ao designar jogadores. Necessários {MAX_PLAYERS}."}, room=sid)
             return

        initial_state = {
            "game_type": "5_5",
            "players": game_players, # Dict {user_id: info}
            "guests": game_guests, # Dict {user_id: info}
            "all_participants": all_participants, # Dict {user_id: info}
            "player_ids_turn_order": player_sids_turn_order, # List of user_ids
            "round": 1,
            "current_player_index": 0,
            "questions": [],
            "status": "round_1", # Start directly in round 1
            "winner": None,
            "last_event": "Jogo iniciado!"
        }

        game_states[room_code] = initial_state
        logger.info(f"Jogo 5:5 started in room {room_code}. State keys: {list(initial_state.keys())}")
        # Emit initial state to everyone in the room
        emit("game_started", {"game_type": "5_5", "initial_state": initial_state}, room=room_code)
        update_game_state(socketio, room_code, initial_state) # Use helper to emit update

    @socketio.on("ask_question_5_5")
    def handle_ask_question_5_5(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        question_text = data.get("question", "").strip()

        state = get_game_state(room_code)
        if not state:
            logger.error(f"Game state not found for room {room_code} on ask_question_5_5")
            emit("error", {"message": "Estado do jogo não encontrado."}, room=sid)
            return

        if not question_text:
            emit("error", {"message": "A pergunta não pode estar vazia."}, room=sid)
            return

        # --- Validations ---
        if user_id not in state["players"]:
             emit("error", {"message": "Você não é um jogador ativo neste jogo."}, room=sid)
             return
             
        current_player_id = state["player_ids_turn_order"][state["current_player_index"]]
        if user_id != current_player_id:
            emit("error", {"message": "Não é sua vez de perguntar."}, room=sid)
            return

        if state["status"] not in ["round_1", "round_2"]:
            emit("error", {"message": "Não é a fase de fazer perguntas."}, room=sid)
            return

        player_info = state["players"][user_id]
        current_round = state["round"]
        round_key = f"questions_asked_round{current_round}"
        if player_info[round_key] >= QUESTIONS_PER_ROUND:
            emit("error", {"message": f"Você já fez suas {QUESTIONS_PER_ROUND} perguntas nesta rodada."}, room=sid)
            return

        if not state["guests"]:
             emit("error", {"message": "Não há convidados para responder."}, room=sid)
             return

        # --- Process Question ---
        player_username = player_info["username"]
        current_round = state["round"]
        logger.info(f"Player {player_username} (User ID: {user_id}) asked: \'{question_text}\' in round {current_round} for room {room_code}")
        player_info[round_key] += 1

        # Simulate guest answers (Yes/No)
        guest_answers = {}
        for guest_id in state["guests"]:
            guest_answers[guest_id] = random.choice(["yes", "no"]) # Keyed by user_id

        yes_count = sum(1 for answer in guest_answers.values() if answer == "yes")
        no_count = len(state["guests"]) - yes_count

        score_awarded = 0
        result_message = f"Respostas: {yes_count} Sim, {no_count} Não."
        if yes_count == 5 and no_count == 5:
            score_awarded = POINTS_FOR_5_5
            player_info["score"] += score_awarded
            result_message += f" Parabéns! +{score_awarded} pontos!"

        question_data = {
            "player_id": user_id, # Use user_id
            "player_username": player_info["username"],
            "question": question_text,
            "round": state["round"],
            "answers": guest_answers, # Dict {guest_user_id: answer}
            "result": {"yes": yes_count, "no": no_count},
            "score_awarded": score_awarded
        }
        state["questions"].append(question_data)
        player_username = player_info["username"]
        state["last_event"] = f"{player_username} perguntou: \'{question_text}\'. {result_message}"

        # --- Advance Turn / Round / Game End ---
        state["current_player_index"] = (state["current_player_index"] + 1) % len(state["player_ids_turn_order"])

        # Check if round ended (everyone asked QUESTIONS_PER_ROUND questions)
        round_ended = all(p[round_key] >= QUESTIONS_PER_ROUND for p in state["players"].values())

        if round_ended:
            if state["round"] == 1:
                state["round"] = 2
                state["current_player_index"] = 0 # Reset for round 2
                state["last_event"] = "Rodada 1 concluída. Iniciando Rodada 2!"
                logger.info(f"Round 1 ended for room {room_code}. Starting Round 2.")
            elif state["round"] == 2:
                state["status"] = "finished"
                # Determine winner
                max_score = -1
                winners = [] # List of winner user_ids
                for p_id, p_info in state["players"].items():
                    if p_info["score"] > max_score:
                        max_score = p_info["score"]
                        winners = [p_id]
                    elif p_info["score"] == max_score:
                        winners.append(p_id)

                if len(winners) == 1:
                    winner_id = winners[0]
                    state["winner"] = state["players"][winner_id]["username"]
                    winner_name = state["winner"]
                    state["last_event"] = f"Jogo terminado! Vencedor: {winner_name} com {max_score} pontos!"
                elif len(winners) > 1:
                     state["winner"] = "Empate"
                     winner_names = ", ".join([state["players"][p_id]["username"] for p_id in winners])
                     state["last_event"] = f"Jogo terminado! Empate entre {winner_names} com {max_score} pontos!"
                else: # Should not happen if there are players
                    state["winner"] = "Ninguém"
                    state["last_event"] = "Jogo terminado! Nenhum vencedor."
                winner_info_str = state["winner"]
                logger.info(f"Game finished for room {room_code}. Winner: {winner_info_str}")
                # TODO: Award prizes based on winner user_ids

        update_game_state(socketio, room_code, state)

    @socketio.on("get_game_state_5_5")
    def handle_get_game_state_5_5(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
             # Cannot easily get room_code without user being authenticated and in a room
             # Maybe just log the error or emit to SID if possible?
             logger.warning(f"Unauthenticated user with SID {sid} tried to get 5_5 game state.")
             emit("error", {"message": "Autenticação necessária."}, room=sid)
             return
             
        room_code = data.get("room_code") # Client should provide room code
        if not room_code:
             emit("error", {"message": "Código da sala não fornecido."}, room=sid)
             return
             
        state = get_game_state(room_code)
        if state:
            # Maybe filter state before sending? For now, send full state.
            emit("update_state_5_5", state, room=sid)
            logger.debug(f"Sent Jogo 5:5 state to user {user_id} (SID: {sid}) for room {room_code}")
        else:
            logger.warning(f"No Jogo 5:5 state found for room {room_code} on request from user {user_id} (SID: {sid})")
            emit("error", {"message": "Nenhum jogo 5:5 ativo nesta sala."}, room=sid)

    logger.info("Jogo 5:5 events registered.")

# Note: The update_game_state helper function needs socketio instance.
# It might be better to pass socketio to it or make it part of the class/registration.
# For now, passing it in handle_start_5_5_game and handle_ask_question_5_5.

