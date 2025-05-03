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
import { Terminal, HelpCircle, CheckCircle, Hourglass, Trophy, Info, Coins, Bot } from 'lucide-react';

// --- Constants ---
const NUM_HORSES_CCC = 4; // Must match backend
const TOTAL_ROUNDS_CCC = 10; // Must match backend

// --- Types ---
interface PairInfo {
    player_username: string;
    guest_sid: string;
    guest_username: string;
    chips: number;
    bets: { [round: number]: { [horse: number]: number } };
}

interface GameStateCCC {
    game_type: 'corrida_cavalos_confinados';
    pairs: { [player_sid: string]: PairInfo };
    guests_map: { [guest_sid: string]: string }; // guest_sid -> player_sid
    winning_horse: number;
    clues_given: string[];
    current_round: number;
    round_bets: { [guest_sid: string]: { [horse: number]: number } }; // Bets placed in the current round before confirmation
    status: 'betting' | 'round_end' | 'finished';
    last_event: string;
    winner_pair: {
        player_username: string;
        guest_username: string;
        chips: number;
    } | null;
}

interface JogoCorridaCavalosConfinadosComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameStateCCC | null;
}

// --- Main Component ---
const JogoCorridaCavalosConfinadosComponent: React.FC<JogoCorridaCavalosConfinadosComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameStateCCC | null>(initialGameState);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(initialGameState?.last_event ?? null);
    const [selectedHorse, setSelectedHorse] = useState<string>("1");
    const [betAmount, setBetAmount] = useState<string>("");

    // --- Memoized Values ---
    const myRole = useMemo(() => {
        if (!gameState) return null;
        if (gameState.pairs[currentUserSid]) return 'player';
        if (gameState.guests_map[currentUserSid]) return 'guest';
        return null;
    }, [gameState, currentUserSid]);

    const myPlayerSid = useMemo(() => {
        if (myRole === 'player') return currentUserSid;
        if (myRole === 'guest' && gameState) return gameState.guests_map[currentUserSid];
        return null;
    }, [myRole, gameState, currentUserSid]);

    const myPairInfo = useMemo(() => {
        if (myPlayerSid && gameState) return gameState.pairs[myPlayerSid];
        return null;
    }, [myPlayerSid, gameState]);

    const myGuestSid = useMemo(() => {
        if (myRole === 'guest') return currentUserSid;
        if (myRole === 'player' && myPairInfo) return myPairInfo.guest_sid;
        return null;
    }, [myRole, myPairInfo, currentUserSid]);

    const hasGuestBetThisRound = useMemo(() => {
        if (!gameState || !myGuestSid) return false;
        return !!gameState.round_bets[myGuestSid] && Object.keys(gameState.round_bets[myGuestSid]).length > 0;
    }, [gameState, myGuestSid]);

    const canBet = useMemo(() => {
        return myRole === 'guest' && gameState?.status === 'betting' && !hasGuestBetThisRound;
    }, [myRole, gameState?.status, hasGuestBetThisRound]);

    const pairsList = useMemo(() => Object.values(gameState?.pairs ?? {}).sort((a, b) => b.chips - a.chips), [gameState]);

    // --- Callbacks ---
    const handleGameStateUpdate = useCallback((newState: GameStateCCC) => {
        console.log("Received game state update (CCC):", newState);
        setGameState(newState);
        setError(null); // Clear error on update
        setInfo(newState.last_event); // Show last event as info
        // Reset bet input on round change if guest
        if (myRole === 'guest' && newState.status === 'betting') {
            // Check if it's actually a new round by comparing round number
            if (newState.current_round !== gameState?.current_round) {
                 setBetAmount("");
                 setSelectedHorse("1");
            }
        }
    }, [myRole, gameState?.current_round]); // Add gameState?.current_round dependency

    const handleBetConfirmed = useCallback((data: { success: boolean, horse: number, amount: number, chips_remaining: number }) => {
        if (data.success) {
            setInfo(`Aposta de ${data.amount} no cavalo ${data.horse} confirmada! Fichas restantes: ${data.chips_remaining}.`);
            // State update will reflect the bet being locked
        } else {
            setError("Falha ao confirmar a aposta.");
        }
    }, []);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (CCC):", errorData.message);
        setError(errorData.message);
    }, []);

    // --- Effects ---
    useEffect(() => {
        if (socket) {
            if (!gameState) {
                console.log("Requesting initial game state for CCC");
                socket.emit('get_game_state_ccc', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_ccc', handleGameStateUpdate);
            socket.on('bet_confirmed_ccc', handleBetConfirmed);
            socket.on('error', handleError);

            return () => {
                socket.off('update_state_ccc', handleGameStateUpdate);
                socket.off('bet_confirmed_ccc', handleBetConfirmed);
                socket.off('error', handleError);
            };
        } else {
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, gameState, handleGameStateUpdate, handleBetConfirmed, handleError]);

    // --- Event Handlers ---
    const handlePlaceBet = () => {
        if (!canBet || !socket || !myGuestSid) return;

        const horseNum = parseInt(selectedHorse, 10);
        const betVal = parseInt(betAmount, 10);

        if (isNaN(horseNum) || horseNum < 1 || horseNum > NUM_HORSES_CCC) {
            setError("Número do cavalo inválido.");
            return;
        }
        if (isNaN(betVal) || betVal <= 0) {
            setError("Valor da aposta inválido.");
            return;
        }
        if (myPairInfo && betVal > myPairInfo.chips) {
            setError("Fichas insuficientes para esta aposta.");
            return;
        }

        console.log(`Emitting place_bet_ccc: horse ${horseNum}, amount ${betVal}`);
        socket.emit('place_bet_ccc', {
            room_code: roomCode,
            guest_sid: myGuestSid,
            horse: horseNum,
            amount: betVal,
        });
        setError(null);
    };

    // --- Render Logic ---
    if (!gameState || !myRole || !myPairInfo) {
        // Added myPairInfo check
        return <div>Carregando estado do Jogo Corrida de Cavalos Confinados...</div>;
    }

    const renderGuestStatusIcon = (guestSid: string) => {
        if (gameState.status === 'betting') {
            return gameState.round_bets[guestSid] && Object.keys(gameState.round_bets[guestSid]).length > 0 ?
                   <CheckCircle className="h-4 w-4 text-green-500" /> :
                   <Hourglass className="h-4 w-4 text-yellow-500" />;
        }
        // Show checkmark if they bet in the last completed round
        const lastRoundNum = gameState.current_round - (gameState.status === 'finished' ? 0 : 1);
        const playerSid = gameState.guests_map[guestSid];
        const pair = gameState.pairs[playerSid];
        if (pair && pair.bets[lastRoundNum] && Object.keys(pair.bets[lastRoundNum]).length > 0) {
             return <CheckCircle className="h-4 w-4 text-gray-400" />;
        }
        return <HelpCircle className="h-4 w-4 text-gray-400" />;
    };

    return (
        <Card className="w-full max-w-5xl mx-auto">
            <CardHeader>
                <CardTitle>Jogo Corrida de Cavalos Confinados</CardTitle>
                <CardDescription>
                    Jogadores são pareados com Convidados. Convidados apostam as fichas da dupla em um dos {NUM_HORSES_CCC} cavalos a cada rodada. Pistas são dadas nas rodadas {3}, {6}, e {9}. A dupla com mais fichas no final vence!
                    {gameState.status === 'finished' ? (
                        <Badge variant="destructive" className="ml-2">Jogo Finalizado</Badge>
                    ) : (
                        <Badge className="ml-2">Rodada {gameState.current_round} / {TOTAL_ROUNDS_CCC}</Badge>
                    )}
                    <Badge variant="outline" className="ml-2">Você é: {myRole === 'player' ? 'Jogador' : 'Convidado'}</Badge>
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

                {/* Pairs and Scores Table */}                
                <Card>
                    <CardHeader><CardTitle className="text-base">Duplas e Fichas</CardTitle></CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Jogador</TableHead>
                                    <TableHead>Convidado</TableHead>
                                    <TableHead className="text-center">Status Convidado</TableHead>
                                    <TableHead className="text-right"><Coins className="h-4 w-4 inline mr-1"/> Fichas</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {pairsList.map(p => {
                                    const playerSid = Object.keys(gameState.pairs).find(key => gameState.pairs[key].guest_sid === p.guest_sid);
                                    const isMyPair = playerSid === myPlayerSid;
                                    return (
                                        <TableRow key={p.guest_sid} className={isMyPair ? "bg-muted/50 font-semibold" : ""}>
                                            <TableCell>{p.player_username} {isMyPair && myRole === 'player' ? '(Você)' : ''}</TableCell>
                                            <TableCell>{p.guest_username} {isMyPair && myRole === 'guest' ? '(Você)' : ''}</TableCell>
                                            <TableCell className="text-center">{renderGuestStatusIcon(p.guest_sid)}</TableCell>
                                            <TableCell className="text-right">{p.chips}</TableCell>
                                        </TableRow>
                                    );
                                })}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Clues */}                    
                    <Card>
                        <CardHeader><CardTitle className="text-base"><Info className="h-4 w-4 inline mr-1"/> Pistas Reveladas</CardTitle></CardHeader>
                        <CardContent>
                            {gameState.clues_given.length > 0 ? (
                                <ul className="space-y-1 text-sm list-disc list-inside">
                                    {gameState.clues_given.map((clue, index) => (
                                        <li key={index}>{clue}</li>
                                    ))}
                                </ul>
                            ) : (
                                <p className="text-sm text-muted-foreground">Nenhuma pista revelada ainda.</p>
                            )}
                        </CardContent>
                    </Card>

                    {/* Betting Area (Guest Only) */}                    
                    {myRole === 'guest' && (
                        <Card>
                            <CardHeader><CardTitle className="text-base">Sua Aposta (Rodada {gameState.current_round})</CardTitle></CardHeader>
                            <CardContent className="space-y-3">
                                {gameState.status === 'betting' ? (
                                    !hasGuestBetThisRound ? (
                                        <div className="flex flex-col sm:flex-row gap-2 items-center">
                                            <Select value={selectedHorse} onValueChange={setSelectedHorse} disabled={!canBet}>
                                                <SelectTrigger className="w-full sm:w-[180px]">
                                                    <SelectValue placeholder="Cavalo" />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {[...Array(NUM_HORSES_CCC)].map((_, i) => (
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
                                                max={myPairInfo?.chips ?? 0}
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
                                            Aposta feita nesta rodada. Aguardando outros convidados...
                                        </p>
                                    )
                                ) : gameState.status === 'finished' ? (
                                     <p className="text-muted-foreground">O jogo terminou.</p>
                                ) : (
                                    <p className="text-muted-foreground">Aguardando início da próxima rodada de apostas...</p>
                                )}
                            </CardContent>
                        </Card>
                    )}
                    {/* Player View */}                    
                    {myRole === 'player' && (
                         <Card>
                            <CardHeader><CardTitle className="text-base">Status do Convidado</CardTitle></CardHeader>
                            <CardContent>
                                {gameState.status === 'betting' ? (
                                    !hasGuestBetThisRound ? (
                                        <p className="flex items-center text-yellow-600">
                                            <Hourglass className="h-4 w-4 mr-2"/> Seu convidado ({myPairInfo?.guest_username}) está apostando...
                                        </p>
                                    ) : (
                                         <p className="flex items-center text-green-600">
                                            <CheckCircle className="h-4 w-4 mr-2"/> Seu convidado ({myPairInfo?.guest_username}) já apostou nesta rodada.
                                        </p>
                                    )
                                ) : gameState.status === 'finished' ? (
                                     <p className="text-muted-foreground">O jogo terminou.</p>
                                ) : (
                                    <p className="text-muted-foreground">Aguardando próxima rodada de apostas...</p>
                                )}
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Finished State */}                
                {gameState.status === 'finished' && gameState.winner_pair && (
                    <div className="space-y-4 mt-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={'default'}>
                            <Trophy className="h-4 w-4" />
                            <AlertTitle>
                                Dupla Vencedora: {gameState.winner_pair.player_username} e {gameState.winner_pair.guest_username}!
                            </AlertTitle>
                            <AlertDescription>
                                Terminaram com {gameState.winner_pair.chips} fichas. O cavalo vencedor era o número {gameState.winning_horse}.
                            </AlertDescription>
                        </Alert>
                    </div>
                )}
                 {gameState.status === 'finished' && !gameState.winner_pair && (
                     <div className="space-y-4 mt-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={'default'}>
                            <Bot className="h-4 w-4" />
                            <AlertTitle>Empate ou Sem Vencedor Claro</AlertTitle>
                            <AlertDescription>
                                Não houve uma dupla vencedora clara. O cavalo vencedor era o número {gameState.winning_horse}.
                            </AlertDescription>
                        </Alert>
                    </div>
                 )}

            </CardContent>
        </Card>
    );
};

export default JogoCorridaCavalosConfinadosComponent;

