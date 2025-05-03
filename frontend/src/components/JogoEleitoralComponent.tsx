import React, { useState, useEffect, useCallback } from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";


import { useToast } from "@/hooks/use-toast";
import { Socket } from 'socket.io-client';
import Countdown from 'react-countdown';

const GAME_NAME = "Jogo Eleitoral";

interface JogoEleitoralProps {
  roomCode: string | undefined;
  currentUserSid: string; // Added currentUserSid
  userId: number | null; // TODO: Replace userId with currentUserSid if backend uses SID
  socket: Socket | null;
  initialGameState: any; // Added initialGameState
}

// --- State Interfaces matching Backend --- 
interface PublicPlayerInfo {
    username: string;
    status: string; // "active", "withdrawn", "eliminated"
    is_candidate: boolean;
    // Chips are private
}

interface PollResult {
    time: string;
    results: { [candidateId: string]: number }; // candidate_id: vote_count
}

interface PublicGameState {
    game_name?: string;
    status?: string; // "declaration", "campaigning", "voting", "finished"
    start_time?: string;
    declaration_end_time?: string;
    voting_end_time?: string;
    next_poll_time?: string;
    candidates: number[]; // List of player_ids
    voters: number[]; // List of player_ids
    polls: PollResult[];
    players: { [userId: string]: PublicPlayerInfo };
    winner_id?: number | null;
    loser_id?: number | null;
    final_votes?: { [voterId: string]: number }; // voter_id: candidate_id
    final_scores?: { [candidateId: string]: number }; // candidate_id: final_score (grenades)
}

interface PrivatePlayerState {
    chips: number;
    my_vote?: number | null; // Candidate ID voted for
    is_candidate: boolean;
    can_declare: boolean;
    // Add other relevant private info if needed
}

// --- Component --- 

