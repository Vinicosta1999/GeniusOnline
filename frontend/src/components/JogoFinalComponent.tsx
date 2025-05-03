import React, { useState, useEffect, useContext } from 'react';
import { SocketContext } from '../context/SocketContext';
// import { AuthContext } from '../context/AuthContext';

// --- Interfaces for Sub-Game States (Simplified) ---
interface PokerIndianoState {
    type: "poker_indiano";
    player_cards_visible?: { [sid: string]: number }; // Card visible to opponent
    player_cards?: { [sid: string]: number }; // Actual cards (only at reveal)
    bets: { [sid: string]: number };
    pot: number;
    current_player: string;
    round_state: "betting" | "reveal";
    winner: string | null | "tie";
}

interface CacaImagemState {
    type: "caca_imagem";
    grid: string[];
    revealed: boolean[];
    matched_pairs: { [sid: string]: string[] };
    current_player: string;
    turn_selection: number[];
    winner: string | null | "tie";
}

interface GyulHapState {
    type: "gyul_hap";
    board: string[]; // Simplified board
    scores: { [sid: string]: number };
    winner: string | null;
}

type SubGameState = PokerIndianoState | CacaImagemState | GyulHapState | null;

// --- Interface for Overall Final Game State ---
interface JogoFinalState {
    players: string[];
    scores: { [sid: string]: number }; // Overall score (sub-game wins)
    current_sub_game_index: number;
    sub_game_order: string[];
    advantages: { [sid: string]: any[] }; // Placeholder for advantages
    game_over: boolean;
    overall_winner: string | null | "tie";
    current_sub_game_state_public?: SubGameState; // Public state of the current sub-game
}

interface JogoFinalProps {
    roomCode: string;
    initialState: JogoFinalState;
}

// --- Sub-Game Components (Placeholders/Simplified) ---

const PokerIndianoUI: React.FC<{ state: PokerIndianoState; roomCode: string; socket: any; currentUserSid: string | undefined }> = 
    ({ state, roomCode, socket, currentUserSid }) => {
    const [betAmount, setBetAmount] = useState<number>(1);
    const opponentSid = state.player_cards_visible ? Object.keys(state.player_cards_visible).find(sid => sid !== currentUserSid) : null;
    const myVisibleCard = opponentSid ? state.player_cards_visible?.[opponentSid] : null; // The card on my forehead
    const myActualCard = state.player_cards?.[currentUserSid!]; // My card value (only at reveal)
    const opponentActualCard = opponentSid ? state.player_cards?.[opponentSid] : null; // Opponent card value (only at reveal)
    const isMyTurn = state.current_player === currentUserSid;

    const handleAction = (action: string) => {
        if (!socket || !isMyTurn || state.winner) return;
        socket.emit('final_poker_action', { room_code: roomCode, action: action, amount: betAmount });
    };

    return (
        <div>
            <h4>Pôquer Indiano</h4>
            {state.round_state === 'reveal' ? (
                <p>Revelação: Você ({myActualCard}) vs {opponentSid?.substring(0,6)} ({opponentActualCard})</p>
            ) : (
                <p>Sua carta (visível para o oponente): {myVisibleCard ?? '?'}</p>
            )}
            <p>Oponente: {opponentSid?.substring(0,6)}</p>
            <p>Pot: {state.pot} | Sua Aposta: {state.bets[currentUserSid!] || 0} | Aposta Oponente: {state.bets[opponentSid!] || 0}</p>
            
            {state.round_state === 'betting' && isMyTurn && (
                <div>
                    <input 
                        type="number" 
                        value={betAmount} 
                        onChange={(e) => setBetAmount(parseInt(e.target.value) || 1)} 
                        min="1" 
                        style={{ marginRight: '5px' }} 
                    />
                    <button onClick={() => handleAction('bet')} style={{ marginRight: '5px' }}>Apostar</button>
                    <button onClick={() => handleAction('call')} style={{ marginRight: '5px' }}>Pagar</button>
                    <button onClick={() => handleAction('fold')}>Desistir</button>
                </div>
            )}
            {!isMyTurn && state.round_state === 'betting' && <p><i>Aguardando oponente...</i></p>}
            {state.winner && <p style={{ color: 'green', fontWeight: 'bold' }}>Vencedor: {state.winner === 'tie' ? 'Empate' : (state.winner === currentUserSid ? 'Você' : 'Oponente')}</p>}
        </div>
    );
};

