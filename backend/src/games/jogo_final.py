# -*- coding: utf-8 -*-
import random
import logging
from flask_socketio import emit
from flask import request
from src.models.user import db, User # Import User
from src.models.game import Player, GameRoom

logger = logging.getLogger(__name__)

# Game state storage for the Final
game_states_final = {}

# --- Sub-game Logic (Placeholders/Simplified - No auth changes needed here) ---

def initialize_poker_indiano(players):
    # Simplified: Deal one card (1-10) to each player
    deck = list(range(1, 11))
    random.shuffle(deck)
    # Ensure players list contains SIDs
    player_sids = [p for p in players if isinstance(p, str)]
    if len(player_sids) != 2:
        logger.error(f"[Poker Indiano Init] Expected 2 player SIDs, got: {players}")
        return None # Or handle error appropriately
        
    return {
        "type": "poker_indiano",
        "player_cards": {player_sids[0]: deck.pop(), player_sids[1]: deck.pop()},
        "bets": {sid: 0 for sid in player_sids},
        "pot": 0,
        "current_player": player_sids[0], # Player SID to bet/act
        "round_state": "betting", # betting, reveal
        "winner": None # SID of winner or "tie"
    }

def initialize_caca_imagem(players):
    # Simplified: 4 pairs (8 cards total)
    symbols = ["A", "B", "C", "D"]
    deck = symbols * 2
    random.shuffle(deck)
    grid_size = 8
    player_sids = [p for p in players if isinstance(p, str)]
    if len(player_sids) != 2:
        logger.error(f"[Caca Imagem Init] Expected 2 player SIDs, got: {players}")
        return None
        
    return {
        "type": "caca_imagem",
        "grid": deck,
        "revealed": [False] * grid_size,
        "matched_pairs": {sid: [] for sid in player_sids},
        "current_player": player_sids[0],
        "turn_selection": [], # Indices of cards flipped this turn
        "winner": None # SID of winner or "tie"
    }

def initialize_gyul_hap(players):
    # Extremely simplified: Just a placeholder structure
    player_sids = [p for p in players if isinstance(p, str)]
    if len(player_sids) != 2:
        logger.error(f"[Gyul Hap Init] Expected 2 player SIDs, got: {players}")
        return None
        
    return {
        "type": "gyul_hap",
        "board": ["Card1", "Card2", "Card3", "Card4", "Card5", "Card6"], # Example board
        "scores": {sid: 0 for sid in player_sids},
        "winner": None # SID of winner or "tie"
    }

# --- Main Final Game Logic ---

