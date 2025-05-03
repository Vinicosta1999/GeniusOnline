import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSocket } from '../context/SocketContext';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Terminal, HelpCircle, CheckCircle, Hourglass, Trophy, Coins, Bomb, Lightbulb } from 'lucide-react';

// --- Constants ---
const NUM_HORSES_CCG = 4; // Must match backend
const TOTAL_ROUNDS_CCG = 12; // Must match backend
const MAX_BET_PER_ROUND_CCG = 3; // Must match backend
const CLUE_COST_CCG = 3; // Must match backend

// --- Types ---
// Public player info received in state updates
interface PublicPlayerInfoCCG {
    username: string;
    chips: number;
    grenades: number;
    has_bet_this_round: boolean;
}

// Private player info received separately
interface PrivatePlayerInfoCCG {
    clues: string[];
    // bets: { [round: number]: { [horse: number]: number } }; // Maybe needed later for history
}

interface FinalResultsCCG {
    winner_username: string;
    max_chips: number;
    payouts: { [sid: string]: number };
}

// Combined public state received via broadcast
interface GameStateCCG {
    game_type: 'corrida_cavalos_golpistas';
    players: { [sid: string]: PublicPlayerInfoCCG };
    current_round: number;
    status: 'betting' | 'round_end' | 'finished';
    last_event: string;
    final_results: FinalResultsCCG | null;
    winning_horse?: number; // Only available when status is 'finished'
}

interface JogoCorridaCavalosGolpistasComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameStateCCG | null; // Public state
}

