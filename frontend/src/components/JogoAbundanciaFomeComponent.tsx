import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSocket } from '../context/SocketContext';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Terminal, HelpCircle, CheckCircle, Hourglass, Wheat, Ticket, Trophy, Users } from 'lucide-react';

// --- Types ---
interface PlayerStateAbundanciaFome {
    username: string;
    sid: string;
    bread: number;
    coupons: number;
    choices: { [round: number]: 'abundancia' | 'fome' | null };
    round_results: { [round: number]: { area: string | null; bread_received: number; coupons_received: number } };
}

interface RoundSummary {
    round: number;
    abundancia_players: string[];
    fome_players: string[];
    bread_per_abundancia: number;
    coupons_per_fome: number;
    num_abundancia: number;
    num_fome: number;
}

interface WinnerInfo {
    type: 'bread' | 'coupons' | 'draw';
    winners: string[];
    score: number;
    reason: string;
}

interface GameStateAbundanciaFome {
    game_type: 'abundancia_fome';
    players: { [sid: string]: PlayerStateAbundanciaFome };
    current_round: number;
    round_choices: { [sid: string]: 'abundancia' | 'fome' }; // Only current round's choices before calculation
    status: 'choosing' | 'calculating' | 'finished';
    round_summary: RoundSummary | null;
    winner: WinnerInfo | null;
    last_event: string;
    room_code: string;
}

interface JogoAbundanciaFomeComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameStateAbundanciaFome | null;
}

const TOTAL_ROUNDS_AF = 10; // Make sure this matches backend