def register_jogo_final_events(socketio, get_authenticated_user_id):

    @socketio.on("start_jogo_final")
    def handle_start_jogo_final(data):
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
            emit("error", {"message": "Apenas o host pode iniciar o jogo final."}, room=sid)
            return

        players = room.players # Get Player objects
        active_players = [p for p in players if p.sid is not None]
        player_count = len(active_players)

        # The final typically has 2 players
        if player_count != 2:
            emit("error", {"message": f"O Jogo Final requer exatamente 2 jogadores ativos. Atuais: {player_count}"}, room=sid)
            return

        logger.info(f"Iniciando Jogo Final na sala {room_code} pelo Host User ID: {user_id}")
        room.current_game_type = "jogo_final"
        db.session.commit()

        player_sids = [p.sid for p in active_players]
        player_user_ids = {p.sid: p.user_id for p in active_players} # Map SID to UserID for rewards

        # TODO: Implement advantage logic based on eliminated players
        advantages = {sid: [] for sid in player_sids} # Placeholder

        game_states_final[room_code] = {
            "players": player_sids, # List of active SIDs
            "player_user_ids": player_user_ids, # Map SID -> UserID
            "scores": {sid: 0 for sid in player_sids}, # Wins in sub-games
            "current_sub_game_index": 0,
            "sub_game_order": ["poker_indiano", "caca_imagem", "gyul_hap"], # Fixed order
            "current_sub_game_state": None,
            "advantages": advantages,
            "game_over": False,
            "overall_winner": None # SID of the overall winner
        }

        emit("game_started", {"game_type": "jogo_final", "initial_state": get_public_final_state(room_code)}, to=room_code)
        start_next_sub_game(socketio, room_code)

    # --- Event Handlers for Sub-Games (Using get_authenticated_user_id) ---

    @socketio.on("final_poker_action")
    def handle_poker_action(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        action = data.get("action") # e.g., "bet", "call", "fold"
        amount = data.get("amount", 0)

        if room_code not in game_states_final or game_states_final[room_code]["game_over"]:
            return
        state = game_states_final[room_code]
        sub_game_state = state.get("current_sub_game_state")

        # Check if player SID is active in this game instance
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo final."}, room=sid)
            return
            
        if not sub_game_state or sub_game_state["type"] != "poker_indiano" or sub_game_state.get("winner") is not None:
            emit("error", {"message": "Ação inválida: Jogo de Poker Indiano não ativo ou já finalizado."}, room=sid)
            return
            
        if sid != sub_game_state["current_player"]:
            emit("error", {"message": "Não é sua vez de agir no Poker Indiano."}, room=sid)
            return
            
        logger.info(f"[Jogo Final - Poker {room_code}] Jogador SID {sid} (User: {user_id}) action: {action} ({amount})")
        
        # --- Implement Poker Logic --- 
        opponent_sid = next(p for p in state["players"] if p != sid)
        
        try: # Add error handling for amounts
            bet_amount = int(amount) if action == "bet" else 0
        except (ValueError, TypeError):
             emit("error", {"message": "Valor da aposta inválido."}, room=sid)
             return

        if action == "bet":
            # TODO: Validate bet amount vs player resources (grenades?)
            # Assuming bet is valid for now
            sub_game_state["bets"][sid] += bet_amount
            sub_game_state["pot"] += bet_amount
            sub_game_state["current_player"] = opponent_sid # Next player's turn
            emit("update_sub_game_state", sub_game_state, to=room_code)
        elif action == "call":
            call_amount = sub_game_state["bets"][opponent_sid] - sub_game_state["bets"][sid]
            if call_amount < 0: call_amount = 0 # Cannot call for less than 0
            # TODO: Validate call amount vs player resources
            sub_game_state["bets"][sid] += call_amount
            sub_game_state["pot"] += call_amount
            sub_game_state["round_state"] = "reveal"
            # Determine winner
            card_sid = sub_game_state["player_cards"][sid]
            card_opponent = sub_game_state["player_cards"][opponent_sid]
            winner = None
            if card_sid > card_opponent:
                winner = sid
            elif card_opponent > card_sid:
                winner = opponent_sid
            else: 
                winner = "tie" 
            sub_game_state["winner"] = winner
            logger.info(f"[Jogo Final - Poker {room_code}] Reveal: {sid}({card_sid}) vs {opponent_sid}({card_opponent}). Winner: {winner}")
            emit("update_sub_game_state", sub_game_state, to=room_code)
            end_sub_game(socketio, room_code, winner)
        elif action == "fold":
            winner = opponent_sid
            sub_game_state["winner"] = winner
            sub_game_state["round_state"] = "reveal"
            logger.info(f"[Jogo Final - Poker {room_code}] Jogador {sid} foldou. Vencedor: {opponent_sid}")
            emit("update_sub_game_state", sub_game_state, to=room_code)
            end_sub_game(socketio, room_code, winner)
        else:
            emit("error", {"message": "Ação desconhecida no Poker Indiano."}, room=sid)

    @socketio.on("final_caca_flip")
    def handle_caca_flip(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        index = data.get("index")

        if room_code not in game_states_final or game_states_final[room_code]["game_over"]:
            return
        state = game_states_final[room_code]
        sub_game_state = state.get("current_sub_game_state")

        # Check if player SID is active
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo final."}, room=sid)
            return

        if not sub_game_state or sub_game_state["type"] != "caca_imagem" or sub_game_state.get("winner") is not None:
            emit("error", {"message": "Ação inválida: Jogo Caça Imagem não ativo ou já finalizado."}, room=sid)
            return
            
        if sid != sub_game_state["current_player"]:
            emit("error", {"message": "Não é sua vez de jogar no Caça Imagem."}, room=sid)
            return
            
        try:
            card_index = int(index)
            if not (0 <= card_index < len(sub_game_state["grid"])):
                 raise ValueError("Index out of bounds")
            if sub_game_state["revealed"][card_index]:
                 emit("error", {"message": "Esta carta já foi revelada."}, room=sid)
                 return
        except (ValueError, TypeError):
            emit("error", {"message": "Seleção de carta inválida."}, room=sid)
            return
            
        if len(sub_game_state["turn_selection"]) >= 2:
             emit("error", {"message": "Você já virou duas cartas nesta jogada."}, room=sid)
             return

        logger.info(f"[Jogo Final - Caca Imagem {room_code}] Jogador SID {sid} (User: {user_id}) virou carta no índice {card_index}")
        sub_game_state["revealed"][card_index] = True
        sub_game_state["turn_selection"].append(card_index)
        emit("update_sub_game_state", sub_game_state, to=room_code)

        # Check after second flip
        if len(sub_game_state["turn_selection"]) == 2:
            idx1, idx2 = sub_game_state["turn_selection"]
            card1 = sub_game_state["grid"][idx1]
            card2 = sub_game_state["grid"][idx2]

            if card1 == card2:
                logger.info(f"[Jogo Final - Caca Imagem {room_code}] Jogador {sid} encontrou um par: {card1}")
                sub_game_state["matched_pairs"].setdefault(sid, []).append(card1)
                sub_game_state["turn_selection"] = [] # Reset for next turn (same player)
                
                # Check if all pairs found
                total_pairs_found = sum(len(pairs) for pairs in sub_game_state["matched_pairs"].values())
                if total_pairs_found == len(sub_game_state["grid"]) // 2:
                    # Game over - determine winner by most pairs
                    score1 = len(sub_game_state["matched_pairs"].get(state["players"][0], []))
                    score2 = len(sub_game_state["matched_pairs"].get(state["players"][1], []))
                    winner = None
                    if score1 > score2:
                        winner = state["players"][0]
                    elif score2 > score1:
                        winner = state["players"][1]
                    else:
                        winner = "tie"
                    sub_game_state["winner"] = winner
                    logger.info(f"[Jogo Final - Caca Imagem {room_code}] Fim do sub-jogo. Vencedor: {winner}")
                    emit("update_sub_game_state", sub_game_state, to=room_code)
                    end_sub_game(socketio, room_code, winner)
                else:
                    # Let player go again
                    emit("update_sub_game_state", sub_game_state, to=room_code) 
            else:
                logger.info(f"[Jogo Final - Caca Imagem {room_code}] Jogador {sid} não encontrou par.")
                # Schedule flip back after a delay
                socketio.start_background_task(flip_back_cards, socketio, room_code, idx1, idx2)
                # Switch player
                opponent_sid = next(p for p in state["players"] if p != sid)
                sub_game_state["current_player"] = opponent_sid
                sub_game_state["turn_selection"] = []
                # Don't emit update immediately, wait for flip_back_cards to emit

    @socketio.on("final_gyulhap_claim")
    def handle_gyulhap_claim(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        claimed_cards_indices = data.get("indices") # Indices of 3 cards claimed
        
        if room_code not in game_states_final or game_states_final[room_code]["game_over"]:
            return
        state = game_states_final[room_code]
        sub_game_state = state.get("current_sub_game_state")

        # Check if player SID is active
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo final."}, room=sid)
            return

        if not sub_game_state or sub_game_state["type"] != "gyul_hap" or sub_game_state.get("winner") is not None:
            emit("error", {"message": "Ação inválida: Jogo Gyul Hap não ativo ou já finalizado."}, room=sid)
            return
            
        # --- Implement Gyul Hap Logic --- 
        # This requires complex validation based on card features.
        # Simplified: Assume any claim is valid for now.
        is_valid_hap = False # Default to false
        try:
            if isinstance(claimed_cards_indices, list) and len(claimed_cards_indices) == 3:
                 # Placeholder validation - replace with real Gyul Hap rules
                 logger.info(f"[Jogo Final - Gyul Hap {room_code}] Validando Hap reivindicado por {sid} (User: {user_id}): {claimed_cards_indices}")
                 # Example: Check if indices are valid and unique
                 board_size = len(sub_game_state.get("board", []))
                 if all(0 <= i < board_size for i in claimed_cards_indices) and len(set(claimed_cards_indices)) == 3:
                     # *** Add real Gyul Hap set validation logic here ***
                     is_valid_hap = True # Assume valid for now
                 else:
                      logger.warning(f"[Jogo Final - Gyul Hap {room_code}] Índices inválidos ou duplicados: {claimed_cards_indices}")
            else:
                 logger.warning(f"[Jogo Final - Gyul Hap {room_code}] Reivindicação inválida (não é lista de 3 índices): {claimed_cards_indices}")
        except Exception as e:
             logger.error(f"[Jogo Final - Gyul Hap {room_code}] Erro ao validar Hap: {e}")

        if is_valid_hap:
            logger.info(f"[Jogo Final - Gyul Hap {room_code}] Jogador {sid} reivindicou um Hap válido.")
            sub_game_state["scores"][sid] = sub_game_state["scores"].get(sid, 0) + 1
            # TODO: Remove cards, add new ones, update board state.
            
            # Check win condition (e.g., first to X points)
            # Simplified: Assume first to 1 point wins
            winner = sid
            sub_game_state["winner"] = winner
            logger.info(f"[Jogo Final - Gyul Hap {room_code}] Fim do sub-jogo. Vencedor: {sid}")
            emit("update_sub_game_state", sub_game_state, to=room_code)
            end_sub_game(socketio, room_code, winner)
        else:
            logger.info(f"[Jogo Final - Gyul Hap {room_code}] Jogador {sid} reivindicou um Hap inválido.")
            # TODO: Penalty? Deduct point?
            emit("gyulhap_invalid", {"sid": sid}, to=room_code) # Notify player their claim was invalid
            # emit("update_sub_game_state", sub_game_state, to=room_code) # Maybe update scores if penalty

# --- Helper Functions (No auth changes needed) ---

def flip_back_cards(socketio, room_code, idx1, idx2):
    socketio.sleep(1.5) # Wait 1.5 seconds before flipping back
    if room_code not in game_states_final: return
    state = game_states_final.get(room_code)
    if not state or state["game_over"]: return
    sub_game_state = state.get("current_sub_game_state")
    # Check if the game is still Caca Imagem and not over
    if not sub_game_state or sub_game_state["type"] != "caca_imagem" or sub_game_state.get("winner") is not None:
        return
        
    # Check bounds and if cards are still revealed (might have been matched by opponent quickly?)
    grid_len = len(sub_game_state.get("grid", []))
    if not (0 <= idx1 < grid_len and 0 <= idx2 < grid_len): return
        
    # Only flip back if they are currently revealed AND they are NOT a matched pair
    # (This check might be redundant if game logic prevents flipping matched pairs back)
    if sub_game_state["revealed"][idx1] and sub_game_state["revealed"][idx2]:
         card1 = sub_game_state["grid"][idx1]
         card2 = sub_game_state["grid"][idx2]
         if card1 != card2:
             sub_game_state["revealed"][idx1] = False
             sub_game_state["revealed"][idx2] = False
             logger.info(f"[Jogo Final - Caca Imagem {room_code}] Virando cartas {idx1} e {idx2} de volta.")
             emit("update_sub_game_state", sub_game_state, to=room_code)
         # else: # It's a pair, should already be handled by match logic
         #    pass 

def start_next_sub_game(socketio, room_code):
    if room_code not in game_states_final or game_states_final[room_code]["game_over"]:
        return

    state = game_states_final[room_code]
    sub_game_idx = state["current_sub_game_index"]

    if sub_game_idx >= len(state["sub_game_order"]):
        # All sub-games finished, determine overall winner based on scores
        score1 = state["scores"].get(state["players"][0], 0)
        score2 = state["scores"].get(state["players"][1], 0)
        overall_winner = None
        if score1 > score2:
            overall_winner = state["players"][0]
        elif score2 > score1:
            overall_winner = state["players"][1]
        else:
            overall_winner = "tie" # Or handle tie differently?
            
        state["game_over"] = True
        state["overall_winner"] = overall_winner
        logger.info(f"[Jogo Final {room_code}] Fim de todos os sub-jogos. Vencedor Geral: {overall_winner} (Scores: {state['scores']})")
        
        # Award final prize
        if overall_winner != "tie" and overall_winner in state["player_user_ids"]:
            winner_user_id = state["player_user_ids"][overall_winner]
            winner_user = User.query.get(winner_user_id)
            if winner_user:
                 # TODO: Define final prize (e.g., 3 tokens, 20 grenades?)
                 final_tokens = 3
                 final_grenades = 20
                 winner_user.tokens_of_life = (winner_user.tokens_of_life or 0) + final_tokens
                 winner_user.grenades = (winner_user.grenades or 0) + final_grenades
                 db.session.commit()
                 logger.info(f"[Jogo Final {room_code}] Vencedor {winner_user.username} (User ID: {winner_user_id}) recompensado com {final_tokens} tokens e {final_grenades} granadas.")
            else:
                 logger.error(f"[Jogo Final {room_code}] Vencedor User ID {winner_user_id} não encontrado no DB para recompensa final.")
                 
        emit("game_over", {"overall_winner": overall_winner, "final_scores": state["scores"], "final_state": get_public_final_state(room_code)}, to=room_code)
        # Clean up game state?
        # socketio.start_background_task(lambda: game_states_final.pop(room_code, None), 10)
        return

    sub_game_type = state["sub_game_order"][sub_game_idx]
    players = state["players"] # List of SIDs
    logger.info(f"[Jogo Final {room_code}] Iniciando Sub-Jogo {sub_game_idx + 1}: {sub_game_type}")

    sub_game_state = None
    if sub_game_type == "poker_indiano":
        sub_game_state = initialize_poker_indiano(players)
    elif sub_game_type == "caca_imagem":
        sub_game_state = initialize_caca_imagem(players)
    elif sub_game_type == "gyul_hap":
        sub_game_state = initialize_gyul_hap(players)
    
    if sub_game_state is None:
        logger.error(f"[Jogo Final {room_code}] Falha ao inicializar sub-jogo: {sub_game_type}")
        # Handle error - skip game? End final?
        # For now, just log and attempt to proceed (might break)
        state["current_sub_game_index"] += 1
        start_next_sub_game(socketio, room_code)
        return
        
    state["current_sub_game_state"] = sub_game_state
    # TODO: Apply advantages for this sub-game

    emit("sub_game_start", {"index": sub_game_idx, "type": sub_game_type, "state": state["current_sub_game_state"]}, to=room_code)
    emit("update_game_state", get_public_final_state(room_code), to=room_code)

def end_sub_game(socketio, room_code, winner_sid):
    # winner_sid can be a SID or "tie"
    if room_code not in game_states_final or game_states_final[room_code]["game_over"]:
        return

    state = game_states_final[room_code]
    sub_game_idx = state["current_sub_game_index"]
    sub_game_type = state["sub_game_order"][sub_game_idx]
    logger.info(f"[Jogo Final {room_code}] Fim do Sub-Jogo {sub_game_idx + 1}: {sub_game_type}. Vencedor: {winner_sid}")

    if winner_sid != "tie" and winner_sid in state["players"]:
        state["scores"][winner_sid] = state["scores"].get(winner_sid, 0) + 1

    emit("sub_game_end", {"index": sub_game_idx, "type": sub_game_type, "winner": winner_sid, "scores": state["scores"]}, to=room_code)

    # Check for overall winner (first to 2 wins)
    overall_winner = None
    for sid, score in state["scores"].items():
        if score >= 2:
            overall_winner = sid
            break
            
    if overall_winner:
        state["game_over"] = True
        state["overall_winner"] = overall_winner
        logger.info(f"[Jogo Final {room_code}] Vencedor Geral alcançado: {overall_winner} (Scores: {state['scores']})")
        
        # Award final prize
        if overall_winner in state["player_user_ids"]:
            winner_user_id = state["player_user_ids"][overall_winner]
            winner_user = User.query.get(winner_user_id)
            if winner_user:
                 final_tokens = 3
                 final_grenades = 20
                 winner_user.tokens_of_life = (winner_user.tokens_of_life or 0) + final_tokens
                 winner_user.grenades = (winner_user.grenades or 0) + final_grenades
                 db.session.commit()
                 logger.info(f"[Jogo Final {room_code}] Vencedor {winner_user.username} (User ID: {winner_user_id}) recompensado com {final_tokens} tokens e {final_grenades} granadas.")
            else:
                 logger.error(f"[Jogo Final {room_code}] Vencedor User ID {winner_user_id} não encontrado no DB para recompensa final.")
                 
        emit("game_over", {"overall_winner": overall_winner, "final_scores": state["scores"], "final_state": get_public_final_state(room_code)}, to=room_code)
        # Clean up game state?
        # socketio.start_background_task(lambda: game_states_final.pop(room_code, None), 10)
    else:
        # Proceed to the next sub-game
        state["current_sub_game_index"] += 1
        # Add a small delay before starting the next game
        socketio.start_background_task(lambda: start_next_sub_game(socketio, room_code), 3) 

def get_public_final_state(room_code):
    """Returns a version of the final game state safe to send to clients."""
    if room_code not in game_states_final:
        return None

    state = game_states_final[room_code]
    public_state = {
        "players": state["players"], # List of SIDs
        "scores": state["scores"], # Dict {sid: score}
        "current_sub_game_index": state["current_sub_game_index"],
        "sub_game_order": state["sub_game_order"],
        "current_sub_game_state": state["current_sub_game_state"], # Sub-game state is assumed public
        "advantages": state["advantages"], # Dict {sid: [adv]}
        "game_over": state["game_over"],
        "overall_winner": state["overall_winner"] # SID or "tie"
    }
    return public_state

