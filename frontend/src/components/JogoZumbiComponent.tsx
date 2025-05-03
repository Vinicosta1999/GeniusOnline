import React, { useState, useEffect, useContext } from 'react';
import { SocketContext } from '../context/SocketContext';
// import { AuthContext } from '../context/AuthContext'; // Assuming AuthContext provides user info

interface PlayerStatus {
    sid: string;
    username: string;
    is_zombie: boolean;
    points?: number; // Only for humans
    antidotes?: number; // Only visible to self?
    grenades?: number; // Only visible to self?
}

interface JogoZumbiState {
    players: string[];
    zombies: string[];
    humans: string[];
    human_points: { [sid: string]: number };
    antidotes: { [sid: string]: number };
    grenades: { [sid: string]: number };
    round: number;
    round_end_time: number | null;
    game_over: boolean;
    winner: string | null; // 'zombies' or winner_sid
    max_rounds: number;
}

interface JogoZumbiProps {
    roomCode: string;
    initialState: JogoZumbiState;
}

const JogoZumbiComponent: React.FC<JogoZumbiProps> = ({ roomCode, initialState }) => {
    const { socket } = useContext(SocketContext);
    // const { user } = useContext(AuthContext); // Get current user info
    const [gameState, setGameState] = useState<JogoZumbiState>(initialState);
    const [playerDetails, setPlayerDetails] = useState<PlayerStatus[]>([]);
    const [timeLeft, setTimeLeft] = useState<number | null>(null);
    const [selectedPlayerSid, setSelectedPlayerSid] = useState<string>('');
    const [canTouch, setCanTouch] = useState<boolean>(true); // Track if player can touch this round

    const currentUserSid = socket?.id;
    const isCurrentUserZombie = currentUserSid ? gameState.zombies.includes(currentUserSid) : false;

    // Function to get player username from SID (requires mapping or context)
    // This is a placeholder - you need a way to map SIDs to usernames reliably
    const getUsernameBySid = (sid: string): string => {
        // Find in playerDetails or fetch from a user context/map
        const player = playerDetails.find(p => p.sid === sid);
        return player ? player.username : sid.substring(0, 6); // Fallback to short SID
    };

    useEffect(() => {
        // Need to fetch initial player details (usernames) based on SIDs
        // This might come from a broader room context or another event
        const initialDetails: PlayerStatus[] = gameState.players.map(sid => ({
            sid: sid,
            username: getUsernameBySid(sid), // Placeholder
            is_zombie: gameState.zombies.includes(sid),
            points: gameState.human_points[sid],
            antidotes: gameState.antidotes[sid], // Show own stats
            grenades: gameState.grenades[sid] // Show own stats
        }));
        setPlayerDetails(initialDetails);

    }, [initialState]); // Only on initial load

    useEffect(() => {
        if (!socket) return;

        const handleUpdateState = (newState: JogoZumbiState) => {
            console.log("JogoZumbi state update:", newState);
            setGameState(newState);
            // Update player details based on new state
            setPlayerDetails(prevDetails =>
                newState.players.map(sid => {
                    const existing = prevDetails.find(p => p.sid === sid);
                    return {
                        sid: sid,
                        username: existing ? existing.username : getUsernameBySid(sid), // Keep existing username
                        is_zombie: newState.zombies.includes(sid),
                        points: newState.human_points[sid],
                        antidotes: newState.antidotes[sid],
                        grenades: newState.grenades[sid]
                    };
                })
            );
            setCanTouch(true); // Reset touch ability at start of new state/round
        };

        const handleRoundStart = (data: { round: number; duration: number; end_timestamp: number }) => {
            console.log(`Round ${data.round} started.`);
            setGameState(prev => ({ ...prev, round: data.round, round_end_time: data.end_timestamp }));
            setCanTouch(true);
        };

        const handleRoundEnd = (data: { round: number; newly_infected: string[]; protected: string[] }) => {
            console.log(`Round ${data.round} ended. Infected: ${data.newly_infected.join(', ')}, Protected: ${data.protected.join(', ')}`);
            // State update will likely follow, or update based on this event?
            // Assuming separate 'update_game_state' handles the changes
            setCanTouch(false); // Cannot touch after round ends
        };

        const handlePlayerTouched = (data: { toucher_sid: string; touched_sid: string }) => {
            console.log(`Player ${getUsernameBySid(data.toucher_sid)} touched ${getUsernameBySid(data.touched_sid)}`);
            if (data.toucher_sid === currentUserSid) {
                setCanTouch(false); // Player used their touch for the round
            }
            // Maybe add visual feedback
        };
        
        const handleAntidoteUsed = (data: { sid: string; remaining: number }) => {
            console.log(`Player ${getUsernameBySid(data.sid)} used antidote. Remaining: ${data.remaining}`);
             setGameState(prev => ({
                ...prev,
                antidotes: { ...prev.antidotes, [data.sid]: data.remaining }
            }));
        };
        
        const handleAntidoteBought = (data: { sid: string; remaining_antidotes: number; remaining_grenades: number }) => {
            console.log(`Player ${getUsernameBySid(data.sid)} bought antidote.`);
             setGameState(prev => ({
                ...prev,
                antidotes: { ...prev.antidotes, [data.sid]: data.remaining_antidotes },
                grenades: { ...prev.grenades, [data.sid]: data.remaining_grenades }
            }));
        };

        const handleGameOver = (data: { winner: string | null; final_state: JogoZumbiState }) => {
            console.log("JogoZumbi Game Over! Winner:", data.winner);
            setGameState(data.final_state);
            setTimeLeft(null); // Stop timer
        };

        socket.on('update_game_state', handleUpdateState);
        socket.on('round_start', handleRoundStart);
        socket.on('round_end', handleRoundEnd);
        socket.on('player_touched', handlePlayerTouched);
        socket.on('antidote_used', handleAntidoteUsed);
        socket.on('antidote_bought', handleAntidoteBought);
        socket.on('game_over', handleGameOver);

        return () => {
            socket.off('update_game_state', handleUpdateState);
            socket.off('round_start', handleRoundStart);
            socket.off('round_end', handleRoundEnd);
            socket.off('player_touched', handlePlayerTouched);
            socket.off('antidote_used', handleAntidoteUsed);
            socket.off('antidote_bought', handleAntidoteBought);
            socket.off('game_over', handleGameOver);
        };
    }, [socket, roomCode, currentUserSid]);

    // Timer logic
    useEffect(() => {
        if (gameState.round_end_time && !gameState.game_over) {
            const updateTimer = () => {
                const now = Date.now() / 1000;
                const remaining = Math.max(0, gameState.round_end_time! - now);
                setTimeLeft(remaining);
                if (remaining === 0) {
                    // Timer ends, backend should handle round end
                }
            };

            updateTimer(); // Initial update
            const intervalId = setInterval(updateTimer, 1000);
            return () => clearInterval(intervalId);
        } else {
            setTimeLeft(null);
        }
    }, [gameState.round_end_time, gameState.game_over]);

    const handleTouchPlayer = () => {
        if (!socket || !selectedPlayerSid || !canTouch || gameState.game_over) return;
        if (selectedPlayerSid === currentUserSid) {
            alert("Você não pode tocar a si mesmo.");
            return;
        }
        console.log(`Attempting to touch ${selectedPlayerSid}`);
        socket.emit('zumbi_touch', { room_code: roomCode, target_sid: selectedPlayerSid });
    };

    const handleUseAntidote = () => {
        if (!socket || gameState.game_over) return;
        if (gameState.antidotes[currentUserSid!] <= 0) {
             alert("Você não tem antídotos.");
             return;
        }
        socket.emit('use_antidote', { room_code: roomCode });
    };

    const handleBuyAntidote = () => {
        if (!socket || gameState.game_over) return;
        const cost = 5;
         if (gameState.grenades[currentUserSid!] < cost) {
             alert(`Você não tem granadas suficientes (custo: ${cost}).`);
             return;
        }
        socket.emit('buy_antidote', { room_code: roomCode });
    };

    const formatTime = (seconds: number | null): string => {
        if (seconds === null) return '--:--';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '15px' }}>Jogo de Zumbi</h3>
            
            {gameState.game_over ? (
                <div style={{ textAlign: 'center', color: 'red', fontWeight: 'bold' }}>
                    FIM DE JOGO! Vencedor: {gameState.winner === 'zombies' ? 'Zumbis' : getUsernameBySid(gameState.winner!)}
                </div>
            ) : (
                <div style={{ textAlign: 'center', marginBottom: '10px' }}>
                    Rodada: {gameState.round} / {gameState.max_rounds} | Tempo Restante: {formatTime(timeLeft)}
                </div>
            )}

            <div style={{ marginBottom: '15px' }}>
                <h4>Seu Status:</h4>
                <p>
                    Você é: <strong style={{ color: isCurrentUserZombie ? 'red' : 'green' }}>{isCurrentUserZombie ? 'Zumbi' : 'Humano'}</strong>
                    {!isCurrentUserZombie && ` | Pontos: ${gameState.human_points[currentUserSid!] || 0}`}
                    | Antídotos: {gameState.antidotes[currentUserSid!] || 0}
                    | Granadas: {gameState.grenades[currentUserSid!] || 0}
                </p>
                {!gameState.game_over && (
                    <div>
                        <button onClick={handleUseAntidote} disabled={gameState.antidotes[currentUserSid!] <= 0}>
                            Usar Antídoto
                        </button>
                        <button onClick={handleBuyAntidote} disabled={gameState.grenades[currentUserSid!] < 5} style={{ marginLeft: '10px' }}>
                            Comprar Antídoto (5 Granadas)
                        </button>
                    </div>
                )}
            </div>

            <h4>Jogadores:</h4>
            <ul style={{ listStyle: 'none', padding: 0 }}>
                {playerDetails.map(player => (
                    <li key={player.sid} style={{ marginBottom: '10px', padding: '8px', border: `1px solid ${player.sid === selectedPlayerSid ? '#007bff' : '#eee'}`, backgroundColor: player.is_zombie ? '#ffdddd' : '#ddffdd' }}>
                        <span>{player.username} ({player.is_zombie ? 'Zumbi' : 'Humano'})</span>
                        {!player.is_zombie && <span> - Pontos: {player.points || 0}</span>}
                        {!gameState.game_over && player.sid !== currentUserSid && (
                             <input 
                                type="radio" 
                                name="selectPlayer" 
                                value={player.sid} 
                                checked={selectedPlayerSid === player.sid}
                                onChange={(e) => setSelectedPlayerSid(e.target.value)}
                                style={{ marginLeft: '15px' }}
                             />
                        )}
                    </li>
                ))}
            </ul>

            {!gameState.game_over && (
                <div style={{ marginTop: '15px', textAlign: 'center' }}>
                    <button 
                        onClick={handleTouchPlayer} 
                        disabled={!selectedPlayerSid || !canTouch || selectedPlayerSid === currentUserSid}
                    >
                        Tocar Jogador Selecionado
                    </button>
                    {!canTouch && <span style={{ marginLeft: '10px', color: 'gray' }}>(Você já tocou alguém nesta rodada)</span>}
                </div>
            )}
        </div>
    );
};

export default JogoZumbiComponent;