const CacaImagemUI: React.FC<{ state: CacaImagemState; roomCode: string; socket: any; currentUserSid: string | undefined }> = 
    ({ state, roomCode, socket, currentUserSid }) => {
    const isMyTurn = state.current_player === currentUserSid;

    const handleFlip = (index: number) => {
        if (!socket || !isMyTurn || state.winner || state.revealed[index] || state.turn_selection.length >= 2) return;
        socket.emit('final_caca_flip', { room_code: roomCode, index: index });
    };

    return (
        <div>
            <h4>Caça à Mesma Imagem</h4>
            <p>Turno: {isMyTurn ? 'Seu Turno' : `Turno de ${state.current_player.substring(0,6)}`}</p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 50px)', gap: '5px', marginBottom: '10px' }}>
                {state.grid.map((symbol, index) => (
                    <button 
                        key={index} 
                        onClick={() => handleFlip(index)} 
                        disabled={!isMyTurn || state.revealed[index] || state.turn_selection.length >= 2 || !!state.winner}
                        style={{ height: '50px', fontSize: '1.2em', backgroundColor: state.revealed[index] ? '#eee' : '#ccc' }}
                    >
                        {state.revealed[index] ? symbol : '?'}
                    </button>
                ))}
            </div>
            <div>
                Pares Encontrados:
                {Object.entries(state.matched_pairs).map(([sid, pairs]) => (
                    <p key={sid}>{sid === currentUserSid ? 'Você' : sid.substring(0,6)}: {pairs.join(', ')} ({pairs.length})</p>
                ))}
            </div>
            {state.winner && <p style={{ color: 'green', fontWeight: 'bold' }}>Vencedor: {state.winner === 'tie' ? 'Empate' : (state.winner === currentUserSid ? 'Você' : 'Oponente')}</p>}
        </div>
    );
};

const GyulHapUI: React.FC<{ state: GyulHapState; roomCode: string; socket: any; currentUserSid: string | undefined }> = 
    ({ state, roomCode, socket, currentUserSid }) => {
    const [selectedIndices, setSelectedIndices] = useState<number[]>([]);

    const handleSelectCard = (index: number) => {
        setSelectedIndices(prev => {
            if (prev.includes(index)) {
                return prev.filter(i => i !== index);
            }
            if (prev.length < 3) {
                return [...prev, index];
            }
            return prev; // Max 3 selected
        });
    };

    const handleClaimHap = () => {
        if (!socket || selectedIndices.length !== 3 || state.winner) return;
        socket.emit('final_gyulhap_claim', { room_code: roomCode, indices: selectedIndices });
        setSelectedIndices([]); // Reset selection after claim
    };

    return (
        <div>
            <h4>Gyul! Hap! (Simplificado)</h4>
            <p><i>Selecione 3 cartas que formam um "Hap"!</i></p>
            <div style={{ display: 'flex', gap: '10px', marginBottom: '10px', flexWrap: 'wrap' }}>
                {state.board.map((card, index) => (
                    <button 
                        key={index} 
                        onClick={() => handleSelectCard(index)}
                        style={{ 
                            padding: '10px', 
                            border: selectedIndices.includes(index) ? '2px solid blue' : '1px solid gray',
                            minWidth: '60px'
                        }}
                        disabled={!!state.winner}
                    >
                        {card} 
                    </button>
                ))}
            </div>
            <button onClick={handleClaimHap} disabled={selectedIndices.length !== 3 || !!state.winner}>
                Reivindicar HAP!
            </button>
             <div>
                Pontuações:
                {Object.entries(state.scores).map(([sid, score]) => (
                    <p key={sid}>{sid === currentUserSid ? 'Você' : sid.substring(0,6)}: {score}</p>
                ))}
            </div>
            {state.winner && <p style={{ color: 'green', fontWeight: 'bold' }}>Vencedor: {state.winner === currentUserSid ? 'Você' : 'Oponente'}</p>}
        </div>
    );
};

