import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSocket } from '../context/SocketContext';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Terminal, HelpCircle, CheckCircle, Hourglass, Trophy, Users, Scale, ShieldQuestion, GitCommitHorizontal } from 'lucide-react';

// --- Constants ---
const ROUNDS_TO_WIN_DK = 3; // Must match backend

// --- Types ---
interface PlayerInfoDK {
    username: string;
    beans: number;
}

interface TeamInfoDK {
    players: { [sid: string]: PlayerInfoDK };
    round_wins: number;
}

interface LastRoundSummaryDK {
    round: number;
    team_A_total: number;
    team_B_total: number;
    winner: 'A' | 'B' | 'draw';
}

// Public state received via broadcast
interface GameStateDK {
    game_type: 'dilema_kong';
    teams: {
        A: TeamInfoDK;
        B: TeamInfoDK;
    };
    player_to_team: { [sid: string]: 'A' | 'B' };
    current_round: number;
    status: 'depositing' | 'round_reveal' | 'finished';
    last_round_winner: 'A' | 'B' | 'draw' | null;
    last_round_summary: LastRoundSummaryDK | null;
    game_winner: 'A' | 'B' | null; // Can be 'draw' if max rounds implemented
    last_event: string;
    round_player_deposits_revealed?: { [sid: string]: number } | null; // Only available after round reveal
}

interface JogoDilemaKongComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameStateDK | null; // Public state
}

