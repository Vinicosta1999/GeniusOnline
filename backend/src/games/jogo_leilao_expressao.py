# -*- coding: utf-8 -*-
import random
import logging
from flask_socketio import emit
from flask import request
from asteval import Interpreter # Using asteval for safe evaluation
from src.models.user import db, User # Import User
from src.models.game import Player, GameRoom

logger = logging.getLogger(__name__)

# Game state storage
game_states_leilao = {}

# Define available pieces for auction (example)
AVAILABLE_PIECES = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', # Numbers
    '+', '-', '*', '/', # Operators
    '(', ')', # Parentheses
    '1', '2', '3', '4', '5', # More numbers to balance
    '+', '-', '*'
]

def register_leilao_expressao_events(socketio, get_authenticated_user_id):

    @socketio.on("start_leilao_expressao")
    def handle_start_leilao_expressao(data):
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
        
        # Minimum players? Let's assume at least 2
        if player_count < 2:
            emit("error", {"message": f"Jogadores insuficientes para iniciar o Leilão de Expressão (mínimo 2). Atuais: {player_count}"}, room=sid)
            return

        logger.info(f"Iniciando Leilão de Expressão na sala {room_code} pelo Host User ID: {user_id}")
        room.current_game_type = "leilao_expressao"
        db.session.commit()

        # Initialize game state using active players' SIDs
        player_sids = [p.sid for p in active_players]
        pieces_to_auction = random.sample(AVAILABLE_PIECES, len(AVAILABLE_PIECES)) # Shuffle pieces

        game_states_leilao[room_code] = {
            "players": player_sids, # List of active SIDs
            "player_pieces": {sid: [] for sid in player_sids},
            "player_cubes": {sid: list(range(1, 11)) for sid in player_sids}, # Cubes 1-10
            "pieces_to_auction": pieces_to_auction,
            "current_auction_piece": None,
            "current_bids": {}, # {sid: bid_cube_value}
            "auction_round": 0,
            "game_over": False,
            "winner": None, # SID of the winner
            "equation_history": {sid: [] for sid in player_sids}, # Track submitted equations
            "asteval": Interpreter() # Safe evaluator instance
        }

        emit("game_started", {"game_type": "leilao_expressao", "initial_state": get_public_leilao_state(room_code)}, to=room_code)
        start_leilao_auction_round(socketio, room_code)

    @socketio.on("leilao_place_bid")
    def handle_leilao_place_bid(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        bid_cube = data.get("bid_cube")

        if room_code not in game_states_leilao or game_states_leilao[room_code]["game_over"]:
            return

        state = game_states_leilao[room_code]

        # Check if player SID is active in this game instance
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo."}, room=sid)
            return
            
        if state["current_auction_piece"] is None:
            emit("error", {"message": "Nenhum leilão ativo no momento."}, room=sid)
            return

        if sid in state["current_bids"]:
            emit("error", {"message": "Você já fez um lance para esta peça."}, room=sid)
            return

        try:
            bid_value = int(bid_cube)
            if bid_value not in state["player_cubes"].get(sid, []):
                emit("error", {"message": f"Cubo de lance inválido ou já utilizado: {bid_value}"}, room=sid)
                return
        except (ValueError, TypeError):
            emit("error", {"message": "Valor do lance inválido."}, room=sid)
            return

        logger.info(f"[Leilão Expressão {room_code}] Jogador SID {sid} (User: {user_id}) lançou o cubo {bid_value} pela peça '{state['current_auction_piece']}'")
        state["current_bids"][sid] = bid_value
        emit("player_bid", {"bidder_sid": sid}, to=room_code) # Notify UI that player bid, not the value

        # Check if all active players have bid
        active_players_count = len(state["players"])
        if len(state["current_bids"]) == active_players_count:
            logger.info(f"[Leilão Expressão {room_code}] Todos os {active_players_count} jogadores ativos fizeram lances.")
            process_leilao_auction_result(socketio, room_code)

    @socketio.on("leilao_submit_equation")
    def handle_leilao_submit_equation(data):
        sid = request.sid
        user_id = get_authenticated_user_id(sid)
        if not user_id:
            return

        room_code = data.get("room_code")
        equation_str = data.get("equation")
        used_piece_indices = data.get("used_indices") # Indices of pieces used from player's hand

        if room_code not in game_states_leilao or game_states_leilao[room_code]["game_over"]:
            return

        state = game_states_leilao[room_code]
        # Check if player SID is active in this game instance
        if sid not in state["players"]:
            emit("error", {"message": "Você não está ativo neste jogo."}, room=sid)
            return
            
        if not equation_str or not isinstance(used_piece_indices, list):
            emit("error", {"message": "Dados da equação inválidos (equação ou índices ausentes/incorretos)."}, room=sid)
            return

        player_pieces = state["player_pieces"].get(sid, [])
        
        # Verify indices are valid and pieces match the equation string components
        try:
            # Ensure indices are within bounds
            if any(i < 0 or i >= len(player_pieces) for i in used_piece_indices):
                raise IndexError("Índice de peça fora dos limites.")
            # Ensure indices are unique
            if len(used_piece_indices) != len(set(used_piece_indices)):
                 emit("error", {"message": "Você não pode usar a mesma peça duas vezes na equação."}, room=sid)
                 return
                 
            used_pieces = [player_pieces[i] for i in used_piece_indices]
            # Basic check (as before, with warning)
            constructed_eq = "".join(used_pieces)
            if constructed_eq != equation_str.replace(" ", ""): 
                 logger.warning(f"[Leilão Expressão {room_code}] Discrepância (aviso): Equação '{equation_str}', Peças usadas: {used_pieces} (Índices: {used_piece_indices})")
                 pass
        except IndexError as e:
            emit("error", {"message": f"Índices de peças inválidos: {e}"}, room=sid)
            return
        except Exception as e: # Catch other potential errors during validation
             emit("error", {"message": f"Erro ao validar peças usadas: {e}"}, room=sid)
             return

        logger.info(f"[Leilão Expressão {room_code}] Jogador SID {sid} (User: {user_id}) submeteu a equação: {equation_str}")
        state["equation_history"][sid].append(equation_str)

        # Safely evaluate the equation using asteval
        aeval = state["asteval"]
        result = None
        error_msg = None
        try:
            aeval.symtable.clear() # Clear previous symbols
            result = aeval(equation_str)
            if aeval.error:
                error_msg = "; ".join([err.msg for err in aeval.error])
                logger.warning(f"[Leilão Expressão {room_code}] Erro de avaliação para '{equation_str}': {error_msg}")
                result = None 
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Leilão Expressão {room_code}] Exceção ao avaliar '{equation_str}': {e}")
            result = None

        # Check if result is numerically close to 10 (allow for float issues if division is used)
        is_winner = False
        if result is not None and isinstance(result, (int, float)):
            if abs(result - 10) < 1e-9: # Tolerance for floating point comparison
                is_winner = True

        if is_winner:
            logger.info(f"[Leilão Expressão {room_code}] Equação VÁLIDA! '{equation_str}' == {result}. Jogador {sid} (User: {user_id}) venceu!")
            state["game_over"] = True
            state["winner"] = sid
            
            # Award Tokens/Grenades using user_id
            winner_user = User.query.get(user_id)
            if winner_user:
                winner_user.tokens_of_life = (winner_user.tokens_of_life or 0) + 2
                winner_user.grenades = (winner_user.grenades or 0) + 10
                db.session.commit()
                logger.info(f"Jogador {winner_user.username} (User ID: {user_id}) recompensado.")
            else:
                 logger.error(f"[Leilão Expressão {room_code}] Vencedor User ID {user_id} não encontrado no DB para recompensa.")

            emit("equation_result", {"sid": sid, "equation": equation_str, "valid": True, "result": result}, to=room_code)
            emit("game_over", {"winner": sid, "winning_equation": equation_str, "final_state": get_public_leilao_state(room_code)}, to=room_code)
            # Clean up game state after a delay?
            # socketio.start_background_task(lambda: game_states_leilao.pop(room_code, None), 10)
        else:
            logger.info(f"[Leilão Expressão {room_code}] Equação INVÁLIDA ou resultado incorreto para '{equation_str}'. Resultado: {result}, Erro: {error_msg}")
            emit("equation_result", {"sid": sid, "equation": equation_str, "valid": False, "result": result, "error": error_msg}, to=room_code)
            # Remove used pieces from player's hand upon failed attempt?
            # Rules don't specify, let's assume they keep the pieces for now.