// --- Main Component ---
const JogoAbundanciaFomeComponent: React.FC<JogoAbundanciaFomeComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameStateAbundanciaFome | null>(initialGameState);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(initialGameState?.last_event ?? null);

    // --- Memoized Values ---
    const myPlayerState = useMemo(() => gameState?.players[currentUserSid], [gameState, currentUserSid]);
    const playerList = useMemo(() => Object.values(gameState?.players ?? {}).sort((a, b) => b.bread - a.bread || b.coupons - a.coupons), [gameState]); // Sort for ranking
    const myChoiceThisRound = useMemo(() => gameState?.round_choices[currentUserSid], [gameState, currentUserSid]);
    const hasMadeChoice = !!myChoiceThisRound;

    // --- Callbacks ---
    const handleGameStateUpdate = useCallback((newState: GameStateAbundanciaFome) => {
        console.log("Received game state update (Abundância/Fome):", newState);
        setGameState(newState);
        setError(null); // Clear error on update
        setInfo(newState.last_event); // Show last event as info
    }, []);

    const handleChoiceConfirmed = useCallback((data: { success: boolean, area: 'abundancia' | 'fome' }) => {
        if (data.success) {
            setInfo(`Sua escolha (${data.area}) foi confirmada para esta rodada.`);
            // The main state update will reflect the choice being locked in round_choices
        } else {
            setError("Falha ao confirmar a escolha.");
        }
    }, []);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (Abundância/Fome):", errorData.message);
        setError(errorData.message);
    }, []);

    // --- Effects ---
    useEffect(() => {
        if (socket) {
            if (!gameState) {
                console.log("Requesting initial game state for Abundância/Fome");
                socket.emit('get_game_state_abundancia_fome', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_abundancia_fome', handleGameStateUpdate);
            socket.on('choice_confirmed_abundancia_fome', handleChoiceConfirmed);
            socket.on('error', handleError);

            return () => {
                socket.off('update_state_abundancia_fome', handleGameStateUpdate);
                socket.off('choice_confirmed_abundancia_fome', handleChoiceConfirmed);
                socket.off('error', handleError);
            };
        } else {
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, gameState, handleGameStateUpdate, handleChoiceConfirmed, handleError]);

    // --- Event Handlers ---
    const handleChooseArea = (area: 'abundancia' | 'fome') => {
        if (socket && gameState && gameState.status === 'choosing' && !hasMadeChoice) {
            console.log(`Emitting choose_area_abundancia_fome with area: ${area}`);
            socket.emit('choose_area_abundancia_fome', {
                room_code: roomCode,
                player_sid: currentUserSid,
                area: area,
            });
            setError(null);
        }
    };

    // --- Render Logic ---
    if (!gameState || !myPlayerState) {
        return <div>Carregando estado do Jogo Abundância/Fome...</div>;
    }

    const renderPlayerStatusIcon = (playerSid: string) => {
        if (gameState.status === 'choosing') {
            return gameState.round_choices[playerSid] ? 
                   <CheckCircle className="h-4 w-4 text-green-500" /> : 
                   <Hourglass className="h-4 w-4 text-yellow-500" />;
        }
        // In calculating/finished, show the choice made for the *last completed* round
        const lastRoundChoice = gameState.players[playerSid]?.choices[gameState.current_round - (gameState.status === 'finished' ? 0 : 1)];
        if (lastRoundChoice === 'abundancia') return <Wheat className="h-4 w-4 text-yellow-600" />;
        if (lastRoundChoice === 'fome') return <Ticket className="h-4 w-4 text-blue-600" />;
        return <HelpCircle className="h-4 w-4 text-gray-400" />;
    };

    return (
        <Card className="w-full max-w-4xl mx-auto">
            <CardHeader>
                <CardTitle>Jogo Abundância e Fome</CardTitle>
                <CardDescription>
                    Escolha entre a área da Abundância (divide pães) ou da Fome (ganha cupons). O objetivo principal é acumular mais pães ao final de {TOTAL_ROUNDS_AF} rodadas.
                    {gameState.status === 'finished' ? (
                        <Badge variant="destructive" className="ml-2">Jogo Finalizado</Badge>
                    ) : (
                        <Badge className="ml-2">Rodada {gameState.current_round} / {TOTAL_ROUNDS_AF}</Badge>
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
                {info && !error && (
                    <Alert variant="default">
                        <HelpCircle className="h-4 w-4" />
                        <AlertTitle>Info</AlertTitle>
                        <AlertDescription>{info}</AlertDescription>
                    </Alert>
                )}

                {/* Player Scores Table */}                
                <Card>
                    <CardHeader><CardTitle className="text-base">Placar</CardTitle></CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Jogador</TableHead>
                                    <TableHead className="text-center">Status</TableHead>
                                    <TableHead className="text-right"><Wheat className="h-4 w-4 inline mr-1"/> Pães</TableHead>
                                    <TableHead className="text-right"><Ticket className="h-4 w-4 inline mr-1"/> Cupons</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {playerList.map(p => (
                                    <TableRow key={p.sid} className={p.sid === currentUserSid ? "bg-muted/50 font-semibold" : ""}>
                                        <TableCell>{p.username} {p.sid === currentUserSid ? '(Você)' : ''}</TableCell>
                                        <TableCell className="text-center">{renderPlayerStatusIcon(p.sid)}</TableCell>
                                        <TableCell className="text-right">{p.bread}</TableCell>
                                        <TableCell className="text-right">{p.coupons}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                {/* Action Area (Choosing Phase) */}                
                {gameState.status === 'choosing' && (
                    <div className="text-center space-y-4">
                        <Separator />
                        <h3 className="text-lg font-semibold">Rodada {gameState.current_round}: Faça sua Escolha</h3>
                        {!hasMadeChoice ? (
                            <div className="flex gap-4 justify-center">
                                <Button onClick={() => handleChooseArea('abundancia')} size="lg" variant="outline" className="border-yellow-500 hover:bg-yellow-50 text-yellow-700">
                                    <Wheat className="h-5 w-5 mr-2"/> Ir para Abundância
                                </Button>
                                <Button onClick={() => handleChooseArea('fome')} size="lg" variant="outline" className="border-blue-500 hover:bg-blue-50 text-blue-700">
                                    <Ticket className="h-5 w-5 mr-2"/> Ir para Fome
                                </Button>
                            </div>
                        ) : (
                            <p className="text-green-600 font-semibold flex items-center justify-center">
                                <CheckCircle className="h-5 w-5 mr-2"/>
                                Você escolheu ir para a área da {myChoiceThisRound === 'abundancia' ? 'Abundância' : 'Fome'} nesta rodada. Aguardando outros jogadores...
                            </p>
                        )}
                    </div>
                )}

                {/* Round Summary (After Calculating) */}                
                {gameState.round_summary && gameState.current_round > gameState.round_summary.round && (
                    <Card className="bg-muted/30">
                        <CardHeader>
                            <CardTitle className="text-base">Resumo da Rodada {gameState.round_summary.round}</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2 text-sm">
                            <div className="flex items-center">
                                <Users className="h-4 w-4 mr-2 text-yellow-600"/> 
                                <span>{gameState.round_summary.num_abundancia} na Abundância: {gameState.round_summary.abundancia_players.join(', ') || 'Ninguém'}</span>
                                <span className="ml-auto font-medium">+{gameState.round_summary.bread_per_abundancia} <Wheat className="h-3 w-3 inline"/> cada</span>
                            </div>
                             <div className="flex items-center">
                                <Users className="h-4 w-4 mr-2 text-blue-600"/> 
                                <span>{gameState.round_summary.num_fome} na Fome: {gameState.round_summary.fome_players.join(', ') || 'Ninguém'}</span>
                                <span className="ml-auto font-medium">+{gameState.round_summary.coupons_per_fome} <Ticket className="h-3 w-3 inline"/> cada</span>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Finished State */}                
                {gameState.status === 'finished' && gameState.winner && (
                    <div className="space-y-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={"default"}>
                            <Trophy className="h-4 w-4" />
                            <AlertTitle>
                                {gameState.winner.type === 'draw' ? "Empate!" : `Vencedor${gameState.winner.winners.length > 1 ? 'es' : ''}: ${gameState.winner.winners.join(', ')}!`}
                            </AlertTitle>
                            <AlertDescription>
                                {gameState.winner.reason}
                                {gameState.winner.type !== 'draw' && ` (${gameState.winner.score} ${gameState.winner.type === 'bread' ? 'pães' : 'cupons'})`}
                            </AlertDescription>
                        </Alert>
                        {/* Optionally show final scores again or history */}                        
                    </div>
                )}

            </CardContent>
        </Card>
    );
};

export default JogoAbundanciaFomeComponent;

