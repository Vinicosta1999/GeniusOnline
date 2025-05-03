import React, { useState, useEffect, useCallback } from 'react';
import { useSocket } from '../context/SocketContext';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { ScrollArea } from './ui/scroll-area';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Terminal } from 'lucide-react';

interface PlayerInfo {
    username: string;
    sid: string;
    role: 'player';
    score: number;
    questions_asked_round1: number;
    questions_asked_round2: number;
}

interface GuestInfo {
    username: string;
    sid: string;
    role: 'guest';
}

interface QuestionData {
    player_sid: string;
    player_username: string;
    question: string;
    round: number;
    result: { yes: number; no: number };
    score_awarded: number;
}

interface GameState55 {
    game_type: '5_5';
    players: { [sid: string]: PlayerInfo };
    guests: { [sid: string]: GuestInfo };
    all_participants: { [sid: string]: PlayerInfo | GuestInfo };
    player_sids_turn_order: string[];
    round: number;
    current_player_index: number;
    questions: QuestionData[];
    status: 'round_1' | 'round_2' | 'finished';
    winner: string | null | 'Empate' | 'Ninguém';
    last_event: string;
}

interface Jogo55ComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameState55 | null;
}

const Jogo55Component: React.FC<Jogo55ComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameState55 | null>(initialGameState);
    const [questionInput, setQuestionInput] = useState('');
    const [error, setError] = useState<string | null>(null);

    const handleGameStateUpdate = useCallback((newState: GameState55) => {
        console.log("Received game state update (5-5):", newState);
        setGameState(newState);
        setError(null); // Clear previous errors on state update
    }, []);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (5-5):", errorData.message);
        setError(errorData.message);
    }, []);

    useEffect(() => {
        if (socket) {
            // Request initial state if not provided or if rejoining
            if (!gameState) {
                console.log("Requesting initial game state for 5-5");
                socket.emit('get_game_state_5_5', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_5_5', handleGameStateUpdate);
            socket.on('error', handleError); // Listen for general errors as well

            // Cleanup listeners on component unmount
            return () => {
                socket.off('update_state_5_5', handleGameStateUpdate);
                socket.off('error', handleError);
            };
        } else {
            console.error("Socket not available in Jogo55Component");
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, handleGameStateUpdate, handleError, gameState]); // Add gameState to dependencies to re-request if it becomes null

    const handleAskQuestion = () => {
        if (socket && gameState && questionInput.trim()) {
            const currentPlayerSid = gameState.player_sids_turn_order[gameState.current_player_index];
            if (currentUserSid === currentPlayerSid) {
                console.log(`Emitting ask_question_5_5: ${questionInput}`);
                socket.emit('ask_question_5_5', {
                    room_code: roomCode,
                    player_sid: currentUserSid,
                    question: questionInput.trim(),
                });
                setQuestionInput('');
                setError(null);
            } else {
                setError("Não é sua vez de perguntar.");
            }
        } else if (!questionInput.trim()) {
            setError("A pergunta não pode estar vazia.");
        } else {
             setError("Não é possível enviar a pergunta agora.");
        }
    };

    if (!gameState) {
        return <div>Carregando estado do Jogo 5:5...</div>;
    }

    const currentPlayerSid = gameState.player_sids_turn_order[gameState.current_player_index];
    const currentPlayer = gameState.players[currentPlayerSid];
    const amICurrentPlayer = currentUserSid === currentPlayerSid;
    const myInfo = gameState.all_participants[currentUserSid];
    const myRole = myInfo?.role;
    const myPlayerInfo = myRole === 'player' ? gameState.players[currentUserSid] : null;

    const questionsAskedThisRound = myPlayerInfo ? myPlayerInfo[`questions_asked_round${gameState.round}` as keyof PlayerInfo] as number : 0;
    const canAskQuestion = amICurrentPlayer && myRole === 'player' && gameState.status !== 'finished' && questionsAskedThisRound < 3;

    return (
        <Card className="w-full max-w-4xl mx-auto">
            <CardHeader>
                <CardTitle>Jogo 5:5</CardTitle>
                <CardDescription>
                    Faça perguntas de Sim/Não. Se 5 convidados responderem Sim E 5 responderem Não, você marca {3} pontos!
                    {gameState.status === 'finished' ? (
                        <Badge variant="destructive" className="ml-2">Jogo Finalizado</Badge>
                    ) : (
                        <Badge className="ml-2">Rodada {gameState.round}</Badge>
                    )}
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {error && (
                    <Alert variant="destructive">
                        <Terminal className="h-4 w-4" />
                        <AlertTitle>Erro</AlertTitle>
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {gameState.status === 'finished' && (
                     <Alert variant="default">
                        <Terminal className="h-4 w-4" />
                        <AlertTitle>Fim de Jogo!</AlertTitle>
                        <AlertDescription>
                            {gameState.winner === 'Empate' ? `O jogo terminou em empate!` : gameState.winner === 'Ninguém' ? 'Ninguém marcou pontos!' : `Vencedor: ${gameState.winner}!`}
                        </AlertDescription>
                    </Alert>
                )}

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Players Info */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Jogadores</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <ul className="space-y-2">
                                {Object.values(gameState.players).map(p => (
                                    <li key={p.sid} className={`flex justify-between items-center ${p.sid === currentPlayerSid && gameState.status !== 'finished' ? 'font-bold text-primary' : ''}`}>
                                        <span>{p.username} {p.sid === currentUserSid ? '(Você)' : ''}</span>
                                        <Badge variant="secondary">{p.score} pts</Badge>
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>

                    {/* Guests Info */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Convidados ({Object.keys(gameState.guests).length})</CardTitle>
                        </CardHeader>
                        <CardContent>
                             {Object.keys(gameState.guests).length > 0 ? (
                                <ul className="space-y-1 text-sm text-muted-foreground">
                                    {Object.values(gameState.guests).map(g => (
                                        <li key={g.sid}>{g.username} {g.sid === currentUserSid ? '(Você)' : ''}</li>
                                    ))}
                                </ul>
                             ) : (
                                <p className="text-sm text-muted-foreground">Não há convidados nesta sala.</p>
                             )}
                        </CardContent>
                    </Card>

                     {/* Game Status / Current Turn */}
                     <Card>
                        <CardHeader>
                            <CardTitle>Status</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {gameState.status !== 'finished' ? (
                                <>
                                    <p>Vez de: <span className="font-semibold">{currentPlayer?.username ?? 'N/A'}</span></p>
                                    {myRole === 'player' && (
                                        <p>Perguntas feitas (Rodada {gameState.round}): {questionsAskedThisRound} / {3}</p>
                                    )}
                                    {myRole === 'guest' && (
                                        <p>Aguardando perguntas dos jogadores...</p>
                                    )}
                                </>                                
                            ) : (
                                <p>O jogo terminou.</p>
                            )}
                             <p className="text-sm text-muted-foreground pt-2">Último Evento: {gameState.last_event}</p>
                        </CardContent>
                    </Card>
                </div>

                {/* Action Area */} 
                {myRole === 'player' && gameState.status !== 'finished' && (
                    <div className="mt-4">
                        <Separator className="my-4" />
                        <h3 className="text-lg font-semibold mb-2">Sua Vez de Perguntar?</h3>
                        {amICurrentPlayer ? (
                            canAskQuestion ? (
                                <div className="flex gap-2">
                                    <Input
                                        type="text"
                                        placeholder="Digite sua pergunta Sim/Não..."
                                        value={questionInput}
                                        onChange={(e) => setQuestionInput(e.target.value)}
                                        disabled={!canAskQuestion}
                                        onKeyPress={(e) => e.key === 'Enter' && canAskQuestion && handleAskQuestion()}
                                    />
                                    <Button onClick={handleAskQuestion} disabled={!canAskQuestion || !questionInput.trim()}>
                                        Perguntar
                                    </Button>
                                </div>
                            ) : (
                                <p className="text-muted-foreground">Você já fez suas {3} perguntas nesta rodada. Aguarde o próximo jogador ou a próxima rodada.</p>
                            )
                        ) : (
                            <p className="text-muted-foreground">Aguarde sua vez de perguntar.</p>
                        )}
                    </div>
                )}

                {/* Questions History */}
                <Separator className="my-4" />
                <h3 className="text-lg font-semibold mb-2">Histórico de Perguntas</h3>
                <ScrollArea className="h-48 w-full rounded-md border p-4">
                    {gameState.questions.length > 0 ? (
                        <ul className="space-y-3">
                            {gameState.questions.slice().reverse().map((q, index) => (
                                <li key={index} className="text-sm">
                                    <p><strong>{q.player_username}</strong> (Rodada {q.round}): "{q.question}"</p>
                                    <p className="text-muted-foreground">
                                        Resultado: {q.result.yes} Sim / {q.result.no} Não.
                                        {q.score_awarded > 0 && <Badge variant="default" className="ml-2">+{q.score_awarded} pts</Badge>}
                                    </p>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="text-sm text-muted-foreground">Nenhuma pergunta feita ainda.</p>
                    )}
                </ScrollArea>
            </CardContent>
        </Card>
    );
};

export default Jogo55Component;