// --- Main Component ---
const JogoDilemaKongComponent: React.FC<JogoDilemaKongComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameStateDK | null>(initialGameState);
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(initialGameState?.last_event ?? null);
    const [depositAmount, setDepositAmount] = useState<string>("0");
    const [hasDepositedThisRound, setHasDepositedThisRound] = useState<boolean>(false);

    // --- Memoized Values ---
    const myTeamId = useMemo(() => gameState?.player_to_team[currentUserSid], [gameState, currentUserSid]);
    const myPlayerInfo = useMemo(() => {
        if (!gameState || !myTeamId) return null;
        return gameState.teams[myTeamId]?.players[currentUserSid];
    }, [gameState, myTeamId, currentUserSid]);
    const myBeans = useMemo(() => myPlayerInfo?.beans ?? 0, [myPlayerInfo]);

    const canDeposit = useMemo(() => {
        return gameState?.status === 'depositing' && !hasDepositedThisRound;
    }, [gameState?.status, hasDepositedThisRound]);

    // const teamAPlayers = useMemo(() => Object.values(gameState?.teams.A.players ?? {}), [gameState?.teams.A.players]);
    // const teamBPlayers = useMemo(() => Object.values(gameState?.teams.B.players ?? {}), [gameState?.teams.B.players]);

    // --- Callbacks ---
    const handleGameStateUpdate = useCallback((newState: GameStateDK) => {
        console.log("Received game state update (DK):", newState);
        
        // Reset deposit status if starting a new depositing round
        if (newState.status === 'depositing' && gameState?.status !== 'depositing') {
            setHasDepositedThisRound(false);
            setDepositAmount("0");
        }
        
        setGameState(newState);
        setError(null); // Clear error on update
        setInfo(newState.last_event); // Show last event as info
    }, [gameState?.status]); // Depend on previous status

    const handleDepositConfirmed = useCallback((data: { success: boolean, amount: number }) => {
        if (data.success) {
            setInfo(`Depósito de ${data.amount} feijões confirmado para esta rodada.`);
            setHasDepositedThisRound(true);
            // Local state update for beans is handled by the main game state update
        } else {
            setError("Falha ao confirmar o depósito.");
            setHasDepositedThisRound(false); // Allow retry if failed
        }
    }, []);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (DK):", errorData.message);
        setError(errorData.message);
    }, []);

    // --- Effects ---
    useEffect(() => {
        if (socket) {
            if (!gameState) {
                console.log("Requesting initial game state for DK");
                socket.emit('get_game_state_dk', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_dk', handleGameStateUpdate);
            socket.on('deposit_confirmed_dk', handleDepositConfirmed);
            socket.on('error', handleError);

            return () => {
                socket.off('update_state_dk', handleGameStateUpdate);
                socket.off('deposit_confirmed_dk', handleDepositConfirmed);
                socket.off('error', handleError);
            };
        } else {
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, gameState, handleGameStateUpdate, handleDepositConfirmed, handleError]);

    // --- Event Handlers ---
    const handleDepositBeans = () => {
        if (!canDeposit || !socket) return;

        const amountVal = parseInt(depositAmount, 10);

        if (isNaN(amountVal) || amountVal < 0) {
            setError("Valor do depósito inválido (deve ser 0 ou maior).");
            return;
        }
        if (amountVal > myBeans) {
            setError(`Valor inválido. Você só tem ${myBeans} feijões.`);
            return;
        }

        console.log(`Emitting deposit_beans_dk: amount ${amountVal}`);
        socket.emit('deposit_beans_dk', {
            room_code: roomCode,
            player_sid: currentUserSid,
            amount: amountVal,
        });
        setError(null);
    };

    // --- Render Logic ---
    if (!gameState || !myTeamId || !myPlayerInfo) {
        return <div>Carregando estado do Jogo Dilema de Kong...</div>;
    }

    const renderTeamCard = (teamId: 'A' | 'B', teamInfo: TeamInfoDK) => (
        <Card className={`flex-1 ${myTeamId === teamId ? 'border-primary' : ''}`}>
            <CardHeader>
                <CardTitle className="flex justify-between items-center">
                    <span>Equipe {teamId} {myTeamId === teamId ? '(Sua Equipe)' : ''}</span>
                    <Badge variant={myTeamId === teamId ? 'default' : 'secondary'}>Vitórias: {teamInfo.round_wins} / {ROUNDS_TO_WIN_DK}</Badge>
                </CardTitle>
            </CardHeader>
            <CardContent>
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Jogador</TableHead>
                            <TableHead className="text-right">Feijões</TableHead>
                            <TableHead className="text-center">Depositou?</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {Object.entries(teamInfo.players).map(([sid, pInfo]) => (
                            <TableRow key={sid} className={sid === currentUserSid ? "font-semibold" : ""}>
                                <TableCell>{pInfo.username} {sid === currentUserSid ? '(Você)' : ''}</TableCell>
                                <TableCell className="text-right">{pInfo.beans}</TableCell>
                                <TableCell className="text-center">
                                    {gameState.status === 'depositing' ? (
                                        gameState.round_player_deposits_revealed?.[sid] !== undefined || (sid === currentUserSid && hasDepositedThisRound) ? 
                                        <CheckCircle className="h-4 w-4 text-green-500 mx-auto" /> : 
                                        <Hourglass className="h-4 w-4 text-yellow-500 mx-auto" />
                                    ) : gameState.round_player_deposits_revealed?.[sid] !== undefined ? (
                                        <span title={`Depositou ${gameState.round_player_deposits_revealed[sid]}`}><GitCommitHorizontal className="h-4 w-4 mx-auto"/></span>
                                    ) : (
                                        <ShieldQuestion className="h-4 w-4 text-gray-400 mx-auto" />
                                    )}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </CardContent>
        </Card>
    );

    return (
        <Card className="w-full max-w-5xl mx-auto">
            <CardHeader>
                <CardTitle>O Dilema de Kong</CardTitle>
                <CardDescription>
                    Duas equipes competem. Deposite feijões secretamente a cada rodada. A equipe que depositar mais feijões vence a rodada. A primeira equipe a vencer {ROUNDS_TO_WIN_DK} rodadas ganha o jogo!
                    {gameState.status === 'finished' ? (
                        <Badge variant="destructive" className="ml-2">Jogo Finalizado</Badge>
                    ) : (
                        <Badge className="ml-2">Rodada {gameState.current_round}</Badge>
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

                {/* Team Info */}                
                <div className="flex flex-col md:flex-row gap-4">
                    {renderTeamCard('A', gameState.teams.A)}
                    {renderTeamCard('B', gameState.teams.B)}
                </div>

                {/* Deposit Area */}                
                {gameState.status === 'depositing' && (
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Rodada {gameState.current_round}: Depositar Feijões</CardTitle>
                            <CardDescription>Quantos dos seus {myBeans} feijões você quer depositar secretamente nesta rodada?</CardDescription>
                        </CardHeader>
                        <CardContent>
                            {!hasDepositedThisRound ? (
                                <div className="flex flex-col sm:flex-row gap-2 items-center">
                                    <Input
                                        type="number"
                                        placeholder="Quantidade"
                                        value={depositAmount}
                                        onChange={(e) => setDepositAmount(e.target.value)}
                                        min="0"
                                        max={myBeans}
                                        disabled={!canDeposit}
                                        className="flex-1"
                                    />
                                    <Button onClick={handleDepositBeans} disabled={!canDeposit}>
                                        Depositar
                                    </Button>
                                </div>
                            ) : (
                                <p className="text-green-600 font-semibold flex items-center">
                                    <CheckCircle className="h-5 w-5 mr-2"/>
                                    Depósito feito nesta rodada. Aguardando outros jogadores...
                                </p>
                            )}
                        </CardContent>
                    </Card>
                )}

                {/* Round Reveal / Summary */}                
                {gameState.status === 'round_reveal' && gameState.last_round_summary && (
                    <Card className="bg-muted/30">
                        <CardHeader>
                            <CardTitle className="text-base">Resultado da Rodada {gameState.last_round_summary.round}</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2 text-sm">
                            <div className="flex items-center">
                                <Scale className="h-4 w-4 mr-2"/> 
                                <span>Equipe A depositou: {gameState.last_round_summary.team_A_total}</span>
                            </div>
                            <div className="flex items-center">
                                <Scale className="h-4 w-4 mr-2"/> 
                                <span>Equipe B depositou: {gameState.last_round_summary.team_B_total}</span>
                            </div>
                            <Separator className="my-2"/>
                            <p className="font-semibold">
                                {gameState.last_round_summary.winner === 'draw' ? 'Empate na rodada!' : `Equipe ${gameState.last_round_summary.winner} venceu a rodada!`}
                            </p>
                            {/* Show individual deposits if available */}
                            {gameState.round_player_deposits_revealed && (
                                <div className="mt-2">
                                    <p className="text-xs text-muted-foreground">Depósitos individuais:</p>
                                    <ul className="text-xs text-muted-foreground list-disc list-inside">
                                        {Object.entries(gameState.round_player_deposits_revealed).map(([sid, amount]) => {
                                            const pTeam = gameState.player_to_team[sid];
                                            const pUsername = gameState.teams[pTeam]?.players[sid]?.username ?? 'Desconhecido';
                                            return <li key={sid}>{pUsername} (Equipe {pTeam}): {amount}</li>;
                                        })}
                                    </ul>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                )}

                {/* Finished State */}                
                {gameState.status === 'finished' && gameState.game_winner && (
                    <div className="space-y-4 mt-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={'default'}>
                            <Trophy className="h-4 w-4" />
                            <AlertTitle>
                                Equipe {gameState.game_winner} Venceu!
                            </AlertTitle>
                            <AlertDescription>
                                A Equipe {gameState.game_winner} foi a primeira a alcançar {ROUNDS_TO_WIN_DK} vitórias de rodada.
                            </AlertDescription>
                        </Alert>
                    </div>
                )}
                 {gameState.status === 'finished' && !gameState.game_winner && (
                     <div className="space-y-4 mt-4">
                        <Separator />
                        <h3 className="text-lg font-semibold text-center">Fim de Jogo!</h3>
                        <Alert variant={'default'}>
                            <Users className="h-4 w-4" />
                            <AlertTitle>Empate?</AlertTitle>
                            <AlertDescription>
                                O jogo terminou sem um vencedor claro (possivelmente devido a um limite de rodadas).
                            </AlertDescription>
                        </Alert>
                    </div>
                 )}

            </CardContent>
        </Card>
    );
};

export default JogoDilemaKongComponent;