// --- Main Component ---
const JogoCorridaCavalosGolpistasComponent: React.FC<JogoCorridaCavalosGolpistasComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameStateCCG | null>(initialGameState);
    const [myPrivateInfo, setMyPrivateInfo] = useState<PrivatePlayerInfoCCG>({ clues: [] });
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(initialGameState?.last_event ?? null);
    const [selectedHorse, setSelectedHorse] = useState<string>("1");
    const [betAmount, setBetAmount] = useState<string>("1"); // Default to 1 chip

    // --- Memoized Values ---
    const myPublicInfo = useMemo(() => gameState?.players[currentUserSid], [gameState, currentUserSid]);
    const myClues = useMemo(() => myPrivateInfo.clues, [myPrivateInfo]);
    const myChips = useMemo(() => myPublicInfo?.chips ?? 0, [myPublicInfo]);
    const myGrenades = useMemo(() => myPublicInfo?.grenades ?? 0, [myPublicInfo]);
    const hasBetThisRound = useMemo(() => myPublicInfo?.has_bet_this_round ?? false, [myPublicInfo]);

    const canBet = useMemo(() => {
        return gameState?.status === 'betting' && !hasBetThisRound;
    }, [gameState?.status, hasBetThisRound]);

    const canBuyClue = useMemo(() => {
        // Allow buying clues during betting phase if affordable
        return gameState?.status === 'betting' && myGrenades >= CLUE_COST_CCG;
    }, [gameState?.status, myGrenades]);

    const playerList = useMemo(() => {
        if (!gameState) return [];
        return Object.entries(gameState.players)
            .map(([sid, data]) => ({ sid, ...data }))
            .sort((a, b) => b.chips - a.chips || b.grenades - a.grenades); // Sort by chips, then grenades
    }, [gameState]);

    // --- Callbacks ---
    const handleGameStateUpdate = useCallback((newState: GameStateCCG) => {
        console.log("Received game state update (CCG):", newState);
        setGameState(newState);
        setError(null); // Clear error on update
        setInfo(newState.last_event); // Show last event as info
        // Reset bet input on round change if betting phase starts
        if (newState.status === 'betting' && gameState?.status !== 'betting') {
            setBetAmount("1");
            setSelectedHorse("1");
        }
    }, [gameState?.status]); // Add gameState?.status dependency

    const handleInitialInfo = useCallback((data: { clues: string[] }) => {
        console.log("Received initial private info (CCG):", data);
        setMyPrivateInfo(prev => ({ ...prev, clues: data.clues }));
    }, []);

    const handleNewClue = useCallback((data: { clue: string, grenades_remaining: number }) => {
        console.log("Received new clue (CCG):", data);
        setMyPrivateInfo(prev => ({ ...prev, clues: [...prev.clues, data.clue] }));
        // Update public state locally for immediate feedback on grenade count
        setGameState(prev => prev ? {
            ...prev,
            players: {
                ...prev.players,
                [currentUserSid]: {
                    ...prev.players[currentUserSid],
                    grenades: data.grenades_remaining
                }
            }
        } : null);
        setInfo(`Nova pista comprada! ${data.clue}`);
    }, [currentUserSid]);

    const handleBetConfirmed = useCallback((data: { success: boolean, horse: number, amount: number, chips_remaining: number }) => {
        if (data.success) {
            setInfo(`Aposta de ${data.amount} no cavalo ${data.horse} confirmada! Fichas restantes: ${data.chips_remaining}.`);
            // Update public state locally for immediate feedback
            setGameState(prev => prev ? {
                ...prev,
                players: {
                    ...prev.players,
                    [currentUserSid]: {
                        ...prev.players[currentUserSid],
                        chips: data.chips_remaining,
                        has_bet_this_round: true
                    }
                }
            } : null);
        } else {
            setError("Falha ao confirmar a aposta.");
        }
    }, [currentUserSid]);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (CCG):", errorData.message);
        setError(errorData.message);
    }, []);

    // --- Effects ---
    useEffect(() => {
        if (socket) {
            if (!gameState) {
                console.log("Requesting initial game state for CCG");
                socket.emit('get_game_state_ccg', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_ccg', handleGameStateUpdate);
            socket.on('initial_info_ccg', handleInitialInfo);
            socket.on('new_clue_ccg', handleNewClue);
            socket.on('bet_confirmed_ccg', handleBetConfirmed);
            socket.on('error', handleError);

            return () => {
                socket.off('update_state_ccg', handleGameStateUpdate);
                socket.off('initial_info_ccg', handleInitialInfo);
                socket.off('new_clue_ccg', handleNewClue);
                socket.off('bet_confirmed_ccg', handleBetConfirmed);
                socket.off('error', handleError);
            };
        } else {
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, gameState, handleGameStateUpdate, handleInitialInfo, handleNewClue, handleBetConfirmed, handleError]);

    // --- Event Handlers ---
    const handlePlaceBet = () => {
        if (!canBet || !socket) return;

        const horseNum = parseInt(selectedHorse, 10);
        const betVal = parseInt(betAmount, 10);

        if (isNaN(horseNum) || horseNum < 1 || horseNum > NUM_HORSES_CCG) {
            setError("Número do cavalo inválido.");
            return;
        }
        if (isNaN(betVal) || betVal < 1 || betVal > MAX_BET_PER_ROUND_CCG) {
            setError(`Valor da aposta inválido (deve ser entre 1 e ${MAX_BET_PER_ROUND_CCG}).`);
            return;
        }
        if (betVal > myChips) {
            setError("Fichas insuficientes para esta aposta.");
            return;
        }

        console.log(`Emitting place_bet_ccg: horse ${horseNum}, amount ${betVal}`);
        socket.emit('place_bet_ccg', {
            room_code: roomCode,
            player_sid: currentUserSid,
            horse: horseNum,
            amount: betVal,
        });
        setError(null);
    };

    const handleBuyClue = () => {
        if (!canBuyClue || !socket) return;

        console.log(`Emitting buy_clue_ccg`);
        socket.emit('buy_clue_ccg', {
            room_code: roomCode,
            player_sid: currentUserSid,
        });
        setError(null);
    };

    // --- Render Logic ---
    if (!gameState || !myPublicInfo) {
        return <div>Carregando estado do Jogo Corrida de Cavalos Golpistas...</div>;
    }

    const renderPlayerStatusIcon = (playerSid: string) => {
        const player = gameState.players[playerSid];
        if (!player) return <HelpCircle className="h-4 w-4 text-gray-400" />;
        if (gameState.status === 'betting') {
            return player.has_bet_this_round ?
                   <CheckCircle className="h-4 w-4 text-green-500" /> :
                   <Hourglass className="h-4 w-4 text-yellow-500" />;
        }
        // Show checkmark if they bet in the last completed round (less relevant here)
        return <CheckCircle className="h-4 w-4 text-gray-400" />;
    };

    return (
        <Card className="w-full max-w-5xl mx-auto">
            <CardHeader>
                <CardTitle>Jogo Corrida de Cavalos Golpistas</CardTitle>
                <CardDescription>
                    Aposte até {MAX_BET_PER_ROUND_CCG} fichas por rodada no cavalo vencedor. Use granadas ({CLUE_COST_CCG} cada) para comprar pistas. Quem tiver mais fichas após {TOTAL_ROUNDS_CCG} rodadas vence!
                    {gameState.status === 'finished' ? (
                        <Badge variant="destructive" className="ml-2">Jogo Finalizado</Badge>
                    ) : (
                        <Badge className="ml-2">Rodada {gameState.current_round} / {TOTAL_ROUNDS_CCG}</Badge>
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
                    <CardHeader><CardTitle className="text-base">Jogadores</CardTitle></CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Jogador</TableHead>
                                    <TableHead className="text-center">Status</TableHead>
                                    <TableHead className="text-right"><Coins className="h-4 w-4 inline mr-1"/> Fichas</TableHead>
                                    <TableHead className="text-right"><Bomb className="h-4 w-4 inline mr-1"/> Granadas</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {playerList.map(p => (
                                    <TableRow key={p.sid} className={p.sid === currentUserSid ? "bg-muted/50 font-semibold" : ""}>
                                        <TableCell>{p.username} {p.sid === currentUserSid ? '(Você)' : ''}</TableCell>
                                        <TableCell className="text-center">{renderPlayerStatusIcon(p.sid)}</TableCell>
                                        <TableCell className="text-right">{p.chips}</TableCell>
                                        <TableCell className="text-right">{p.grenades}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Clues */}                    
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between">
                            <CardTitle className="text-base"><Lightbulb className="h-4 w-4 inline mr-1"/> Suas Pistas</CardTitle>
                            <Button 
                                size="sm" 
                                variant="outline"
                                onClick={handleBuyClue}
                                disabled={!canBuyClue}
                                title={`Comprar pista (Custo: ${CLUE_COST_CCG} granadas)`}
                            >
                                <Bomb className="h-4 w-4 mr-1"/> Comprar ({myGrenades})
                            </Button>
                        </CardHeader>
                        <CardContent>
                            {myClues.length > 0 ? (
                                <ul className="space-y-1 text-sm list-disc list-inside">
                                    {myClues.map((clue, index) => (
                                        <li key={index}>{clue}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-sm text-muted-foreground">Você ainda não tem pistas.</p>
                            )}
                        </CardContent>
                    </Card>

                    {/* Betting Area */}                    
                    <Card>
                        <CardHeader><CardTitle className="text-base">Sua Aposta (Rodada {gameState.current_round})</CardTitle></CardHeader>
                        <CardContent className="space-y-3">
                            {gameState.status === 'betting' ? (
                                !hasBetThisRound ? (
                                    <div className="flex flex-col sm:flex-row gap-2 items-center">
                                        <Select value={selectedHorse} onValueChange={setSelectedHorse} disabled={!canBet}>
                                            <SelectTrigger className="w-full sm:w-[180px]">
                                                <SelectValue placeholder="Cavalo" />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {[...Array(NUM_HORSES_CCG)].map((_, i) => (
                                                    <SelectItem key={i + 1} value={String(i + 1)}>Cavalo {i + 1}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                        <Input
                                            type="number"
                                            placeholder="Valor"
                                            value={betAmount}
                                            onChange={(e) => setBetAmount(e.target.value)}
                                            min="1"
                                            max={Math.min(MAX_BET_PER_ROUND_CCG, myChips)} // Can't bet more than max or current chips
                                            disabled={!canBet}
                                            className="flex-1"
                                        />
                                        <Button onClick={handlePlaceBet} disabled={!canBet || !betAmount || parseInt(betAmount) <= 0}>
                                            Apostar
                                        </Button>
                                    </div>
                                ) : (
                                    <p className="text-green-600 font-semibold flex items-center">
                                        <CheckCircle className="h-5 w-5 mr-2"/>
                                        Aposta feita nesta rodada. Aguardando outros jogadores...
                                    </p>
                                )
                            ) : gameState.status === 'finished' ? (
                                 <p className="text-muted-foreground">O jogo terminou.</p>
                            ) : (
                                <p className="text-muted-foreground">Aguardando início da próxima rodada de apostas...</p>
                            )}
                        </CardContent>
                    </Card>
                </div>

                {/* Finished State */}                
                {gameState.status === 'finished' && gameState.final_results && (
                    <div className="space-y-4 mt-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={'default'}>
                            <Trophy className="h-4 w-4" />
                            <AlertTitle>
                                Vencedor(es): {gameState.final_results.winner_username}!
                            </AlertTitle>
                            <AlertDescription>
                                Terminou com {gameState.final_results.max_chips} fichas. O cavalo vencedor era o número {gameState.winning_horse}.
                            </AlertDescription>
                        </Alert>
                        {/* Optional: Show detailed payout table */}
                    </div>
                )}

            </CardContent>
        </Card>
    );
};

export default JogoCorridaCavalosGolpistasComponent;