// --- Main Jogo Final Component ---
const JogoFinalComponent: React.FC<JogoFinalProps> = ({ roomCode, initialState }) => {
    const { socket } = useContext(SocketContext);
    // const { user } = useContext(AuthContext);
    const [gameState, setGameState] = useState<JogoFinalState>(initialState);
    const [playerUsernames, setPlayerUsernames] = useState<{ [sid: string]: string }>({});

    const currentUserSid = socket?.id;
    const currentSubGame = gameState.current_sub_game_state_public;
    const currentSubGameType = gameState.sub_game_order[gameState.current_sub_game_index];

    // Placeholder: Need a reliable way to get usernames
    const getUsername = (sid: string): string => playerUsernames[sid] || sid.substring(0, 6);

    useEffect(() => {
        // Fetch usernames based on initial SIDs
        const initialUsernames: { [sid: string]: string } = {};
        initialState.players.forEach(sid => {
            initialUsernames[sid] = `User_${sid.substring(0, 4)}`; // Replace with actual fetching
        });
        setPlayerUsernames(initialUsernames);
        setGameState(initialState);
    }, [initialState]);

    useEffect(() => {
        if (!socket) return;

        const handleUpdateState = (newState: JogoFinalState) => {
            console.log("Jogo Final state update:", newState);
            setGameState(newState);
            // Update usernames if needed
            setPlayerUsernames(prev => {
                const updated = { ...prev };
                newState.players.forEach(sid => {
                    if (!updated[sid]) {
                        updated[sid] = `User_${sid.substring(0, 4)}`;
                    }
                });
                return updated;
            });
        };
        
        const handleSubGameStart = (data: { index: number; type: string; state: SubGameState }) => {
            console.log(`Sub-game ${data.index + 1} (${data.type}) started.`);
            // The main state update likely includes this already, but good for logging
            // setGameState(prev => ({ ...prev, current_sub_game_index: data.index, current_sub_game_state_public: data.state }));
        };
        
        const handleUpdateSubGameState = (subGameState: SubGameState) => {
             console.log("Sub-game state update:", subGameState);
             setGameState(prev => ({ ...prev, current_sub_game_state_public: subGameState }));
        };
        
        const handleSubGameEnd = (data: { index: number; type: string; winner: string | null | "tie"; scores: { [sid: string]: number } }) => {
             console.log(`Sub-game ${data.index + 1} (${data.type}) ended. Winner: ${data.winner}`);
             // Main state update should reflect score changes
        };

        const handleGameOver = (data: { overall_winner: string | null | "tie"; final_scores: { [sid: string]: number } }) => {
            console.log("Jogo Final Game Over! Winner:", data.overall_winner);
            setGameState(prev => ({ ...prev, game_over: true, overall_winner: data.overall_winner, scores: data.final_scores }));
        };

        socket.on('update_game_state', handleUpdateState);
        socket.on('sub_game_start', handleSubGameStart);
        socket.on('update_sub_game_state', handleUpdateSubGameState);
        socket.on('sub_game_end', handleSubGameEnd);
        socket.on('game_over', handleGameOver);

        return () => {
            socket.off('update_game_state', handleUpdateState);
            socket.off('sub_game_start', handleSubGameStart);
            socket.off('update_sub_game_state', handleUpdateSubGameState);
            socket.off('sub_game_end', handleSubGameEnd);
            socket.off('game_over', handleGameOver);
        };
    }, [socket, roomCode]);

    const renderSubGame = () => {
        if (!currentSubGame || !socket || !currentUserSid) return <p>Aguardando início do sub-jogo...</p>;

        switch (currentSubGame.type) {
            case 'poker_indiano':
                return <PokerIndianoUI state={currentSubGame} roomCode={roomCode} socket={socket} currentUserSid={currentUserSid} />;
            case 'caca_imagem':
                return <CacaImagemUI state={currentSubGame} roomCode={roomCode} socket={socket} currentUserSid={currentUserSid} />;
            case 'gyul_hap':
                return <GyulHapUI state={currentSubGame} roomCode={roomCode} socket={socket} currentUserSid={currentUserSid} />;
            default:
                return <p>Tipo de sub-jogo desconhecido.</p>;
        }
    };

    return (
        <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '15px' }}>A Final</h3>

            {gameState.game_over ? (
                <div style={{ textAlign: 'center', color: 'red', fontWeight: 'bold' }}>
                    <p>FIM DE JOGO!</p>
                    <p>Vencedor Geral: {gameState.overall_winner === 'tie' ? 'Empate' : (gameState.overall_winner ? getUsername(gameState.overall_winner) : 'N/A')}</p>
                </div>
            ) : (
                <div style={{ textAlign: 'center', marginBottom: '10px' }}>                    Sub-Jogo Atual: {gameState.current_sub_game_index + 1} / {gameState.sub_game_order.length} ({currentSubGameType})
                </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-around', marginBottom: '15px', borderBottom: '1px solid #eee', paddingBottom: '10px' }}>
                {gameState.players.map(sid => (
                    <div key={sid} style={{ textAlign: 'center' }}>
                        <strong>{sid === currentUserSid ? 'Você' : getUsername(sid)}</strong>
                        <p>Vitórias: {gameState.scores[sid] || 0}</p>
                        {/* Display advantages? */}
                        {/* <p>Vantagens: {gameState.advantages[sid]?.join(', ') || 'Nenhuma'}</p> */}
                    </div>
                ))}
            </div>

            {!gameState.game_over && (
                <div style={{ border: '1px dashed #aaa', padding: '15px', marginTop: '15px' }}>
                    {renderSubGame()}
                </div>
            )}

        </div>
    );
};

export default JogoFinalComponent;

