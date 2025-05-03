import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSocket } from '../context/SocketContext';
import { Button } from './ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Terminal, Shuffle, CheckCircle, XCircle, HelpCircle, Hourglass } from 'lucide-react';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, DragEndEvent } from '@dnd-kit/core';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, rectSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// --- Types ---
type CardType = number | string; // number or "+", "-", "*", "/"

interface PlayerStateAbrirPassar {
    username: string;
    sid: string;
    // initial_hand is managed separately via update_player_hand_abrir_passar
    built_deck: CardType[] | null;
    shuffles_remaining: number;
    choice: 'abrir' | 'passar' | null;
    calculated_total: number | null;
    is_ready: boolean;
}

interface GameStateAbrirPassar {
    game_type: 'abrir_passar';
    players: { [sid: string]: PlayerStateAbrirPassar };
    status: 'building' | 'choosing' | 'reveal' | 'finished';
    round_results: {
        winner_sid: string | null | 'draw';
        reason: string;
        p1_choice: string; p1_total: number | null; p1_deck: CardType[];
        p2_choice: string; p2_total: number | null; p2_deck: CardType[];
    } | null;
    last_event: string;
}

interface JogoAbrirPassarComponentProps {
    roomCode: string;
    currentUserSid: string;
    initialGameState: GameStateAbrirPassar | null;
}

// --- Sortable Card Component ---
interface SortableCardProps {
    id: string | number; // Needs unique ID for dnd-kit
    card: CardType;
    isOperator: boolean;
}

function SortableCard({ id, card, isOperator }: SortableCardProps) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        cursor: 'grab',
    };

    return (
        <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
            <Badge
                variant={isOperator ? "secondary" : "outline"}
                className="text-lg p-2 m-1 min-w-[40px] flex justify-center items-center select-none"
            >
                {card}
            </Badge>
        </div>
    );
}