# --- Helper Functions (No auth changes needed here, logic is internal to game state) --- 

def start_leilao_auction_round(socketio, room_code):
    if room_code not in game_states_leilao or game_states_leilao[room_code]["game_over"]:
        return

    state = game_states_leilao[room_code]

    # Check if there are still active players
    if not state["players"]:
        logger.info(f"[Leilão Expressão {room_code}] Não há jogadores ativos. Encerrando jogo.")
        state["game_over"] = True
        emit("game_over", {"winner": None, "message": "Não há jogadores ativos.", "final_state": get_public_leilao_state(room_code)}, to=room_code)
        return
        
    if not state["pieces_to_auction"]:
        logger.info(f"[Leilão Expressão {room_code}] Todas as peças foram leiloadas. Nenhum vencedor.")
        state["game_over"] = True
        emit("game_over", {"winner": None, "message": "Nenhuma peça restante, ninguém formou a equação.", "final_state": get_public_leilao_state(room_code)}, to=room_code)
        return

    state["auction_round"] += 1
    state["current_auction_piece"] = state["pieces_to_auction"].pop(0)
    state["current_bids"] = {}

    logger.info(f"[Leilão Expressão {room_code}] Iniciando Leilão Rodada {state['auction_round']}. Peça: '{state['current_auction_piece']}'")
    emit("auction_start", {"round": state["auction_round"], "piece": state["current_auction_piece"]}, to=room_code)
    emit("update_game_state", get_public_leilao_state(room_code), to=room_code)

