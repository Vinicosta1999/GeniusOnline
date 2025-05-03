# -*- coding: utf-8 -*-
import random
import logging
from flask_socketio import emit
from flask import request
from src.models.user import db, User # Import User
from src.models.game import Player, GameRoom

logger = logging.getLogger(__name__)

# Game state storage (in-memory, consider persistent storage for production)
game_states = {}

def register_jogo_zumbi_events(socketio, get_authenticated_user_id):

    @socketio.on("start_jogo_zumbi")
    def handle_start_jogo_zumbi(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return # Error emitted by get_authenticated_user_id

        room_code = data.get("room_code")
        room = GameRoom.query.filter_by(room_code=room_code).first()

        if not room:
            emit("error", {"message": "Sala não encontrada."}, room=sid)
            return

        # Check if the user sending the request is the host of the room
        if room.host_id != user_id:
            emit("error", {"message": "Apenas o host pode iniciar o jogo."}, room=sid)
            return

        players = room.players # These are Player objects
        active_players = [p for p in players if p.sid is not None]
        player_count = len(active_players)

        if player_count < 3: # Minimum players needed? Adjust as per rules
            emit("error", {"message": f"Jogadores insuficientes para iniciar o Jogo de Zumbi (mínimo 3). Atuais: {player_count}"}, room=sid)
            return

        logger.info(f"Iniciando Jogo de Zumbi na sala {room_code} pelo Host User ID: {user_id}")
        room.current_game_type = "jogo_zumbi"
        db.session.commit()

        # Initialize game state
        player_sids = [p.sid for p in active_players] # Use current SIDs
        player_user_ids = {p.sid: p.user_id for p in active_players} # Map SID to User ID
             
        zombies = random.sample(player_sids, 2) # Select 2 initial zombies by SID
        human_points = {sid: 0 for sid in player_sids if sid not in zombies}
        antidotes = {sid: 1 for sid in player_sids} # Each player starts with 1 antidote
        # Fetch grenades for active players based on their user_id
        grenades = {}
        for p in active_players:
             grenades[p.sid] = p.user.grenades if p.user.grenades is not None else 0 # Ensure grenades is not None

        game_states[room_code] = {
            "players": player_sids, # List of active SIDs
            "player_user_ids": player_user_ids, # Map SID -> User ID
            "zombies": list(zombies),
            "humans": list(human_points.keys()),
            "human_points": human_points,
            "antidotes": antidotes,
            "grenades": grenades,
            "round": 1,
            "round_timer": None, # Timer object
            "round_end_time": None,
            "round_touches": {sid: None for sid in player_sids}, # Who touched whom this round
            "used_antidote_this_round": set(), # Track who used antidote this round
            "game_over": False,
            "winner": None,
            "max_rounds": 3
        }

        emit("game_started", {"game_type": "jogo_zumbi", "initial_state": get_public_game_state(room_code)}, to=room_code)
        start_zumbi_round(socketio, room_code)

    @socketio.on("zumbi_touch")
    def handle_zumbi_touch(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        target_sid = data.get("target_sid")

        if room_code not in game_states or game_states[room_code]["game_over"]:
            return

        state = game_states[room_code]
        # Check if both sids are currently active players in this game instance
        if sid not in state["players"] or target_sid not in state["players"] or sid == target_sid:
            emit("error", {"message": "Ação inválida (jogador/alvo não está no jogo ou é você mesmo)."}, room=sid)
            return
            
        if state["round_touches"].get(sid) is not None:
            emit("error", {"message": "Você já tocou alguém nesta rodada."}, room=sid)
            return

        logger.info(f"[Jogo Zumbi {room_code}] Jogador SID {sid} (User: {user_id}) tocou {target_sid}")
        state["round_touches"][sid] = target_sid
        emit("player_touched", {"toucher_sid": sid, "touched_sid": target_sid}, to=room_code) # Notify everyone for UI feedback
        # Logic for points/transformation happens at round end

    # Moved inside register_jogo_zumbi_events
    @socketio.on("use_antidote")
    def handle_use_antidote(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")

        if room_code not in game_states or game_states[room_code]["game_over"]:
            return

        state = game_states[room_code]
        if sid not in state["players"]:
             emit("error", {"message": "Você não está ativo neste jogo."}, room=sid)
             return
            
        if state["antidotes"].get(sid, 0) > 0:
            state["antidotes"][sid] -= 1
            state["used_antidote_this_round"].add(sid) # Track usage for this round
            logger.info(f"[Jogo Zumbi {room_code}] Jogador SID {sid} (User: {user_id}) usou um antídoto.")
            emit("antidote_used", {"sid": sid, "remaining": state["antidotes"][sid]}, to=room_code)
            emit("update_game_state", get_public_game_state(room_code), to=room_code)
        else:
            emit("error", {"message": "Você não tem antídotos."}, room=sid)

    # Moved inside register_jogo_zumbi_events
    @socketio.on("buy_antidote")
    def handle_buy_antidote(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        grenade_cost = 5

        if room_code not in game_states or game_states[room_code]["game_over"]:
            return

        state = game_states[room_code]
        # Check if player is active in this game instance
        if sid not in state["players"]:
             emit("error", {"message": "Você não está ativo neste jogo."}, room=sid)
             return
             
        player_grenades = state["grenades"].get(sid, 0)

        if player_grenades >= grenade_cost:
            state["grenades"][sid] -= grenade_cost
            state["antidotes"][sid] = state["antidotes"].get(sid, 0) + 1
            
            # Optional: Update User model grenades in DB
            # Fetch the correct user_id using the SID map
            actual_user_id = state.get("player_user_ids", {}).get(sid)
            if actual_user_id:
                user = User.query.get(actual_user_id)
                if user:
                    user.grenades = state["grenades"][sid] # Update user's grenade count in DB
                    db.session.commit()
                else: 
                    logger.error(f"[Jogo Zumbi {room_code}] User not found for ID {actual_user_id} (from SID {sid}) when buying antidote.")
            else:
                 logger.error(f"[Jogo Zumbi {room_code}] Could not find User ID for SID {sid} when buying antidote.")
            
            logger.info(f"[Jogo Zumbi {room_code}] Jogador SID {sid} (User: {user_id}) comprou um antídoto.")
            emit("antidote_bought", {"sid": sid, "remaining_antidotes": state["antidotes"][sid], "remaining_grenades": state["grenades"][sid]}, to=room_code)
            emit("update_game_state", get_public_game_state(room_code), to=room_code)
        else:
            emit("error", {"message": f"Granadas insuficientes. Custo: {grenade_cost}"}, room=sid)

# --- Helper Functions (No change needed for auth here) --- 

def start_zumbi_round(socketio, room_code):
    if room_code not in game_states or game_states[room_code]["game_over"]:
        return

    state = game_states[room_code]
    round_num = state["round"]
    # round_duration = 30 * 60 # 30 minutes in seconds
    round_duration = 60 # 1 minute for testing

    logger.info(f"[Jogo Zumbi {room_code}] Iniciando Rodada {round_num}")
    state["round_touches"] = {sid: None for sid in state["players"]}
    state["used_antidote_this_round"] = set() # Reset antidote usage tracking
    state["round_end_time"] = socketio.time() + round_duration

    emit("round_start", {"round": round_num, "duration": round_duration, "end_timestamp": state["round_end_time"]}, to=room_code)
    emit("update_game_state", get_public_game_state(room_code), to=room_code)

    # Schedule end of round
    if state["round_timer"]:
        try: state["round_timer"].cancel() # Cancel previous timer if any
        except: pass
    state["round_timer"] = socketio.start_background_task(end_zumbi_round, socketio, room_code, round_duration)

def end_zumbi_round(socketio, room_code, delay):
    socketio.sleep(delay)
    logger.info(f"[Jogo Zumbi {room_code}] Finalizando Rodada {game_states.get(room_code, {}).get('round', 'N/A')}")

    if room_code not in game_states or game_states[room_code]["game_over"]:
        logger.warning(f"[Jogo Zumbi {room_code}] end_zumbi_round called but game state missing or game over.")
        return

    state = game_states[room_code]
    touches = state["round_touches"]
    used_antidote = state["used_antidote_this_round"]
    newly_infected = []
    protected_by_antidote_list = [] # Track who was saved by antidote

    # Process touches and transformations
    for toucher_sid, touched_sid in touches.items():
        # Ensure both players are still active before processing touch
        if toucher_sid not in state["players"] or (touched_sid is not None and touched_sid not in state["players"]):
            logger.info(f"[Jogo Zumbi {room_code}] Skipping touch processing involving inactive player(s): {toucher_sid} -> {touched_sid}")
            continue
            
        if touched_sid is None: # Player didn't touch anyone
            if toucher_sid in state["humans"]:
                logger.info(f"[Jogo Zumbi {room_code}] Humano {toucher_sid} não tocou ninguém e virou zumbi.")
                newly_infected.append(toucher_sid)
            continue # Zombies don't change if they don't touch

        # --- Touch Logic --- 
        is_toucher_human = toucher_sid in state["humans"]
        is_toucher_zombie = toucher_sid in state["zombies"]
        is_touched_human = touched_sid in state["humans"]
        is_touched_zombie = touched_sid in state["zombies"]

        # Human touched Human
        if is_toucher_human and is_touched_human:
            state["human_points"][toucher_sid] = state["human_points"].get(toucher_sid, 0) + 1
            logger.info(f"[Jogo Zumbi {room_code}] Humano {toucher_sid} tocou humano {touched_sid} (+1 ponto).")

        # Human touched Zombie
        elif is_toucher_human and is_touched_zombie:
            logger.info(f"[Jogo Zumbi {room_code}] Humano {toucher_sid} tocou zumbi {touched_sid} (sem efeito).")
            pass 

        # Zombie touched Human
        elif is_toucher_zombie and is_touched_human:
            if touched_sid in used_antidote:
                 protected_by_antidote_list.append(touched_sid)
                 logger.info(f"[Jogo Zumbi {room_code}] Zumbi {toucher_sid} tocou humano {touched_sid}, mas ele usou antídoto.")
            else:
                logger.info(f"[Jogo Zumbi {room_code}] Zumbi {toucher_sid} tocou humano {touched_sid}. {touched_sid} virou zumbi.")
                newly_infected.append(touched_sid)

        # Zombie touched Zombie
        elif is_toucher_zombie and is_touched_zombie:
            logger.info(f"[Jogo Zumbi {room_code}] Zumbi {toucher_sid} tocou zumbi {touched_sid} (sem efeito).")
            pass

    # Apply transformations (remove duplicates from newly_infected)
    unique_newly_infected = list(set(newly_infected))
    for sid in unique_newly_infected:
        if sid in state["humans"]:
            state["humans"].remove(sid)
            if sid in state["human_points"]:
                del state["human_points"][sid]
            if sid not in state["zombies"]:
                 state["zombies"].append(sid)

    emit("round_end", {"round": state["round"], "newly_infected": unique_newly_infected, "protected": protected_by_antidote_list}, to=room_code)

    # Check game end conditions
    # Update active humans list after potential infections
    current_humans = [h for h in state["humans"] if h in state["players"]]
    if not current_humans: # All active players are zombies
        state["game_over"] = True
        state["winner"] = "zombies"
        logger.info(f"[Jogo Zumbi {room_code}] Fim de jogo! Todos os jogadores ativos viraram zumbis.")
        emit("game_over", {"winner": "zombies", "final_state": get_public_game_state(room_code)}, to=room_code)
        # Clean up game state after a delay?
        socketio.start_background_task(lambda rc=room_code: game_states.pop(rc, None), 10)
        return

    if state["round"] >= state["max_rounds"]:
        state["game_over"] = True
        if current_humans:
            # Human with most points among active humans wins
            active_human_points = {sid: pts for sid, pts in state["human_points"].items() if sid in current_humans}
            winner_sid = max(active_human_points, key=active_human_points.get) if active_human_points else None
            state["winner"] = winner_sid # Store SID of the winner
            logger.info(f"[Jogo Zumbi {room_code}] Fim de jogo! Humano {winner_sid} venceu com mais pontos.")
            emit("game_over", {"winner": winner_sid, "final_state": get_public_game_state(room_code)}, to=room_code)
        else: # Should have been caught above, but as a fallback
            state["winner"] = "zombies"
            logger.info(f"[Jogo Zumbi {room_code}] Fim de jogo! Última rodada e não há humanos ativos.")
            emit("game_over", {"winner": "zombies", "final_state": get_public_game_state(room_code)}, to=room_code)
        # Clean up game state after a delay?
        socketio.start_background_task(lambda rc=room_code: game_states.pop(rc, None), 10)
        return

    # Proceed to next round
    state["round"] += 1
    start_zumbi_round(socketio, room_code)

def get_public_game_state(room_code):
    """Returns a version of the game state safe to send to all clients."""
    if room_code not in game_states:
        return None
    
    state = game_states[room_code]
    # Send only necessary info. SIDs are needed for client-side identification.
    return {
        "players": state["players"], # List of SIDs currently in game
        "zombies": state["zombies"], # List of SIDs that are zombies
        "humans": state["humans"],   # List of SIDs that are humans
        "human_points": state["human_points"], # Dict {sid: points}
        "antidotes": state["antidotes"], # Dict {sid: count}
        "grenades": state["grenades"],   # Dict {sid: count}
        "round": state["round"],
        "round_end_time": state["round_end_time"],
        "game_over": state["game_over"],
        "winner": state["winner"], # SID of winner or 'zombies'
        "max_rounds": state["max_rounds"]
    }

