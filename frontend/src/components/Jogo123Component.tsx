import React, { useState, useEffect, useCallback } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { Socket } from 'socket.io-client'; // Import Socket type

const GAME_NAME = "Jogo 1-2-3";

interface Jogo123Props {
  roomCode: string | undefined;
  currentUserSid: string; // Added currentUserSid
  userId: number | null; // TODO: Replace userId with currentUserSid if backend uses SID
  socket: Socket | null; // Use the specific Socket type
  initialGameState: any; // Added initialGameState
}

// --- State Interfaces matching Backend --- 
interface PublicPlayerInfo {
    username: string;
    score: number;
    status: string; // e.g., "active", "eliminated"
}

interface PublicDuelInfo {
    player1_id: number;
    player2_id: number;
    status: string; // "waiting_cards", "waiting_p1", "waiting_p2"
}

interface PublicGameState {
    game_name?: string;
    status?: string; // "starting", "in_progress", "finished"
    round?: number;
    players: { [userId: string]: PublicPlayerInfo };
    active_duels?: { [duelId: string]: PublicDuelInfo };
}

interface PendingChallenge {
    challenge_id: string;
    challenger_id?: number; // Present if received
    challenger_username?: string; // Present if received
    challenged_id?: number; // Present if sent
}

interface ActiveDuel {
    duel_id: string;
    opponent_id: number;
    status: string; // "waiting_cards", "waiting_p1", "waiting_p2"
    my_card_played: boolean;
}

interface PendingTrade {
    trade_id: string;
    sender_id?: number; // Present if received
    sender_username?: string; // Present if received
    receiver_id?: number; // Present if sent
    offered_card: number;
    requested_card: number | null;
}

interface PrivatePlayerState {
    hand: number[];
    score: number;
    pending_challenges_sent: PendingChallenge[];
    pending_challenges_received: PendingChallenge[];
    active_duels: ActiveDuel[];
    pending_trades_sent: PendingTrade[];
    pending_trades_received: PendingTrade[];
}

interface DuelResultData {
    duel_id: string;
    your_card: number;
    opponent_card: number;
    winner_id: number | null;
    your_score: number;
}

interface TradeResultData {
    trade_id: string;
    status: string; // "accepted", "rejected"
    reason?: string;
    offered?: number;
    requested?: number | null;
}

interface GameOverData {
    message: string;
    winner_id: number | null;
    loser_id: number | null;
    final_scores: { [userId: string]: number };
}

// --- Component --- 

