# -*- coding: utf-8 -*-
import random
import logging
from flask_socketio import emit
from flask import request
from sqlalchemy import func
from src.models.user import db, User # Import User
from src.models.game import Player, GameRoom

logger = logging.getLogger(__name__)

# Game state storage
game_states_ladrao = {}

def register_pegue_ladrao_events(socketio, get_authenticated_user_id):

    @socketio.on("start_pegue_ladrao")
    def handle_start_pegue_ladrao(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return # Error emitted by get_authenticated_user_id

        room_code = data.get("room_code")
        room = GameRoom.query.filter_by(room_code=room_code).first()

        if not room:
            emit("error", {"message": "Sala não encontrada."}, room=sid)
            return

        # Check if the user sending the request is the host of the room using user_id
        if room.host_id != user_id:
            emit("error", {"message": "Apenas o host pode iniciar o jogo."}, room=sid)
            return

        players = room.players # Get Player objects
        active_players = [p for p in players if p.sid is not None]
        player_count = len(active_players)
        
        # Rules specify 8 players (5 in one village, 3 in another)
        if player_count != 8:
            emit("error", {"message": f"O jogo Pegue o Ladrão requer exatamente 8 jogadores ativos. Atuais: {player_count}"}, room=sid)
            return

        logger.info(f"Iniciando Pegue o Ladrão na sala {room_code} pelo Host User ID: {user_id}")
        room.current_game_type = "pegue_ladrao"
        db.session.commit()

        # Initialize game state using active players' SIDs
        player_sids = [p.sid for p in active_players]
        random.shuffle(player_sids)

        village1_sids = player_sids[:5]
        village2_sids = player_sids[5:]

        thief_sid = random.choice(player_sids)
        thief_village = 1 if thief_sid in village1_sids else 2

        # Initial gold (assuming 10 as per description)
        player_gold = {p.sid: 10 for p in active_players}

        game_states_ladrao[room_code] = {
            "players": player_sids, # List of active SIDs
            "village1": village1_sids,
            "village2": village2_sids,
            "thief": thief_sid,
            "thief_village": thief_village,
            "player_gold": player_gold,
            "round": 1,
            "max_rounds": 10,
            "exiled_this_round": {1: None, 2: None}, # {village_num: exiled_sid}
            "votes": {1: {}, 2: {}}, # {village_num: {voter_sid: voted_sid}}
            "game_over": False,
            "winner_village": None,
            "winner_player": None, # Player SID with most gold
            "loser_player": None, # Player SID with least gold in losing village
        }

        # Send state specific to each player (revealing their role)
        for p_sid in player_sids:
             emit("game_started", {"game_type": "pegue_ladrao", "initial_state": get_public_ladrao_state(room_code, p_sid)}, room=p_sid)
        # emit("game_started", {"game_type": "pegue_ladrao"}, to=room_code) # Generic notification
        start_ladrao_round(socketio, room_code)

    @socketio.on("ladrao_vote_exile")
    def handle_ladrao_vote_exile(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        voted_sid = data.get("voted_sid")

        if room_code not in game_states_ladrao or game_states_ladrao[room_code]["game_over"]:
            return

        state = game_states_ladrao[room_code]

        # Check if voter SID is part of the current active players for this game instance
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo."}, room=sid)
            return

        # Determine voter's village
        voter_village = 0
        if sid in state["village1"]:
            voter_village = 1
        elif sid in state["village2"]:
            voter_village = 2
        else: # Should not happen if sid is in state["players"]
             emit("error", {"message": "Erro interno: Jogador ativo não encontrado em nenhuma vila."}, room=sid)
             return
             
        # Check if voted player SID is valid and in the same village
        if voted_sid not in state["players"]:
             emit("error", {"message": "O jogador votado não é válido ou não está mais ativo."}, room=sid)
             return
             
        if (voter_village == 1 and voted_sid not in state["village1"]) or \
           (voter_village == 2 and voted_sid not in state["village2"]):
            emit("error", {"message": "Você só pode votar para exilar alguém da sua própria vila."}, room=sid)
            return
            
        if sid in state["votes"][voter_village]:
            emit("error", {"message": "Você já votou nesta rodada."}, room=sid)
            return

        logger.info(f"[Pegue o Ladrão {room_code}] Jogador SID {sid} (User: {user_id}, Vila {voter_village}) votou para exilar {voted_sid}")
        state["votes"][voter_village][sid] = voted_sid
        emit("player_voted", {"voter_sid": sid, "village": voter_village}, to=room_code) # Notify UI, but not who was voted

        # Check if all active players in the village have voted
        village_sids = state[f"village{voter_village}"]
        # Filter village_sids to only include currently active players in state["players"]
        active_village_sids = [vsid for vsid in village_sids if vsid in state["players"]]
        if len(state["votes"][voter_village]) == len(active_village_sids):
            logger.info(f"[Pegue o Ladrão {room_code}] Todos da Vila {voter_village} votaram.")
            process_ladrao_exile(socketio, room_code, voter_village)

# --- Helper Functions (Mostly SID based logic within round, which is okay) --- 

def start_ladrao_round(socketio, room_code):
    if room_code not in game_states_ladrao or game_states_ladrao[room_code]["game_over"]:
        return

    state = game_states_ladrao[room_code]
    round_num = state["round"]

    logger.info(f"[Pegue o Ladrão {room_code}] Iniciando Rodada {round_num}")
    state["exiled_this_round"] = {1: None, 2: None}
    state["votes"] = {1: {}, 2: {}}

    emit("round_start", {"round": round_num}, to=room_code)
    # Send updated state to each player individually
    for p_sid in state["players"]:
        emit("update_game_state", get_public_ladrao_state(room_code, p_sid), room=p_sid)
    # No timer specified, relies on players voting

def process_ladrao_exile(socketio, room_code, village_num):
    if room_code not in game_states_ladrao or game_states_ladrao[room_code]["game_over"]:
        return

    state = game_states_ladrao[room_code]
    votes = state["votes"][village_num]
    village_sids = state[f"village{village_num}"]
    active_village_sids = [vsid for vsid in village_sids if vsid in state["players"]]

    if len(votes) != len(active_village_sids):
        logger.warning(f"[Pegue o Ladrão {room_code}] Tentativa de processar exílio da Vila {village_num} prematuramente. Votos: {len(votes)}, Ativos: {len(active_village_sids)}")
        return

    # Count votes
    vote_counts = {}
    for voter, voted in votes.items():
        # Ensure the voted player is still active before counting vote
        if voted in state["players"]:
            vote_counts[voted] = vote_counts.get(voted, 0) + 1

    # Determine exiled player (handle ties by random choice among tied)
    max_votes = 0
    tied_players = []
    if vote_counts:
        max_votes = max(vote_counts.values())
        tied_players = [sid for sid, count in vote_counts.items() if count == max_votes]
    
    exiled_sid = random.choice(tied_players) if tied_players else None 

    if exiled_sid:
        logger.info(f"[Pegue o Ladrão {room_code}] Jogador {exiled_sid} foi exilado da Vila {village_num} com {max_votes} votos.")
        state["exiled_this_round"][village_num] = exiled_sid
        # NOTE: Player is NOT removed from state["players"] or state[f"village{village_num}"]
        # They just don't participate further if exiled? Rules are a bit vague.
        # Let's assume they are just marked as exiled for the round result processing.
        
        # Check if thief was exiled
        if exiled_sid == state["thief"]:
            logger.info(f"[Pegue o Ladrão {room_code}] O ladrão ({exiled_sid}) foi exilado pela Vila {village_num}!")
            # Thief doesn't steal gold this round
            pass 
        
    else:
        logger.info(f"[Pegue o Ladrão {room_code}] Ninguém foi exilado da Vila {village_num} (sem votos válidos ou empate sem votos?).")
        # Ensure the state reflects no one was exiled
        state["exiled_this_round"][village_num] = None # Explicitly set to None

    emit("village_exiled", {"village": village_num, "exiled_sid": exiled_sid, "votes": vote_counts}, to=room_code)

    # Check if both villages have completed their exile process for the round
    # Use a flag or check if both entries in exiled_this_round are not None
    # Need a way to know if a village *finished* voting, even if result was None
    # Let's add a flag
    if f"village_{village_num}_voted" not in state:
        state[f"village_{village_num}_voted"] = True
    else:
        state[f"village_{village_num}_voted"] = True
        
    if state.get("village_1_voted") and state.get("village_2_voted"):
        end_ladrao_round(socketio, room_code)

def end_ladrao_round(socketio, room_code):
    if room_code not in game_states_ladrao or game_states_ladrao[room_code]["game_over"]:
        return

    state = game_states_ladrao[room_code]
    round_num = state["round"]
    logger.info(f"[Pegue o Ladrão {room_code}] Finalizando Rodada {round_num}")

    # Thief steals gold if not exiled
    thief_sid = state["thief"]
    thief_village = state["thief_village"]
    # Check if the thief is still an active player
    if thief_sid in state["players"]:
        if state["exiled_this_round"].get(thief_village) != thief_sid:
            state["player_gold"][thief_sid] = state["player_gold"].get(thief_sid, 0) + 1
            logger.info(f"[Pegue o Ladrão {room_code}] Ladrão ({thief_sid}) não foi exilado e roubou 1 ouro.")
            emit("thief_stole", {"thief_sid": thief_sid, "new_gold": state["player_gold"][thief_sid]}, to=room_code)
        else:
            logger.info(f"[Pegue o Ladrão {room_code}] Ladrão ({thief_sid}) foi exilado e não roubou ouro.")
            emit("thief_caught", {"thief_sid": thief_sid, "village": thief_village}, to=room_code)
    else:
        logger.warning(f"[Pegue o Ladrão {room_code}] Ladrão ({thief_sid}) não está mais ativo, não pode roubar.")

    emit("round_end", {"round": round_num, "exiled": state["exiled_this_round"], "player_gold": state["player_gold"]}, to=room_code)

    # Check game end condition
    if round_num >= state["max_rounds"]:
        state["game_over"] = True
        max_rounds_val = state["max_rounds"]
        logger.info(f"[Pegue o Ladrão {room_code}] Fim de jogo após {max_rounds_val} rodadas.")

        # Determine winning village (village without the thief)
        state["winner_village"] = 1 if state["thief_village"] == 2 else 2
        losing_village = state["thief_village"]
        winner_village_val = state["winner_village"]
        logger.info(f"[Pegue o Ladrão {room_code}] Vila Vencedora: {winner_village_val}")

        # Determine player with most gold overall (winner)
        active_player_gold = {sid: gold for sid, gold in state["player_gold"].items() if sid in state["players"]}
        if active_player_gold:
            max_gold = -1
            winners = []
            for sid, gold in active_player_gold.items():
                if gold > max_gold:
                    max_gold = gold
                    winners = [sid]
                elif gold == max_gold:
                    winners.append(sid)
            state["winner_player"] = random.choice(winners) if winners else None
            winner_player_val = state["winner_player"]
        if active_player_gold:
            max_gold = -1
            winners = []
            for sid, gold in active_player_gold.items():
                if gold > max_gold:
                    max_gold = gold
                    winners = [sid]
                elif gold == max_gold:
                    winners.append(sid)
            state["winner_player"] = random.choice(winners) if winners else None
            winner_player_val = state["winner_player"]
            logger.info(f"[Pegue o Ladrão {room_code}] Vencedor (mais ouro): {winner_player_val} com {max_gold} ouro.")
        else:
             state["winner_player"] = None

        # Determine player with least gold in the losing village (loser)
        losing_village_sids = state[f"village{losing_village}"]
        active_losing_village_sids = [sid for sid in losing_village_sids if sid in state["players"]]
        if active_losing_village_sids:
            min_gold = float("inf")
            losers = []
            for sid in active_losing_village_sids:
                 gold = active_player_gold.get(sid, 0)
                 if gold < min_gold:
                     min_gold = gold
                     losers = [sid]
                 elif gold == min_gold:
                     losers.append(sid)
            state["loser_player"] = random.choice(losers) if losers else None
            loser_player_val = state["loser_player"]
            logger.info(f"[Pegue o Ladrão {room_code}] Perdedor (menos ouro na vila {losing_village}): {loser_player_val} com {min_gold} ouro.")
        else:
            state["loser_player"] = None

        # TODO: Award Tokens/Grenades based on winner/loser status
        # Need to map SIDs back to User IDs for DB updates
        # winner_user_id = Player.query.filter_by(sid=state["winner_player"]).first().user_id if state["winner_player"] else None
        # loser_user_id = Player.query.filter_by(sid=state["loser_player"]).first().user_id if state["loser_player"] else None
        # ... update User model ...

        emit("game_over", {
            "winner_village": state["winner_village"],
            "winner_player": state["winner_player"],
            "loser_player": state["loser_player"],
            "final_gold": state["player_gold"],
            "thief": state["thief"]
        }, to=room_code)
        # Clean up game state after a delay?
        # socketio.start_background_task(lambda: game_states_ladrao.pop(room_code, None), 10)
        return

    # Proceed to next round
    state["round"] += 1
    # Reset village voted flags for next round
    state["village_1_voted"] = False
    state["village_2_voted"] = False
    start_ladrao_round(socketio, room_code)

def get_public_ladrao_state(room_code, requesting_sid):
    """Returns a version of the game state safe to send to clients."""
    if room_code not in game_states_ladrao:
        return None

    state = game_states_ladrao[room_code]
    public_state = {
        "players": state["players"], # List of active SIDs
        "village1": state["village1"],
        "village2": state["village2"],
        "player_gold": state["player_gold"],
        "round": state["round"],
        "max_rounds": state["max_rounds"],
        "exiled_this_round": state["exiled_this_round"],
        "game_over": state["game_over"],
        "winner_village": state["winner_village"],
        "winner_player": state["winner_player"],
        "loser_player": state["loser_player"],
        "my_village_votes": {},
        "my_role": "unknown",
        "my_village": None
    }
    
    # Add thief info if game is over
    if state["game_over"]:
        public_state["thief"] = state["thief"]
        public_state["thief_village"] = state["thief_village"]

    # Add role and village-specific vote info for the requesting player
    if requesting_sid and requesting_sid in state["players"]:
        if requesting_sid == state["thief"]:
            public_state["my_role"] = "thief"
        else:
             public_state["my_role"] = "villager"
             
        my_village = 0
        if requesting_sid in state["village1"]:
            my_village = 1
        elif requesting_sid in state["village2"]:
            my_village = 2
            
        if my_village > 0:
            public_state["my_village"] = my_village
            # Send only the votes cast *by* players in the requesting player's village
            public_state["my_village_votes"] = {voter: voted for voter, voted in state["votes"].get(my_village, {}).items()}
            
    return public_state

