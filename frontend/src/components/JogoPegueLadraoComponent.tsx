import React, { useState, useEffect, useContext } from 'react';
import { SocketContext } from '../context/SocketContext';
// import { AuthContext } from '../context/AuthContext';

interface PlayerGold {
    [sid: string]: number;
}

interface LadraoGameState {
    players: string[];
    village1: string[];
    village2: string[];
    player_gold: PlayerGold;
    round: number;
    max_rounds: number;
    exiled_this_round: { [village: number]: string | null };
    game_over: boolean;
    winner_village: number | null;
    winner_player: string | null;
    loser_player: string | null;
    thief?: string; // Revealed at game over
    my_role?: 'thief' | 'villager' | 'unknown';
    my_village_votes?: { [voter_sid: string]: string };
}

interface JogoPegueLadraoProps {
    roomCode: string;
    initialState: LadraoGameState;
}

const JogoPegueLadraoComponent: React.FC<JogoPegueLadraoProps> = ({ roomCode, initialState }) => {
    const { socket } = useContext(SocketContext);
    // const { user } = useContext(AuthContext);
    const [gameState, setGameState] = useState<LadraoGameState>(initialState);
    const [selectedVoteSid, setSelectedVoteSid] = useState<string>('');
    const [hasVoted, setHasVoted] = useState<boolean>(false);
    const [playerUsernames, setPlayerUsernames] = useState<{ [sid: string]: string }>({}); // Map SID to username

    const currentUserSid = socket?.id;
    const myVillage = currentUserSid ? (gameState.village1.includes(currentUserSid) ? 1 : (gameState.village2.includes(currentUserSid) ? 2 : 0)) : 0;
    const myVillageSids = myVillage === 1 ? gameState.village1 : (myVillage === 2 ? gameState.village2 : []);

    // Placeholder: Need a reliable way to get usernames
    const getUsername = (sid: string): string => playerUsernames[sid] || sid.substring(0, 6);

    useEffect(() => {
        // Fetch usernames based on initial SIDs
        // This should ideally come from a shared context or initial room data
        const initialUsernames: { [sid: string]: string } = {};
        initialState.players.forEach(sid => {
            // Replace with actual username fetching logic
            initialUsernames[sid] = `User_${sid.substring(0, 4)}`; 
        });
        setPlayerUsernames(initialUsernames);
        setGameState(initialState); // Ensure initial state is set
    }, [initialState]);

    useEffect(() => {
        if (!socket) return;

        const handleUpdateState = (newState: LadraoGameState) => {
            console.log("Pegue o Ladrão state update:", newState);
            setGameState(newState);
            setHasVoted(false); // Reset vote status on new round/state update
            setSelectedVoteSid('');
            // Update usernames if new players joined (though unlikely mid-game)
            setPlayerUsernames(prev => {
                const updated = { ...prev };
                newState.players.forEach(sid => {
                    if (!updated[sid]) {
                        updated[sid] = `User_${sid.substring(0, 4)}`; // Fetch real username
                    }
                });
                return updated;
            });
        };

        const handleRoundStart = (data: { round: number }) => {
            console.log(`Pegue o Ladrão Round ${data.round} started.`);
            setGameState(prev => ({ ...prev, round: data.round, exiled_this_round: { 1: null, 2: null } }));
            setHasVoted(false);
            setSelectedVoteSid('');
        };

        const handlePlayerVoted = (data: { voter_sid: string; village: number }) => {
            console.log(`Player ${getUsername(data.voter_sid)} from Village ${data.village} has voted.`);
            if (data.voter_sid === currentUserSid) {
                setHasVoted(true);
            }
            // Update UI to show who has voted, maybe?
        };

        const handleVillageExiled = (data: { village: number; exiled_sid: string | null; votes: { [voted_sid: string]: number } }) => {
            console.log(`Village ${data.village} exiled: ${data.exiled_sid ? getUsername(data.exiled_sid) : 'Nobody'}`);
            // Update state based on this or wait for full update_game_state?
            setGameState(prev => ({
                ...prev,
                exiled_this_round: { ...prev.exiled_this_round, [data.village]: data.exiled_sid }
            }));
        };
        
        const handleThiefStole = (data: { thief_sid: string; new_gold: number }) => {
             console.log(`Thief ${getUsername(data.thief_sid)} stole gold! New total: ${data.new_gold}`);
             setGameState(prev => ({
                ...prev,
                player_gold: { ...prev.player_gold, [data.thief_sid]: data.new_gold }
            }));
        };
        
        const handleThiefCaught = (data: { thief_sid: string; village: number }) => {
             console.log(`Thief ${getUsername(data.thief_sid)} was caught by Village ${data.village}! No gold stolen.`);
        };

        const handleGameOver = (data: LadraoGameState) => { // Assuming game_over sends the final state
            console.log("Pegue o Ladrão Game Over!", data);
            setGameState(data);
        };

        socket.on('update_game_state', handleUpdateState);
        socket.on('round_start', handleRoundStart);
        socket.on('player_voted', handlePlayerVoted);
        socket.on('village_exiled', handleVillageExiled);
        socket.on('thief_stole', handleThiefStole);
        socket.on('thief_caught', handleThiefCaught);
        socket.on('game_over', handleGameOver);

        return () => {
            socket.off('update_game_state', handleUpdateState);
            socket.off('round_start', handleRoundStart);
            socket.off('player_voted', handlePlayerVoted);
            socket.off('village_exiled', handleVillageExiled);
            socket.off('thief_stole', handleThiefStole);
            socket.off('thief_caught', handleThiefCaught);
            socket.off('game_over', handleGameOver);
        };
    }, [socket, roomCode, currentUserSid]);

    const handleVote = () => {
        if (!socket || !selectedVoteSid || hasVoted || gameState.game_over || myVillage === 0) return;
        console.log(`Voting to exile ${selectedVoteSid}`);
        socket.emit('ladrao_vote_exile', { room_code: roomCode, voted_sid: selectedVoteSid });
    };

    return (
        <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '15px' }}>Pegue o Ladrão</h3>

            {gameState.game_over ? (
                <div style={{ textAlign: 'center', color: 'red', fontWeight: 'bold' }}>
                    <p>FIM DE JOGO!</p>
                    <p>Ladrão: {gameState.thief ? getUsername(gameState.thief) : 'N/A'}</p>
                    <p>Vila Vencedora: {gameState.winner_village ?? 'N/A'}</p>
                    <p>Vencedor (Mais Ouro): {gameState.winner_player ? getUsername(gameState.winner_player) : 'N/A'}</p>
                    <p>Perdedor (Menos Ouro na Vila Perdedora): {gameState.loser_player ? getUsername(gameState.loser_player) : 'N/A'}</p>
                </div>
            ) : (
                <div style={{ textAlign: 'center', marginBottom: '10px' }}>
                    Rodada: {gameState.round} / {gameState.max_rounds}
                </div>
            )}

            <div style={{ marginBottom: '15px' }}>
                <h4>Seu Status:</h4>
                <p>
                    Vila: {myVillage || 'N/A'} | Ouro: {gameState.player_gold[currentUserSid!] || 0}
                    {gameState.my_role && ` | Papel: ${gameState.my_role === 'thief' ? 'Ladrão' : 'Morador'}`}
                </p>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-around', marginBottom: '20px' }}>
                {[1, 2].map(villageNum => (
                    <div key={villageNum} style={{ border: '1px solid #eee', padding: '10px', width: '45%' }}>
                        <h4>Vila {villageNum} ({villageNum === 1 ? gameState.village1.length : gameState.village2.length} jogadores)</h4>
                        <ul style={{ listStyle: 'none', padding: 0 }}>
                            {(villageNum === 1 ? gameState.village1 : gameState.village2).map(sid => (
                                <li key={sid} style={{ marginBottom: '5px', backgroundColor: gameState.exiled_this_round[villageNum] === sid ? '#ffcccc' : 'transparent' }}>
                                    <span>{getUsername(sid)} - Ouro: {gameState.player_gold[sid] || 0}</span>
                                    {myVillage === villageNum && !gameState.game_over && !hasVoted && (
                                        <input
                                            type="radio"
                                            name="voteExile"
                                            value={sid}
                                            checked={selectedVoteSid === sid}
                                            onChange={(e) => setSelectedVoteSid(e.target.value)}
                                            style={{ marginLeft: '10px' }}
                                            disabled={hasVoted}
                                        />
                                    )}
                                    {gameState.exiled_this_round[villageNum] === sid && <span style={{ color: 'red', marginLeft: '5px' }}>(Exilado nesta rodada)</span>}
                                </li>
                            ))}
                        </ul>
                        {myVillage === villageNum && !gameState.game_over && (
                            <button onClick={handleVote} disabled={!selectedVoteSid || hasVoted} style={{ marginTop: '10px' }}>
                                {hasVoted ? 'Voto Enviado' : 'Votar para Exilar'}
                            </button>
                        )}
                    </div>
                ))}
            </div>

            {/* Display vote status or results? */}
            {/* Maybe show who in your village has voted */} 
            {myVillage > 0 && !gameState.game_over && (
                 <div>
                    <h5>Status Votação (Vila {myVillage}):</h5>
                    {myVillageSids.map(sid => (
                        <span key={sid} style={{ marginRight: '10px', color: gameState.my_village_votes && gameState.my_village_votes[sid] ? 'green' : 'gray' }}>
                            {getUsername(sid)}
                        </span>
                    ))}
                 </div>
            )}

        </div>
    );
};

export default JogoPegueLadraoComponent;