const Jogo123Component: React.FC<Jogo123Props> = ({ roomCode, userId, socket }) => {
  const { toast } = useToast();
  const [publicState, setPublicState] = useState<PublicGameState | null>(null);
  const [privateState, setPrivateState] = useState<PrivatePlayerState | null>(null);
  
  // UI Interaction State
  const [selectedCard, setSelectedCard] = useState<number | null>(null);
  const [targetPlayerId, setTargetPlayerId] = useState<number | null>(null);
  const [tradeOfferedCard, setTradeOfferedCard] = useState<number | null>(null);
  const [tradeRequestedCard, setTradeRequestedCard] = useState<string>("none"); // 'none' or card number as string
  const [tradeTargetPlayerId, setTradeTargetPlayerId] = useState<number | null>(null);
  const [cardToPlayInDuel, setCardToPlayInDuel] = useState<number | null>(null);

  // --- Event Handlers --- 

  const handlePublicStateUpdate = useCallback((data: PublicGameState) => {
    console.log(`${GAME_NAME} Public State Update:`, data);
    setPublicState(data);
  }, []);

  const handlePrivateStateUpdate = useCallback((data: PrivatePlayerState) => {
    console.log(`${GAME_NAME} Private State Update:`, data);
    setPrivateState(data);
    // Reset selections if hand changes significantly? Maybe not needed.
  }, []);

  const handleGameError = useCallback((data: { message: string }) => {
    console.error(`${GAME_NAME} Error:`, data.message);
    toast({ title: `Erro no ${GAME_NAME}`, description: data.message, variant: "destructive" });
  }, [toast]);

  const handleChallengeReceived = useCallback((data: PendingChallenge) => {
    console.log(`${GAME_NAME} Challenge Received:`, data);
    toast({ 
        title: "Desafio Recebido!", 
        description: `${data.challenger_username || 'Alguém'} desafiou você!`,
        // TODO: Add Accept/Reject actions directly in the toast or rely on UI update
    });
    // State update will handle UI changes via handlePrivateStateUpdate
  }, [toast]);

  const handleChallengeSent = useCallback((data: { challenge_id: string, challenged_id: number }) => {
    console.log(`${GAME_NAME} Challenge Sent:`, data);
    toast({ title: "Desafio Enviado", description: `Você desafiou ${publicState?.players[data.challenged_id.toString()]?.username || 'jogador'}. Aguardando resposta.` });
  }, [toast, publicState]);

  const handleChallengeResult = useCallback((data: { challenge_id: string, status: string, reason?: string }) => {
    console.log(`${GAME_NAME} Challenge Result:`, data);
    if (data.status === 'rejected') {
        toast({ title: "Desafio Recusado", description: `Seu desafio foi recusado. ${data.reason ? `Motivo: ${data.reason}` : ''}` });
    } 
    // 'accepted' is handled by play_card_request
  }, [toast]);

  const handlePlayCardRequest = useCallback((data: { duel_id: string, opponent_id: number }) => {
    console.log(`${GAME_NAME} Play Card Request:`, data);
    const opponentUsername = publicState?.players[data.opponent_id.toString()]?.username || 'oponente';
    toast({ title: "Duelo Aceito!", description: `Jogue uma carta contra ${opponentUsername}.` });
    // UI should now show options to select a card for this duel_id
  }, [toast, publicState]);

  const handleDuelResult = useCallback((data: DuelResultData) => {
    console.log(`${GAME_NAME} Duel Result:`, data);
    let description = `Você jogou ${data.your_card}, oponente jogou ${data.opponent_card}. `;
    if (data.winner_id === null) {
        description += "Empate!";
    } else if (data.winner_id === userId) {
        description += "Você venceu!";
    } else {
        description += "Você perdeu.";
    }
    description += ` Sua pontuação: ${data.your_score}.`;
    toast({ title: "Resultado do Duelo", description });
    setCardToPlayInDuel(null); // Reset card selection for duel
  }, [toast, userId]);

  const handleTradeOfferReceived = useCallback((data: PendingTrade) => {
    console.log(`${GAME_NAME} Trade Offer Received:`, data);
    let description = `${data.sender_username || 'Alguém'} oferece ${data.offered_card}`;
    if (data.requested_card !== null) {
        description += ` em troca de ${data.requested_card}.`;
    } else {
        description += ` (doação).`;
    }
    toast({ title: "Oferta de Troca Recebida", description });
    // UI update handled by private state update
  }, [toast]);

  const handleTradeOfferSent = useCallback((data: { trade_id: string, receiver_id: number }) => {
    console.log(`${GAME_NAME} Trade Offer Sent:`, data);
    toast({ title: "Oferta de Troca Enviada", description: `Oferta enviada para ${publicState?.players[data.receiver_id.toString()]?.username || 'jogador'}. Aguardando resposta.` });
  }, [toast, publicState]);

  const handleTradeResult = useCallback((data: TradeResultData) => {
    console.log(`${GAME_NAME} Trade Result:`, data);
    if (data.status === 'accepted') {
        toast({ title: "Troca Aceita!", description: `Troca ${data.offered} por ${data.requested ?? 'nada'} concluída.` });
    } else {
        toast({ title: "Troca Recusada", description: `Sua oferta de troca foi recusada. ${data.reason ? `Motivo: ${data.reason}` : ''}` });
    }
  }, [toast]);

  const handleGameOver = useCallback((data: GameOverData) => {
    console.log(`${GAME_NAME} Game Over:`, data);
    const winnerUsername = data.winner_id ? publicState?.players[data.winner_id.toString()]?.username : 'Ninguém';
    const loserUsername = data.loser_id ? publicState?.players[data.loser_id.toString()]?.username : 'Ninguém';
    toast({ title: "Fim de Jogo!", description: `${data.message} Vencedor: ${winnerUsername}. Perdedor: ${loserUsername}.`, duration: 10000 });
    // Maybe disable game actions here
  }, [toast, publicState]);

  // --- Socket Effect --- 

  useEffect(() => {
    if (!socket || !roomCode) return;

    console.log(`Setting up ${GAME_NAME} listeners for room ${roomCode}`);
    
    // Register event listeners
    socket.on(`${GAME_NAME}_update_state`, handlePublicStateUpdate);
    socket.on(`${GAME_NAME}_update_private_state`, handlePrivateStateUpdate);
    socket.on(`${GAME_NAME}_challenge_received`, handleChallengeReceived);
    socket.on(`${GAME_NAME}_challenge_sent`, handleChallengeSent);
    socket.on(`${GAME_NAME}_challenge_result`, handleChallengeResult);
    socket.on(`${GAME_NAME}_play_card_request`, handlePlayCardRequest);
    socket.on(`${GAME_NAME}_duel_result`, handleDuelResult);
    socket.on(`${GAME_NAME}_trade_offer_received`, handleTradeOfferReceived);
    socket.on(`${GAME_NAME}_trade_offer_sent`, handleTradeOfferSent);
    socket.on(`${GAME_NAME}_trade_result`, handleTradeResult);
    socket.on(`${GAME_NAME}_game_over`, handleGameOver);
    socket.on(`error`, handleGameError); // Listen to generic errors too

    // Request initial state when component mounts or socket connects
    console.log(`Requesting initial ${GAME_NAME} state for room ${roomCode}`);
    socket.emit(`${GAME_NAME}_get_state`, { room_code: roomCode });

    // Cleanup listeners on component unmount or socket change
    return () => {
      console.log(`Cleaning up ${GAME_NAME} listeners for room ${roomCode}`);
      socket.off(`${GAME_NAME}_update_state`, handlePublicStateUpdate);
      socket.off(`${GAME_NAME}_update_private_state`, handlePrivateStateUpdate);
      socket.off(`${GAME_NAME}_challenge_received`, handleChallengeReceived);
      socket.off(`${GAME_NAME}_challenge_sent`, handleChallengeSent);
      socket.off(`${GAME_NAME}_challenge_result`, handleChallengeResult);
      socket.off(`${GAME_NAME}_play_card_request`, handlePlayCardRequest);
      socket.off(`${GAME_NAME}_duel_result`, handleDuelResult);
      socket.off(`${GAME_NAME}_trade_offer_received`, handleTradeOfferReceived);
      socket.off(`${GAME_NAME}_trade_offer_sent`, handleTradeOfferSent);
      socket.off(`${GAME_NAME}_trade_result`, handleTradeResult);
      socket.off(`${GAME_NAME}_game_over`, handleGameOver);
      socket.off(`error`, handleGameError);
    };
  }, [socket, roomCode, handlePublicStateUpdate, handlePrivateStateUpdate, handleGameError, 
      handleChallengeReceived, handleChallengeSent, handleChallengeResult, handlePlayCardRequest, 
      handleDuelResult, handleTradeOfferReceived, handleTradeOfferSent, handleTradeResult, handleGameOver]);

  // --- Action Functions --- 

  const emitGameAction = (eventName: string, payload: object) => {
      if (!socket || !roomCode || !userId) {
          toast({ title: "Erro", description: "Não conectado ou informações ausentes.", variant: "destructive" });
          return;
      }
      console.log(`Emitting ${eventName}:`, payload);
      socket.emit(eventName, { ...payload, room_code: roomCode, user_id: userId }); // Add common fields
  };

  const handleChallengeClick = () => {
    if (targetPlayerId === null) {
      toast({ title: "Ação Inválida", description: "Selecione um jogador para desafiar.", variant: "destructive" });
      return;
    }
    if (!userId) return;

    emitGameAction(`${GAME_NAME}_challenge_player`, {
      challenger_id: userId,
      challenged_id: targetPlayerId,
    });
    setTargetPlayerId(null); // Reset selection
  };

  const handleRespondChallenge = (challengeId: string, response: 'accept' | 'reject') => {
      emitGameAction(`${GAME_NAME}_respond_challenge`, {
          challenge_id: challengeId,
          response: response,
      });
  };

  const handlePlayCardInDuel = (duelId: string) => {
      if (cardToPlayInDuel === null) {
          toast({ title: "Ação Inválida", description: "Selecione uma carta para jogar no duelo.", variant: "destructive" });
          return;
      }
      if (!userId) return;
      
      emitGameAction(`${GAME_NAME}_play_card`, {
          duel_id: duelId,
          player_id: userId,
          card_value: cardToPlayInDuel,
      });
      // State update will clear the duel from active_duels upon completion
      setCardToPlayInDuel(null); 
  };

  const handleOfferTrade = () => {
      if (tradeTargetPlayerId === null || tradeOfferedCard === null) {
          toast({ title: "Ação Inválida", description: "Selecione um jogador, uma carta para oferecer.", variant: "destructive" });
          return;
      }
      if (!userId) return;

      const requested = tradeRequestedCard === 'none' ? null : parseInt(tradeRequestedCard, 10);

      emitGameAction(`${GAME_NAME}_offer_trade`, {
          sender_id: userId,
          receiver_id: tradeTargetPlayerId,
          offered_card: tradeOfferedCard,
          requested_card: requested,
      });
      // Reset trade UI state
      setTradeTargetPlayerId(null);
      setTradeOfferedCard(null);
      setTradeRequestedCard("none");
  };
  
  const handleRespondTrade = (tradeId: string, response: 'accept' | 'reject') => {
      emitGameAction(`${GAME_NAME}_respond_trade`, {
          trade_id: tradeId,
          response: response,
      });
  };

  // --- Render Logic --- 

  if (!publicState || !privateState) {
    return <p>Carregando estado do {GAME_NAME}...</p>;
  }

  // const myPlayerIdStr = userId?.toString();
  // const myPublicInfo = myPlayerIdStr ? publicState.players[myPlayerIdStr] : null;
  const gameStatus = publicState.status;
  const isGameActive = gameStatus === 'in_progress';

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{GAME_NAME} (Sua Pontuação: {privateState.score})</CardTitle>
        <CardDescription>Status: {gameStatus}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* My Hand */}
        <div>
          <h3 className="font-semibold mb-2">Sua Mão ({privateState.hand.length} cartas):</h3>
          <div className="flex flex-wrap gap-2">
            {privateState.hand.map((card, index) => (
              <Button
                key={`${card}-${index}`}
                variant={selectedCard === card ? "default" : "outline"}
                onClick={() => setSelectedCard(card)}
                disabled={!isGameActive}
                size="sm"
              >
                {card}
              </Button>
            ))}
          </div>
        </div>

        {/* Player List & Actions */}
        <div>
            <h3 className="font-semibold mb-2">Jogadores:</h3>
            <ul className="space-y-1">
                {Object.entries(publicState.players).map(([pidStr, player]) => {
                    const pid = parseInt(pidStr, 10);
                    const isSelf = pid === userId;
                    const isTarget = pid === targetPlayerId;
                    return (
                        <li key={pid} className={`flex items-center justify-between p-2 rounded ${isTarget ? "bg-yellow-100" : ""}`}>
                            <span>
                                {player.username} ({player.score} pts) {isSelf ? '(Você)' : ''} [{player.status}]
                            </span>
                            {!isSelf && isGameActive && (
                                <Button 
                                    variant="outline" 
                                    size="sm"
                                    onClick={() => setTargetPlayerId(pid)}
                                    disabled={targetPlayerId === pid}
                                >
                                    Selecionar
                                </Button>
                            )}
                        </li>
                    );
                })}
            </ul>
            {targetPlayerId && isGameActive && (
                 <Button onClick={handleChallengeClick} className="mt-2" size="sm">
                    Desafiar {publicState.players[targetPlayerId.toString()]?.username}
                 </Button>
            )}
        </div>

        {/* Pending Challenges Received */}
        {privateState.pending_challenges_received.length > 0 && (
            <div>
                <h3 className="font-semibold mb-2 text-orange-600">Desafios Recebidos:</h3>
                <ul className="space-y-2">
                    {privateState.pending_challenges_received.map(challenge => (
                        <li key={challenge.challenge_id} className="flex items-center justify-between p-2 border rounded">
                            <span>Desafio de: {challenge.challenger_username}</span>
                            <div className="flex gap-2">
                                <Button variant="default" size="sm" onClick={() => handleRespondChallenge(challenge.challenge_id, 'accept')} disabled={!isGameActive}>Aceitar</Button>
                                <Button variant="destructive" size="sm" onClick={() => handleRespondChallenge(challenge.challenge_id, 'reject')} disabled={!isGameActive}>Recusar</Button>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        )}

        {/* Active Duels */}
        {privateState.active_duels.length > 0 && (
            <div>
                <h3 className="font-semibold mb-2 text-red-600">Duelos Ativos:</h3>
                <ul className="space-y-2">
                    {privateState.active_duels.map(duel => (
                        <li key={duel.duel_id} className="p-2 border rounded">
                            <span>Duelo com: {publicState.players[duel.opponent_id.toString()]?.username} (Status: {duel.status})</span>
                            {duel.status === 'waiting_cards' || (duel.status === 'waiting_p1' && userId === publicState.active_duels?.[duel.duel_id]?.player1_id) || (duel.status === 'waiting_p2' && userId === publicState.active_duels?.[duel.duel_id]?.player2_id) ? (
                                !duel.my_card_played ? (
                                    <div className="mt-2 space-y-2">
                                        <Label>Selecione sua carta para o duelo:</Label>
                                        <div className="flex flex-wrap gap-2">
                                            {privateState.hand.map((card, index) => (
                                                <Button
                                                    key={`${card}-${index}-duel`}
                                                    variant={cardToPlayInDuel === card ? "destructive" : "outline"}
                                                    onClick={() => setCardToPlayInDuel(card)}
                                                    size="sm"
                                                >
                                                    {card}
                                                </Button>
                                            ))}
                                        </div>
                                        <Button onClick={() => handlePlayCardInDuel(duel.duel_id)} disabled={cardToPlayInDuel === null || !isGameActive} size="sm">Jogar Carta</Button>
                                    </div>
                                ) : (
                                    <p className="text-sm text-gray-500 mt-1">Aguardando oponente jogar...</p>
                                )
                            ) : null}
                        </li>
                    ))}
                </ul>
            </div>
        )}
        
        {/* Trade Offers */}
        {isGameActive && (
             <Dialog>
                <DialogTrigger asChild>
                    <Button variant="outline" className="mt-4">Oferecer Troca</Button>
                </DialogTrigger>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Oferecer Troca</DialogTitle>
                        <DialogDescription>Selecione o jogador, a carta a oferecer e a carta desejada (opcional).</DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4 py-4">
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="trade-player" className="text-right">Jogador</Label>
                            <Select onValueChange={(value) => setTradeTargetPlayerId(parseInt(value, 10))} value={tradeTargetPlayerId?.toString()}>
                                <SelectTrigger className="col-span-3">
                                    <SelectValue placeholder="Selecione um jogador" />
                                </SelectTrigger>
                                <SelectContent>
                                    {Object.entries(publicState.players)
                                        .filter(([pidStr]) => parseInt(pidStr, 10) !== userId)
                                        .map(([pidStr, player]) => (
                                            <SelectItem key={pidStr} value={pidStr}>{player.username}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="trade-offer" className="text-right">Oferecer</Label>
                             <Select onValueChange={(value) => setTradeOfferedCard(parseInt(value, 10))} value={tradeOfferedCard?.toString()}>
                                <SelectTrigger className="col-span-3">
                                    <SelectValue placeholder="Sua carta" />
                                </SelectTrigger>
                                <SelectContent>
                                    {privateState.hand.map((card, index) => (
                                        <SelectItem key={`${card}-${index}-offer`} value={card.toString()}>{card}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-4 items-center gap-4">
                            <Label htmlFor="trade-request" className="text-right">Pedir</Label>
                             <Select onValueChange={setTradeRequestedCard} value={tradeRequestedCard}>
                                <SelectTrigger className="col-span-3">
                                    <SelectValue placeholder="Carta desejada" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="none">Nada (Doação)</SelectItem>
                                    <SelectItem value="1">1</SelectItem>
                                    <SelectItem value="2">2</SelectItem>
                                    <SelectItem value="3">3</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button onClick={handleOfferTrade} disabled={!tradeTargetPlayerId || tradeOfferedCard === null}>Enviar Oferta</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        )}

        {/* Pending Trades Received */}
        {privateState.pending_trades_received.length > 0 && (
            <div className="mt-4">
                <h3 className="font-semibold mb-2 text-blue-600">Ofertas de Troca Recebidas:</h3>
                <ul className="space-y-2">
                    {privateState.pending_trades_received.map(trade => (
                        <li key={trade.trade_id} className="flex items-center justify-between p-2 border rounded">
                            <span>
                                {trade.sender_username} oferece {trade.offered_card} 
                                {trade.requested_card !== null ? ` por ${trade.requested_card}` : ' (Doação)'}
                            </span>
                            <div className="flex gap-2">
                                <Button variant="default" size="sm" onClick={() => handleRespondTrade(trade.trade_id, 'accept')} disabled={!isGameActive}>Aceitar</Button>
                                <Button variant="destructive" size="sm" onClick={() => handleRespondTrade(trade.trade_id, 'reject')} disabled={!isGameActive}>Recusar</Button>
                            </div>
                        </li>
                    ))}
                </ul>
            </div>
        )}

      </CardContent>
      {/* Optional Footer for game log or global actions */}
      {/* <CardFooter>
          <p>Game Log Placeholder</p>
      </CardFooter> */}
    </Card>
  );
};

export default Jogo123Component;

