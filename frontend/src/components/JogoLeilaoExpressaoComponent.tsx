import React, { useState, useEffect, useContext } from 'react';
import { SocketContext } from '../context/SocketContext';
// import { AuthContext } from '../context/AuthContext';

interface LeilaoGameState {
    players: string[];
    player_pieces: { [sid: string]: string[] };
    player_cubes: { [sid: string]: number[] };
    pieces_remaining: number;
    current_auction_piece: string | null;
    auction_round: number;
    game_over: boolean;
    winner: string | null;
    equation_history: { [sid: string]: string[] };
}

interface JogoLeilaoExpressaoProps {
    roomCode: string;
    initialState: LeilaoGameState;
}

const JogoLeilaoExpressaoComponent: React.FC<JogoLeilaoExpressaoProps> = ({ roomCode, initialState }) => {
    const { socket } = useContext(SocketContext);
    // const { user } = useContext(AuthContext);
    const [gameState, setGameState] = useState<LeilaoGameState>(initialState);
    const [selectedCube, setSelectedCube] = useState<number | null>(null);
    const [hasBid, setHasBid] = useState<boolean>(false);
    const [equationInput, setEquationInput] = useState<string>("");
    const [selectedPieceIndices, setSelectedPieceIndices] = useState<number[]>([]);
    const [playerUsernames, setPlayerUsernames] = useState<{ [sid: string]: string }>({});
    const [lastAuctionResult, setLastAuctionResult] = useState<any>(null);
    const [lastEquationResult, setLastEquationResult] = useState<any>(null);

    const currentUserSid = socket?.id;
    const myCubes = currentUserSid ? gameState.player_cubes[currentUserSid] || [] : [];
    const myPieces = currentUserSid ? gameState.player_pieces[currentUserSid] || [] : [];

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

        const handleUpdateState = (newState: LeilaoGameState) => {
            console.log("Leilão Expressão state update:", newState);
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

        const handleAuctionStart = (data: { round: number; piece: string }) => {
            console.log(`Auction Round ${data.round} started. Piece: ${data.piece}`);
            setGameState(prev => ({ ...prev, auction_round: data.round, current_auction_piece: data.piece }));
            setHasBid(false);
            setSelectedCube(null);
            setLastAuctionResult(null); // Clear previous result
            setLastEquationResult(null);
        };

        const handlePlayerBid = (data: { bidder_sid: string }) => {
            console.log(`Player ${getUsername(data.bidder_sid)} has placed a bid.`);
            if (data.bidder_sid === currentUserSid) {
                setHasBid(true);
            }
            // Update UI to show who has bid?
        };

        const handleAuctionResult = (data: { piece: string; winner_sid: string | null; winning_bid: number | null; bids: { [sid: string]: number } }) => {
            console.log(`Auction for ${data.piece} ended. Winner: ${data.winner_sid ? getUsername(data.winner_sid) : 'None'}, Bid: ${data.winning_bid}`);
            setLastAuctionResult(data); // Store result for display
            // State update should follow to reflect piece/cube changes
        };
        
        const handleEquationResult = (data: { sid: string; equation: string; valid: boolean; result: number | null; error?: string }) => {
            console.log(`Equation submitted by ${getUsername(data.sid)}: ${data.equation}. Valid: ${data.valid}, Result: ${data.result}`);
            setLastEquationResult(data); // Store result for display
            if (data.sid === currentUserSid) {
                setEquationInput(""); // Clear input on result
                setSelectedPieceIndices([]);
            }
        };

        const handleGameOver = (data: { winner: string | null; winning_equation?: string; final_state: LeilaoGameState }) => {
            console.log("Leilão Expressão Game Over! Winner:", data.winner);
            setGameState(data.final_state);
        };

        socket.on('update_game_state', handleUpdateState);
        socket.on('auction_start', handleAuctionStart);
        socket.on('player_bid', handlePlayerBid);
        socket.on('auction_result', handleAuctionResult);
        socket.on('equation_result', handleEquationResult);
        socket.on('game_over', handleGameOver);

        return () => {
            socket.off('update_game_state', handleUpdateState);
            socket.off('auction_start', handleAuctionStart);
            socket.off('player_bid', handlePlayerBid);
            socket.off('auction_result', handleAuctionResult);
            socket.off('equation_result', handleEquationResult);
            socket.off('game_over', handleGameOver);
        };
    }, [socket, roomCode, currentUserSid]);

    const handlePlaceBid = () => {
        if (!socket || !selectedCube || hasBid || gameState.game_over || !gameState.current_auction_piece) return;
        console.log(`Placing bid with cube ${selectedCube}`);
        socket.emit('leilao_place_bid', { room_code: roomCode, bid_cube: selectedCube });
    };

    const handleTogglePieceSelection = (index: number) => {
        setSelectedPieceIndices(prev =>
            prev.includes(index)
                ? prev.filter(i => i !== index)
                : [...prev, index]
        );
    };
    
    const handleSubmitEquation = () => {
        if (!socket || !equationInput || selectedPieceIndices.length === 0 || gameState.game_over) return;
        // Basic validation: ensure selected indices are valid
        if (selectedPieceIndices.some(index => index < 0 || index >= myPieces.length)) {
            alert("Seleção de peças inválida.");
            return;
        }
        console.log(`Submitting equation: ${equationInput} using indices: ${selectedPieceIndices}`);
        socket.emit('leilao_submit_equation', { 
            room_code: roomCode, 
            equation: equationInput, 
            used_indices: selectedPieceIndices 
        });
    };

    return (
        <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px', backgroundColor: '#f9f9f9' }}>
            <h3 style={{ textAlign: 'center', marginBottom: '15px' }}>Leilão de Expressão</h3>

            {gameState.game_over ? (
                <div style={{ textAlign: 'center', color: 'red', fontWeight: 'bold' }}>
                    <p>FIM DE JOGO!</p>
                    <p>Vencedor: {gameState.winner ? getUsername(gameState.winner) : 'Ninguém'}</p>
                    {gameState.winner && <p>Equação Vencedora: {gameState.equation_history[gameState.winner]?.slice(-1)[0]}</p>}
                </div>
            ) : (
                <div style={{ textAlign: 'center', marginBottom: '10px' }}>
                    Leilão Rodada: {gameState.auction_round} | Peças Restantes: {gameState.pieces_remaining}
                </div>
            )}

            {/* Auction Section */}
            {!gameState.game_over && gameState.current_auction_piece && (
                <div style={{ border: '1px dashed blue', padding: '10px', marginBottom: '15px' }}>
                    <h4>Leilão Ativo</h4>
                    <p>Peça em leilão: <strong style={{ fontSize: '1.5em' }}>{gameState.current_auction_piece}</strong></p>
                    <p>Seus cubos disponíveis: {myCubes.sort((a, b) => a - b).join(', ')}</p>
                    <div>
                        <label>Selecione o cubo para o lance: </label>
                        <select 
                            value={selectedCube ?? ''} 
                            onChange={(e) => setSelectedCube(Number(e.target.value))} 
                            disabled={hasBid}
                        >
                            <option value="" disabled>--Selecione--</option>
                            {myCubes.map(cube => (
                                <option key={cube} value={cube}>{cube}</option>
                            ))}
                        </select>
                        <button onClick={handlePlaceBid} disabled={!selectedCube || hasBid} style={{ marginLeft: '10px' }}>
                            {hasBid ? 'Lance Enviado' : 'Dar Lance'}
                        </button>
                    </div>
                </div>
            )}
            
            {/* Last Auction Result */}
            {lastAuctionResult && (
                 <div style={{ border: '1px dashed gray', padding: '10px', marginBottom: '15px', backgroundColor: '#eee' }}>
                    <h4>Resultado Último Leilão (Peça: {lastAuctionResult.piece})</h4>
                    <p>Vencedor: {lastAuctionResult.winner_sid ? getUsername(lastAuctionResult.winner_sid) : 'Ninguém'}</p>
                    <p>Lance Vencedor: {lastAuctionResult.winning_bid ?? 'N/A'}</p>
                    {/* Optionally show all bids */} 
                    {/* <pre>{JSON.stringify(lastAuctionResult.bids, null, 2)}</pre> */}
                 </div>
            )}

            {/* Player Status Section */}
            <div style={{ marginBottom: '15px' }}>
                <h4>Seu Status:</h4>
                <p>Suas Peças: 
                    {myPieces.map((piece, index) => (
                        <span 
                            key={index} 
                            onClick={() => handleTogglePieceSelection(index)}
                            style={{
                                display: 'inline-block',
                                border: selectedPieceIndices.includes(index) ? '2px solid green' : '1px solid black',
                                padding: '2px 5px',
                                margin: '2px',
                                cursor: 'pointer',
                                backgroundColor: selectedPieceIndices.includes(index) ? '#ccffcc' : 'white'
                            }}
                        >
                            {piece}
                        </span>
                    ))}
                    {myPieces.length === 0 && <i>Nenhuma peça ainda</i>}
                </p>
                <p>Seus Cubos Restantes: {myCubes.sort((a, b) => a - b).join(', ')}</p>
            </div>

            {/* Equation Submission Section */}
            {!gameState.game_over && (
                <div style={{ border: '1px dashed green', padding: '10px', marginBottom: '15px' }}>
                    <h4>Submeter Equação (Objetivo: 10)</h4>
                    <p><i>Clique nas suas peças acima para selecioná-las.</i></p>
                    <input 
                        type="text" 
                        value={equationInput} 
                        onChange={(e) => setEquationInput(e.target.value)} 
                        placeholder="Digite a equação (ex: (2*5) ou 3+7)" 
                        style={{ width: '300px', marginRight: '10px' }} 
                    />
                    <button onClick={handleSubmitEquation} disabled={!equationInput || selectedPieceIndices.length === 0}>
                        Submeter Equação
                    </button>
                </div>
            )}
            
            {/* Last Equation Result */}
            {lastEquationResult && (
                 <div style={{ border: '1px dashed orange', padding: '10px', marginBottom: '15px', backgroundColor: lastEquationResult.valid ? '#e6ffe6' : '#ffe6e6' }}>
                    <h4>Resultado Última Equação Submetida ({getUsername(lastEquationResult.sid)})</h4>
                    <p>Equação: {lastEquationResult.equation}</p>
                    <p>Resultado: {lastEquationResult.valid ? `Válida (${lastEquationResult.result})` : `Inválida (Resultado: ${lastEquationResult.result ?? 'Erro'})`}</p>
                    {lastEquationResult.error && <p style={{color: 'red'}}>Erro: {lastEquationResult.error}</p>}
                 </div>
            )}

            {/* Optional: Display other players' piece counts? */}
            {/* <div>
                <h4>Outros Jogadores:</h4>
                {gameState.players.filter(sid => sid !== currentUserSid).map(sid => (
                    <p key={sid}>{getUsername(sid)}: {gameState.player_pieces[sid]?.length || 0} peças, {gameState.player_cubes[sid]?.length || 0} cubos restantes</p>
                ))}
            </div> */} 

        </div>
    );
};

export default JogoLeilaoExpressaoComponent;