def process_leilao_auction_result(socketio, room_code):
    if room_code not in game_states_leilao or game_states_leilao[room_code]["game_over"]:
        return

    state = game_states_leilao[room_code]
    bids = state["current_bids"]
    piece = state["current_auction_piece"]
    active_players = state["players"] # SIDs of players still active

    # Filter bids to only include those from currently active players
    active_bids = {sid: bid for sid, bid in bids.items() if sid in active_players}

    if not active_bids:
        logger.warning(f"[Leilão Expressão {room_code}] Nenhum lance ativo recebido para a peça '{piece}'.")
        emit("auction_result", {"piece": piece, "winner_sid": None, "winning_bid": None, "bids": active_bids}, to=room_code)
        state["current_auction_piece"] = None
        start_leilao_auction_round(socketio, room_code) 
        return

    # Determine winner among active bidders
    max_bid = -1
    bid_counts = {}
    for sid, bid in active_bids.items():
        bid_counts[bid] = bid_counts.get(bid, 0) + 1
        if bid > max_bid:
            max_bid = bid
            
    unique_bids = {bid: sid for sid, bid in active_bids.items() if bid_counts[bid] == 1}
    highest_unique_bid = -1
    auction_winner_sid = None
    winning_bid_value = None
    
    if unique_bids:
        highest_unique_bid = max(unique_bids.keys())
        auction_winner_sid = unique_bids[highest_unique_bid]
        winning_bid_value = highest_unique_bid
        logger.info(f"[Leilão Expressão {room_code}] Lance único mais alto entre ativos: {highest_unique_bid} por {auction_winner_sid}.")
    else:
        highest_tied_bidders = [sid for sid, bid in active_bids.items() if bid == max_bid]
        if highest_tied_bidders:
            auction_winner_sid = random.choice(highest_tied_bidders)
            winning_bid_value = max_bid
            logger.info(f"[Leilão Expressão {room_code}] Empate no lance mais alto ({max_bid}) entre ativos. Vencedor aleatório: {auction_winner_sid}.")
        else:
             logger.error(f"[Leilão Expressão {room_code}] Erro ao determinar vencedor do leilão entre ativos.")

    # Update state for winner and bidders
    if auction_winner_sid:
        state["player_pieces"].setdefault(auction_winner_sid, []).append(piece)
        if winning_bid_value in state["player_cubes"].get(auction_winner_sid, []):
            state["player_cubes"][auction_winner_sid].remove(winning_bid_value)
        logger.info(f"[Leilão Expressão {room_code}] Jogador {auction_winner_sid} ganhou a peça '{piece}' com o lance {winning_bid_value}.")
    else:
        logger.info(f"[Leilão Expressão {room_code}] Peça '{piece}' não foi vendida (sem lances únicos ou válidos).")
        
    # Remove used cubes for all active bidders
    for sid, bid in active_bids.items():
        # Winner's cube already removed if they won
        if sid != auction_winner_sid:
            if bid in state["player_cubes"].get(sid, []):
                 state["player_cubes"][sid].remove(bid)

    emit("auction_result", {"piece": piece, "winner_sid": auction_winner_sid, "winning_bid": winning_bid_value, "bids": active_bids}, to=room_code)
    state["current_auction_piece"] = None
    state["current_bids"] = {}

    # Start next auction round
    start_leilao_auction_round(socketio, room_code)

def get_public_leilao_state(room_code):
    """Returns a version of the game state safe to send to clients."""
    if room_code not in game_states_leilao:
        return None

    state = game_states_leilao[room_code]
    # Current implementation sends full state (pieces/cubes of all players)
    # This seems acceptable for this game's rules based on description.
    public_state = {
        "players": state["players"], # List of active SIDs
        "player_pieces": state["player_pieces"], # Dict {sid: [pieces]}
        "player_cubes": state["player_cubes"], # Dict {sid: [cubes]}
        "pieces_remaining": len(state["pieces_to_auction"]),
        "current_auction_piece": state["current_auction_piece"],
        "auction_round": state["auction_round"],
        "game_over": state["game_over"],
        "winner": state["winner"], # SID of winner
        "equation_history": state["equation_history"] # Dict {sid: [equations]}
    }
    return public_state