// --- Main Component ---
const JogoAbrirPassarComponent: React.FC<JogoAbrirPassarComponentProps> = ({ roomCode, currentUserSid, initialGameState }) => {
    const { socket } = useSocket();
    const [gameState, setGameState] = useState<GameStateAbrirPassar | null>(initialGameState);
    const [myHand, setMyHand] = useState<CardType[]>([]);
    const [deckBuilder, setDeckBuilder] = useState<CardType[]>([]); // Cards currently in the deck builder area
    const [error, setError] = useState<string | null>(null);
    const [info, setInfo] = useState<string | null>(null);

    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    // --- Memoized Values ---
    const myPlayerState = useMemo(() => gameState?.players[currentUserSid], [gameState, currentUserSid]);
    const opponentSid = useMemo(() => Object.keys(gameState?.players ?? {}).find(sid => sid !== currentUserSid), [gameState, currentUserSid]);
    const opponentPlayerState = useMemo(() => opponentSid ? gameState?.players[opponentSid] : undefined, [gameState, opponentSid]);
    const amIReady = myPlayerState?.is_ready ?? false;
    // const opponentIsReady = opponentPlayerState?.is_ready ?? false;
    const myChoice = myPlayerState?.choice;
    // const opponentChoice = opponentPlayerState?.choice;

    // Map card values to unique IDs for dnd-kit
    // const handItems = useMemo(() => myHand.map((card, index) => ({ id: `hand-${index}-${card}`, card })), [myHand]);
    const deckItems = useMemo(() => deckBuilder.map((card, index) => ({ id: `deck-${index}-${card}`, card })), [deckBuilder]);

    // --- Callbacks ---    
    const handleGameStateUpdate = useCallback((newState: GameStateAbrirPassar) => {
        console.log("Received game state update (Abrir/Passar):", newState);
        setGameState(newState);
        setError(null); // Clear error on update
        setInfo(newState.last_event); // Show last event as info
    }, []);

    const handlePlayerHandUpdate = useCallback((data: { hand: CardType[] }) => {
        console.log("Received player hand update (Abrir/Passar):", data.hand);
        setMyHand(data.hand);
        // Initialize deck builder with the hand if not already built
        if (!myPlayerState?.is_ready) {
             setDeckBuilder(data.hand.slice(0, 10)); // Start with first 10 cards
        }
    }, [myPlayerState?.is_ready]);

    const handleDeckShuffled = useCallback((data: { shuffled_deck: CardType[], shuffles_remaining: number }) => {
        console.log("Deck shuffled update:", data);
        setDeckBuilder(data.shuffled_deck);
        // Update local state immediately for responsiveness (backend state will confirm)
        if (gameState) {
            setGameState(prev => prev ? {
                 ...prev,
                 players: {
                     ...prev.players,
                     [currentUserSid]: {
                         ...prev.players[currentUserSid],
                         shuffles_remaining: data.shuffles_remaining
                     }
                 }
             } : null);
        }
        setInfo(`Deck embaralhado! ${data.shuffles_remaining} embaralhamentos restantes.`);
    }, [gameState, currentUserSid]);

    const handleDeckBuiltConfirmation = useCallback((data: { success: boolean }) => {
        if (data.success) {
            setInfo("Deck montado com sucesso!");
            // State update from backend will confirm readiness
        } else {
            setError("Falha ao confirmar a montagem do deck.");
        }
    }, []);

    const handleChoiceConfirmed = useCallback((data: { success: boolean }) => {
        if (data.success) {
            setInfo("Escolha confirmada!");
            // State update from backend will confirm choice
        } else {
            setError("Falha ao confirmar a escolha.");
        }
    }, []);

    const handleError = useCallback((errorData: { message: string }) => {
        console.error("Received game error (Abrir/Passar):", errorData.message);
        setError(errorData.message);
    }, []);

    // --- Effects ---    
    useEffect(() => {
        if (socket) {
            if (!gameState) {
                console.log("Requesting initial game state for Abrir/Passar");
                socket.emit('get_game_state_abrir_passar', { room_code: roomCode, sid: currentUserSid });
            }

            socket.on('update_state_abrir_passar', handleGameStateUpdate);
            socket.on('update_player_hand_abrir_passar', handlePlayerHandUpdate);
            socket.on('deck_shuffled', handleDeckShuffled);
            socket.on('deck_built_confirmation', handleDeckBuiltConfirmation);
            socket.on('choice_confirmed', handleChoiceConfirmed);
            socket.on('error', handleError);

            return () => {
                socket.off('update_state_abrir_passar', handleGameStateUpdate);
                socket.off('update_player_hand_abrir_passar', handlePlayerHandUpdate);
                socket.off('deck_shuffled', handleDeckShuffled);
                socket.off('deck_built_confirmation', handleDeckBuiltConfirmation);
                socket.off('choice_confirmed', handleChoiceConfirmed);
                socket.off('error', handleError);
            };
        } else {
            setError("Erro de conexão com o servidor.");
        }
    }, [socket, roomCode, currentUserSid, gameState, handleGameStateUpdate, handlePlayerHandUpdate, handleDeckShuffled, handleDeckBuiltConfirmation, handleChoiceConfirmed, handleError]);

    // --- Event Handlers ---
    const handleBuildDeck = () => {
        if (socket && gameState && gameState.status === 'building' && !amIReady) {
            if (deckBuilder.length !== 10) {
                setError("Seu deck deve ter exatamente 10 cartas.");
                return;
            }
            console.log("Emitting build_deck_abrir_passar with deck:", deckBuilder);
            socket.emit('build_deck_abrir_passar', {
                room_code: roomCode,
                player_sid: currentUserSid,
                deck: deckBuilder,
            });
            setError(null);
        }
    };

    const handleShuffleDeck = () => {
        if (socket && gameState && gameState.status === 'building' && !amIReady && myPlayerState && myPlayerState.shuffles_remaining > 0) {
             if (deckBuilder.length !== 10) {
                setError("Monte um deck de 10 cartas antes de embaralhar.");
                return;
            }
            console.log("Emitting shuffle_deck_abrir_passar");
            socket.emit('shuffle_deck_abrir_passar', {
                room_code: roomCode,
                player_sid: currentUserSid,
            });
            setError(null);
        }
    };

    const handleChooseAction = (choice: 'abrir' | 'passar') => {
        if (socket && gameState && gameState.status === 'choosing' && !myChoice) {
            console.log(`Emitting choose_action_abrir_passar with choice: ${choice}`);
            socket.emit('choose_action_abrir_passar', {
                room_code: roomCode,
                player_sid: currentUserSid,
                choice: choice,
            });
            setError(null);
        }
    };

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;

        if (over && active.id !== over.id) {
            // Check if moving within deckBuilder
            const activeIndexInDeck = deckItems.findIndex(item => item.id === active.id);
            const overIndexInDeck = deckItems.findIndex(item => item.id === over.id);

            if (activeIndexInDeck !== -1 && overIndexInDeck !== -1) {
                setDeckBuilder((items) => {
                    return arrayMove(items, activeIndexInDeck, overIndexInDeck);
                });
            }
            // Add logic here if allowing dragging between hand and deck (more complex)
        }
    };

    // --- Render Logic ---
    if (!gameState || !myPlayerState) {
        return <div>Carregando estado do Jogo Abrir/Passar...</div>;
    }

    const renderPlayerStatus = (playerState: PlayerStateAbrirPassar | undefined /*, isOpponent: boolean*/) => {
        if (!playerState) return <Badge variant="outline">Aguardando...</Badge>;
        // const name = isOpponent ? 'Oponente' : 'Você';
        if (gameState.status === 'building') {
            return playerState.is_ready ? <Badge variant="default"><CheckCircle className="h-4 w-4 mr-1"/>Pronto</Badge> : <Badge variant="secondary"><Hourglass className="h-4 w-4 mr-1"/>Montando Deck</Badge>;
        }
        if (gameState.status === 'choosing') {
            return playerState.choice ? <Badge variant="default"><CheckCircle className="h-4 w-4 mr-1"/>Escolheu</Badge> : <Badge variant="secondary"><Hourglass className="h-4 w-4 mr-1"/>Escolhendo</Badge>;
        }
        if (gameState.status === 'reveal' || gameState.status === 'finished') {
            if (playerState.choice === 'passar') return <Badge variant="destructive"><XCircle className="h-4 w-4 mr-1"/>Passou</Badge>;
            if (playerState.choice === 'abrir') return <Badge variant="default">Abriu ({playerState.calculated_total ?? '?'})</Badge>;
        }
        return <Badge variant="outline">Aguardando...</Badge>;
    };

    const renderDeck = (deck: CardType[] | null | undefined, title: string, hideContent = false) => (
        <Card className="flex-1 min-w-[200px]">
            <CardHeader>
                <CardTitle className="text-sm">{title}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap justify-center items-center min-h-[50px]">
                {hideContent ? (
                    <Badge variant="outline">?</Badge>
                ) : deck && deck.length > 0 ? (
                    deck.map((card, index) => (
                        <Badge
                            key={index}
                            variant={typeof card === 'string' ? "secondary" : "outline"}
                            className="text-base p-1 m-0.5"
                        >
                            {card}
                        </Badge>
                    ))
                ) : (
                    <span className="text-xs text-muted-foreground">Vazio</span>
                )}
            </CardContent>
        </Card>
    );

    return (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <Card className="w-full max-w-5xl mx-auto">
                <CardHeader>
                    <CardTitle>Jogo Abrir/Passar</CardTitle>
                    <CardDescription>
                        Monte um deck de 10 cartas (da sua mão inicial de 5 números e 5 operadores). Escolha Abrir ou Passar. Quem abrir com o maior total vence!
                        <Badge className="ml-2 capitalize">{gameState.status.replace('_', ' ')}</Badge>
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

                    {/* Player Status Area */}                    
                    <div className="flex justify-around gap-4 mb-4">
                        <div className="text-center">
                            <p className="font-semibold">Você ({myPlayerState.username})</p>
                            {renderPlayerStatus(myPlayerState)}
                        </div>
                        <div className="text-center">
                            <p className="font-semibold">Oponente ({opponentPlayerState?.username ?? '...'})</p>
                            {renderPlayerStatus(opponentPlayerState)}
                        </div>
                    </div>
                    <Separator />

                    {/* Building Phase */}                    
                    {gameState.status === 'building' && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold">Fase de Construção</h3>
                            <Card>
                                <CardHeader><CardTitle className="text-base">Sua Mão Inicial ({myHand.length} cartas)</CardTitle></CardHeader>
                                <CardContent className="flex flex-wrap gap-1">
                                    {myHand.length > 0 ? myHand.map((card, index) => (
                                        <Badge key={index} variant={typeof card === 'string' ? "secondary" : "outline"} className="text-lg p-2">
                                            {card}
                                        </Badge>
                                    )) : <p className="text-sm text-muted-foreground">Recebendo cartas...</p>}
                                </CardContent>
                            </Card>

                            <Card>
                                <CardHeader>
                                    <CardTitle className="text-base">Seu Deck (Arraste para reordenar - {deckBuilder.length}/10 cartas)</CardTitle>
                                    <CardDescription>Construa seu deck de 10 cartas a partir da sua mão inicial. A ordem importa para o cálculo!</CardDescription>
                                </CardHeader>
                                <CardContent className="p-4 border rounded-md min-h-[80px]">
                                    {deckBuilder.length > 0 ? (
                                        <SortableContext items={deckItems.map(item => item.id)} strategy={rectSortingStrategy}>
                                            <div className="flex flex-wrap gap-1">
                                                {deckItems.map(item => (
                                                    <SortableCard key={item.id} id={item.id} card={item.card} isOperator={typeof item.card === 'string'} />
                                                ))}
                                            </div>
                                        </SortableContext>
                                    ) : <p className="text-sm text-muted-foreground">Arraste cartas da mão aqui (funcionalidade de arrastar entre listas não implementada - selecione as 10 cartas desejadas e ordene).</p>}
                                     {/* Placeholder for drag-and-drop source if implemented */}
                                </CardContent>
                            </Card>

                            {!amIReady && (
                                <div className="flex gap-2 justify-center">
                                    <Button
                                        onClick={handleShuffleDeck}
                                        disabled={amIReady || (myPlayerState?.shuffles_remaining ?? 0) <= 0 || deckBuilder.length !== 10}
                                        variant="outline"
                                    >
                                        <Shuffle className="h-4 w-4 mr-2" />
                                        Embaralhar Deck ({myPlayerState?.shuffles_remaining ?? 0} restantes)
                                    </Button>
                                    <Button onClick={handleBuildDeck} disabled={amIReady || deckBuilder.length !== 10}>
                                        <CheckCircle className="h-4 w-4 mr-2" />
                                        Confirmar Deck
                                    </Button>
                                </div>
                            )}
                            {amIReady && <p className="text-center text-green-600 font-semibold">Você está pronto! Aguardando oponente...</p>}
                        </div>
                    )}

                    {/* Choosing Phase */}                    
                    {gameState.status === 'choosing' && (
                        <div className="text-center space-y-4">
                            <h3 className="text-lg font-semibold">Fase de Escolha</h3>
                            <p>Seu deck está montado. Você quer <span className="font-bold">Abrir</span> (revelar e calcular) ou <span className="font-bold">Passar</span>?</p>
                            {renderDeck(myPlayerState.built_deck, "Seu Deck Final", false)}
                            {!myChoice ? (
                                <div className="flex gap-4 justify-center">
                                    <Button onClick={() => handleChooseAction('abrir')} size="lg">Abrir</Button>
                                    <Button onClick={() => handleChooseAction('passar')} variant="destructive" size="lg">Passar</Button>
                                </div>
                            ) : (
                                <p className="text-center text-green-600 font-semibold">Você escolheu {myChoice}! Aguardando oponente...</p>
                            )}
                        </div>
                    )}

                    {/* Reveal / Finished Phase */}                    
                    {(gameState.status === 'reveal' || gameState.status === 'finished') && gameState.round_results && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold text-center">Resultado Final</h3>
                            <Alert variant={gameState.round_results.winner_sid === 'draw' ? 'default' : (gameState.round_results.winner_sid === currentUserSid ? 'default' : 'destructive')}>
                                <Terminal className="h-4 w-4" />
                                <AlertTitle>
                                    {gameState.round_results.winner_sid === 'draw' ? "Empate!" : (gameState.round_results.winner_sid === currentUserSid ? "Você Venceu!" : "Você Perdeu!")}
                                </AlertTitle>
                                <AlertDescription>{gameState.round_results.reason}</AlertDescription>
                            </Alert>

                            <div className="flex flex-col md:flex-row gap-4 justify-around">
                                {/* Your Results */}                                
                                <Card className="flex-1">
                                    <CardHeader>
                                        <CardTitle className="text-base">Você ({myPlayerState.username})</CardTitle>
                                        <CardDescription>Escolha: <Badge variant={myPlayerState.choice === 'abrir' ? 'default' : 'destructive'}>{myPlayerState.choice}</Badge></CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {renderDeck(myPlayerState.built_deck, "Seu Deck", false)}
                                        {myPlayerState.choice === 'abrir' && (
                                            <p className="text-center font-semibold mt-2">Total Calculado: {myPlayerState.calculated_total ?? 'N/A'}</p>
                                        )}
                                    </CardContent>
                                </Card>
                                {/* Opponent Results */}                                
                                <Card className="flex-1">
                                    <CardHeader>
                                        <CardTitle className="text-base">Oponente ({opponentPlayerState?.username ?? '...'})</CardTitle>
                                        <CardDescription>Escolha: <Badge variant={opponentPlayerState?.choice === 'abrir' ? 'default' : 'destructive'}>{opponentPlayerState?.choice ?? '?'}</Badge></CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        {renderDeck(opponentPlayerState?.built_deck, "Deck Oponente", false)} 
                                        {opponentPlayerState?.choice === 'abrir' && (
                                            <p className="text-center font-semibold mt-2">Total Calculado: {opponentPlayerState?.calculated_total ?? 'N/A'}</p>
                                        )}
                                    </CardContent>
                                </Card>
                            </div>
                        </div>
                    )}

                </CardContent>
            </Card>
        </DndContext>
    );
};

export default JogoAbrirPassarComponent;