const JogoEleitoralComponent: React.FC<JogoEleitoralProps> = ({ roomCode, userId, socket }) => {
  const { toast } = useToast();
  const [publicState, setPublicState] = useState<PublicGameState | null>(null);
  const [privateState, setPrivateState] = useState<PrivatePlayerState | null>(null);
  
  // UI Interaction State
  const [giveChipsAmount, setGiveChipsAmount] = useState<number>(1);
  const [giveChipsTargetVoterId, setGiveChipsTargetVoterId] = useState<number | null>(null);
  const [voteCandidateId, setVoteCandidateId] = useState<number | null>(null);

  // --- Event Handlers --- 

  const handlePublicStateUpdate = useCallback((data: PublicGameState) => {
    console.log(`${GAME_NAME} Public State Update:`, data);
    setPublicState(data);
  }, []);

  const handlePrivateStateUpdate = useCallback((data: PrivatePlayerState) => {
    console.log(`${GAME_NAME} Private State Update:`, data);
    setPrivateState(data);
  }, []);

  const handleGameError = useCallback((data: { message: string }) => {
    console.error(`${GAME_NAME} Error:`, data.message);
    toast({ title: `Erro no ${GAME_NAME}`, description: data.message, variant: "destructive" });
  }, [toast]);

  const handleCandidacyDeclared = useCallback((data: { player_id: number }) => {
      const username = publicState?.players[data.player_id.toString()]?.username || 'Jogador';
      if (data.player_id === userId) {
          toast({ title: "Candidatura Declarada", description: "Você agora é um candidato!" });
      } else {
          toast({ title: "Novo Candidato", description: `${username} declarou candidatura.` });
      }
      // State update handles UI changes
  }, [toast, userId, publicState]);

  const handleWithdrawal = useCallback((data: { player_id: number }) => {
      const username = publicState?.players[data.player_id.toString()]?.username || 'Candidato';
      toast({ title: "Candidato Desistiu", description: `${username} retirou sua candidatura.` });
      // State update handles UI changes
  }, [toast, publicState]);

  const handlePollResults = useCallback((_data: { poll: PollResult }) => {
      toast({ title: "Nova Pesquisa de Opinião", description: "Resultados disponíveis." });
      // State update handles UI changes
  }, [toast]);

  const handleVoteCast = useCallback((data: { voter_id: number, candidate_id: number }) => {
      if (data.voter_id === userId) {
          const candidateName = publicState?.players[data.candidate_id.toString()]?.username || 'Candidato';
          toast({ title: "Voto Confirmado", description: `Você votou em ${candidateName}.` });
      }
      // No public toast for other votes to keep them secret until the end
  }, [toast, userId, publicState]);

  const handleGameOver = useCallback((data: PublicGameState) => { // Assuming game over sends the final public state
    console.log(`${GAME_NAME} Game Over:`, data);
    const winnerUsername = data.winner_id ? data.players[data.winner_id.toString()]?.username : 'Ninguém';
    const loserUsername = data.loser_id ? data.players[data.loser_id.toString()]?.username : 'Ninguém';
    let description = `Vencedor: ${winnerUsername}. Candidato à Partida da Morte: ${loserUsername}.`;
    if (data.final_scores) {
        description += " Granadas (Ex-Fichas): " + Object.entries(data.final_scores).map(([cid, score]) => `${data.players[cid]?.username}: ${score}`).join(', ');
    }
    toast({ title: "Fim da Eleição!", description, duration: 15000 });
  }, [toast]);

  // --- Socket Effect --- 

  useEffect(() => {
    if (!socket || !roomCode) return;

    console.log(`Setting up ${GAME_NAME} listeners for room ${roomCode}`);
    
    socket.on(`${GAME_NAME}_update_state`, handlePublicStateUpdate);
    socket.on(`${GAME_NAME}_update_private_state`, handlePrivateStateUpdate);
    socket.on(`${GAME_NAME}_candidacy_declared`, handleCandidacyDeclared);
    socket.on(`${GAME_NAME}_withdrawal_confirmed`, handleWithdrawal); // Assuming this event name
    socket.on(`${GAME_NAME}_poll_results`, handlePollResults); // Assuming this event name
    socket.on(`${GAME_NAME}_vote_cast`, handleVoteCast);
    socket.on(`${GAME_NAME}_game_over`, handleGameOver); // Assuming game over sends final state
    socket.on(`error`, handleGameError);

    console.log(`Requesting initial ${GAME_NAME} state for room ${roomCode}`);
    socket.emit(`${GAME_NAME}_get_state`, { room_code: roomCode });

    return () => {
      console.log(`Cleaning up ${GAME_NAME} listeners for room ${roomCode}`);
      socket.off(`${GAME_NAME}_update_state`, handlePublicStateUpdate);
      socket.off(`${GAME_NAME}_update_private_state`, handlePrivateStateUpdate);
      socket.off(`${GAME_NAME}_candidacy_declared`, handleCandidacyDeclared);
      socket.off(`${GAME_NAME}_withdrawal_confirmed`, handleWithdrawal);
      socket.off(`${GAME_NAME}_poll_results`, handlePollResults);
      socket.off(`${GAME_NAME}_vote_cast`, handleVoteCast);
      socket.off(`${GAME_NAME}_game_over`, handleGameOver);
      socket.off(`error`, handleGameError);
    };
  }, [socket, roomCode, handlePublicStateUpdate, handlePrivateStateUpdate, handleGameError, 
      handleCandidacyDeclared, handleWithdrawal, handlePollResults, handleVoteCast, handleGameOver]);

  // --- Action Functions --- 

  const emitGameAction = (eventName: string, payload: object) => {
      if (!socket || !roomCode || !userId) {
          toast({ title: "Erro", description: "Não conectado ou informações ausentes.", variant: "destructive" });
          return;
      }
      console.log(`Emitting ${eventName}:`, payload);
      socket.emit(eventName, { ...payload, room_code: roomCode, user_id: userId });
  };

  const handleDeclareCandidacy = () => {
      emitGameAction(`${GAME_NAME}_declare_candidacy`, {});
  };

  const handleWithdrawCandidacy = () => {
      // Add confirmation dialog?
      emitGameAction(`${GAME_NAME}_withdraw_candidacy`, {});
  };

  const handleGiveChips = () => {
      if (giveChipsTargetVoterId === null || giveChipsAmount <= 0) {
          toast({ title: "Ação Inválida", description: "Selecione um eleitor e uma quantidade válida de fichas.", variant: "destructive" });
          return;
      }
      if (!privateState || privateState.chips < giveChipsAmount) {
           toast({ title: "Fichas Insuficientes", description: "Você não tem fichas suficientes.", variant: "destructive" });
           return;
      }
      emitGameAction(`${GAME_NAME}_give_chips`, {
          receiver_id: giveChipsTargetVoterId,
          amount: giveChipsAmount
      });
      // Reset UI
      setGiveChipsTargetVoterId(null);
      setGiveChipsAmount(1);
  };

  const handleCastVote = () => {
      if (voteCandidateId === null) {
          toast({ title: "Ação Inválida", description: "Selecione um candidato para votar.", variant: "destructive" });
          return;
      }
      emitGameAction(`${GAME_NAME}_cast_vote`, {
          candidate_id: voteCandidateId
      });
  };

  // --- Render Logic --- 

  const renderCountdown = (isoTimestamp: string | undefined, prefix: string) => {
      if (!isoTimestamp) return null;
      const targetDate = new Date(isoTimestamp);
      if (targetDate <= new Date()) return <span className="text-gray-500">{prefix} encerrado</span>;
      return (
          <Countdown date={targetDate} renderer={({ minutes, seconds }) => (
              <span className="text-sm font-medium">{prefix}: {minutes}:{seconds < 10 ? `0${seconds}` : seconds}</span>
          )} />
      );
  };

  if (!publicState || !privateState) {
    return <p>Carregando estado do {GAME_NAME}...</p>;
  }

  const myPlayerIdStr = userId?.toString();
  const myPublicInfo = myPlayerIdStr ? publicState.players[myPlayerIdStr] : null;
  const gameStatus = publicState.status;
  const isGameActive = gameStatus !== 'finished' && gameStatus !== 'loading';
  const isDeclarationPhase = gameStatus === 'declaration';
  const isCampaigningPhase = gameStatus === 'campaigning';
  const isVotingPhase = gameStatus === 'voting'; // Assuming backend adds this status
  const isFinished = gameStatus === 'finished';

  const candidates = publicState.candidates.map(cid => ({ id: cid, ...publicState.players[cid.toString()] })).filter(c => c.status === 'active'); // Filter out withdrawn candidates
  const voters = publicState.voters.map(vid => ({ id: vid, ...publicState.players[vid.toString()] }));

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{GAME_NAME}</CardTitle>
        <CardDescription className="flex justify-between items-center">
            <span>Status: {gameStatus}</span>
            {isDeclarationPhase && renderCountdown(publicState.declaration_end_time, "Fim Declaração")}
            {(isCampaigningPhase || isVotingPhase) && renderCountdown(publicState.voting_end_time, "Fim Votação")}
            {/* TODO: Show next poll time? */}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Player Info & Candidacy Actions */} 
        {myPublicInfo && (
            <div className="p-2 border rounded bg-blue-50">
                <p>Você: {myPublicInfo.username} [{myPublicInfo.status}]</p>
                {privateState.is_candidate && <p>Fichas: {privateState.chips}</p>}
                {isDeclarationPhase && privateState.can_declare && (
                    <Button onClick={handleDeclareCandidacy} size="sm" className="mt-1">Declarar Candidatura</Button>
                )}
                {privateState.is_candidate && isGameActive && !isFinished && (
                    <Button onClick={handleWithdrawCandidacy} variant="destructive" size="sm" className="mt-1 ml-2">Desistir da Candidatura</Button>
                )}
            </div>
        )}

        {/* Candidate List */} 
        <div>
            <h3 className="font-semibold mb-2">Candidatos Ativos:</h3>
            {candidates.length > 0 ? (
                <ul className="space-y-1">
                    {candidates.map(candidate => (
                        <li key={candidate.id} className="p-1 border rounded">
                            {candidate.username}
                        </li>
                    ))}
                </ul>
            ) : (
                <p className="text-gray-500">Nenhum candidato ativo.</p>
            )}
        </div>

        {/* Voter Actions (Give Chips / Cast Vote) */} 
        {(isCampaigningPhase || isVotingPhase) && (
            <div>
                <h3 className="font-semibold mb-2">Eleitores:</h3>
                <ul className="space-y-1 mb-4">
                    {voters.map(voter => (
                        <li key={voter.id} className={`flex items-center justify-between p-2 rounded ${giveChipsTargetVoterId === voter.id ? 'bg-yellow-100' : ''}`}>
                            <span>{voter.username} {voter.id === userId ? '(Você)' : ''}</span>
                            {privateState.is_candidate && voter.id !== userId && (
                                <Button 
                                    variant="outline" 
                                    size="sm"
                                    onClick={() => setGiveChipsTargetVoterId(voter.id)}
                                    disabled={giveChipsTargetVoterId === voter.id}
                                >
                                    Selecionar p/ Fichas
                                </Button>
                            )}
                        </li>
                    ))}
                </ul>

                {/* Give Chips UI (for Candidates) */} 
                {privateState.is_candidate && giveChipsTargetVoterId && (
                    <div className="p-3 border rounded bg-green-50 space-y-2">
                        <Label>Dar fichas para: {publicState.players[giveChipsTargetVoterId.toString()]?.username}</Label>
                        <div className="flex items-center gap-2">
                            <Input 
                                type="number"
                                value={giveChipsAmount}
                                onChange={(e) => setGiveChipsAmount(Math.max(1, parseInt(e.target.value) || 1))}
                                min="1"
                                max={privateState.chips}
                                className="w-20"
                            />
                            <Button onClick={handleGiveChips} size="sm">Dar Fichas</Button>
                            <Button variant="ghost" size="sm" onClick={() => setGiveChipsTargetVoterId(null)}>Cancelar</Button>
                        </div>
                    </div>
                )}

                {/* Voting UI (for Voters) */} 
                {!privateState.is_candidate && isVotingPhase && !privateState.my_vote && (
                     <div className="p-3 border rounded bg-purple-50 space-y-2">
                        <Label>Seu Voto:</Label>
                        <Select onValueChange={(value) => setVoteCandidateId(parseInt(value, 10))} value={voteCandidateId?.toString()}>
                            <SelectTrigger>
                                <SelectValue placeholder="Selecione um candidato" />
                            </SelectTrigger>
                            <SelectContent>
                                {candidates.map(candidate => (
                                    <SelectItem key={candidate.id} value={candidate.id.toString()}>{candidate.username}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Button onClick={handleCastVote} disabled={voteCandidateId === null} size="sm">Confirmar Voto</Button>
                    </div>
                )}
                {privateState.my_vote && (
                    <p className="text-green-700 font-medium mt-2">Você votou em: {publicState.players[privateState.my_vote.toString()]?.username}</p>
                )}
            </div>
        )}

        {/* Poll Results */} 
        {publicState.polls.length > 0 && (
            <div>
                <h3 className="font-semibold mb-2">Pesquisas de Opinião:</h3>
                {publicState.polls.map((poll, index) => (
                    <div key={index} className="mb-3 p-2 border rounded">
                        <p className="text-sm font-medium mb-1">Pesquisa {index + 1} ({new Date(poll.time).toLocaleTimeString()})</p>
                        <ul className="text-sm">
                            {Object.entries(poll.results).map(([cid, votes]) => (
                                <li key={cid}>{publicState.players[cid]?.username}: {votes} votos</li>
                            ))}
                        </ul>
                    </div>
                ))}
            </div>
        )}

        {/* Final Results */} 
        {isFinished && (
            <div className="p-3 border rounded bg-gray-100">
                <h3 className="font-semibold mb-2">Resultado Final</h3>
                <p>Vencedor: {publicState.winner_id ? publicState.players[publicState.winner_id.toString()]?.username : 'N/A'}</p>
                <p>Candidato à Partida da Morte: {publicState.loser_id ? publicState.players[publicState.loser_id.toString()]?.username : 'N/A'}</p>
                {publicState.final_scores && (
                    <div className="mt-2">
                        <p className="font-medium">Granadas (Ex-Fichas):</p>
                        <ul>
                            {Object.entries(publicState.final_scores).map(([cid, score]) => (
                                <li key={cid}>{publicState.players[cid]?.username}: {score}</li>
                            ))}
                        </ul>
                    </div>
                )}
                 {/* Optionally show final vote counts if desired */}
            </div>
        )}

      </CardContent>
    </Card>
  );
};

export default JogoEleitoralComponent;

