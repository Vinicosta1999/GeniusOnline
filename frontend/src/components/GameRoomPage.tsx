import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import { useSocket } from '@/context/SocketContext';

// Import existing and new game components
import Jogo123Component from './Jogo123Component';
import JogoEleitoralComponent from './JogoEleitoralComponent';
import Jogo55Component from './Jogo55Component'; // Added
import JogoAbrirPassarComponent from './JogoAbrirPassarComponent'; // Added
import JogoAbundanciaFomeComponent from './JogoAbundanciaFomeComponent'; // Added
import JogoCorridaCavalosConfinadosComponent from './JogoCorridaCavalosConfinadosComponent'; // Added
import JogoCorridaCavalosGolpistasComponent from './JogoCorridaCavalosGolpistasComponent'; // Added
import JogoDilemaKongComponent from './JogoDilemaKongComponent'; // Added
// Import other game components as they are created...
// import JogoZumbiComponent from './JogoZumbiComponent';
// import JogoPegueLadraoComponent from './JogoPegueLadraoComponent';
// import JogoLeilaoExpressaoComponent from './JogoLeilaoExpressaoComponent';
// import JogoFinalComponent from './JogoFinalComponent';

interface Player {
  user_id: number;
  username: string;
  sid: string; // Add SID for easier identification
}

interface Message {
  username: string;
  message: string;
}

// Define a type for the game state shared structure (if possible)
// This helps in handling generic updates, but might be complex
/*
interface BaseGameState {
    game_type: string;
    // Add other common fields if they exist across all games
}
*/

const GameRoomPage = () => {
  const { roomCode } = useParams<{ roomCode: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { socket, isConnected, sid: currentUserSid } = useSocket(); // Get SID from context

  const [players, setPlayers] = useState<Player[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [newMessage, setNewMessage] = useState("");
  // const [username, setUsername] = useState<string | null>(null); // Re-enabled
  const [userId, setUserId] = useState<number | null>(null); // Re-enabled
  // const [userId, setUserId] = useState<number | null>(null); // Using SID from context now
  const [hostSid, setHostSid] = useState<string | null>(null); // Store host SID
  const [currentGameType, setCurrentGameType] = useState<string | null>(null); // Track game type from backend state (e.g., 'jogo_123', 'abundancia_fome')
  const [currentGameInitialState, setCurrentGameInitialState] = useState<any | null>(null); // Store initial state for the current game

  // --- Game List (Match backend event names/types) ---
  // Ensure these names match the `game_type` identifier used in the backend state
  // and correspond to the start event names (e.g., start_jogo_123_game -> jogo_123)
  const gameList = [
      { name: "Jogo 1-2-3", type: "jogo_123" },
      { name: "Jogo Eleitoral", type: "jogo_eleitoral" },
      { name: "Jogo 5:5", type: "5_5" },
      { name: "Abrir, Passar", type: "abrir_passar" },
      { name: "Abundância e Fome", type: "abundancia_fome" },
      { name: "Corrida de Cavalos Confinados", type: "corrida_cavalos_confinados" },
      { name: "Corrida de Cavalos Golpistas", type: "corrida_cavalos_golpistas" },
      { name: "O Dilema de Kong", type: "dilema_kong" },
      // Add other games as implemented
      // { name: "Jogo de Zumbi", type: "jogo_zumbi" },
      // { name: "Pegue o Ladrão", type: "jogo_pegue_ladrao" },
      // { name: "Leilão de Expressão", type: "jogo_leilao_expressao" },
      // { name: "A Final", type: "jogo_final" },
  ];

  // --- Event Handlers ---
  const handlePlayerJoined = useCallback((data: Player) => {
    console.log("Player joined:", data);
    setPlayers((prevPlayers) => [...prevPlayers, data]);
    toast({ title: "Novo Jogador", description: `${data.username} entrou na sala.` });
  }, [toast]);

  const handlePlayerLeft = useCallback((data: { sid: string; username: string }) => {
    console.log("Player left:", data);
    setPlayers((prevPlayers) => prevPlayers.filter((p) => p.sid !== data.sid));
    toast({ title: "Jogador Saiu", description: `${data.username} saiu da sala.` });
  }, [toast]);

  const handleRoomStatus = useCallback((data: { room_code: string; players: Player[]; host_sid: string; current_game_type?: string | null }) => {
    console.log("Room status:", data);
    if (data.room_code === roomCode) {
      setPlayers(data.players);
      setHostSid(data.host_sid);
      // Set the current game based on room status
      if (data.current_game_type && data.current_game_type !== currentGameType) {
          console.log("Setting current game from room status:", data.current_game_type);
          setCurrentGameType(data.current_game_type);
          setCurrentGameInitialState(null); // Reset initial state, game component will request it
      }
    }
  }, [roomCode, currentGameType]);

  const handleChatMessage = useCallback((data: Message) => {
    console.log("Chat message:", data);
    setMessages((prevMessages) => [...prevMessages, data]);
  }, []);

  const handleError = useCallback((data: { message: string }) => {
    console.error("Socket Error:", data.message);
    toast({ title: "Erro", description: data.message, variant: "destructive" });
  }, [toast]);

  // Handler for when a game starts
  const handleGameStarted = useCallback((data: { game_type: string; initial_state: any }) => {
      console.log(`Game started event received: ${data.game_type}`, data.initial_state);
      if (data.game_type !== currentGameType) {
          setCurrentGameType(data.game_type);
          setCurrentGameInitialState(data.initial_state); // Store initial state
          const gameDetails = gameList.find(g => g.type === data.game_type);
          toast({ title: "Jogo Iniciado", description: `O jogo ${gameDetails?.name ?? data.game_type} começou!` });
      }
  }, [currentGameType, toast]);

  // --- Effects ---
  useEffect(() => {
    // const storedUsername = localStorage.getItem("username");
    const storedUserId = localStorage.getItem("userId"); // Re-enabled
    // if (storedUsername) setUsername(storedUsername); // Re-enabled call
    if (storedUserId) setUserId(parseInt(storedUserId, 10)); // Re-enabled call

    if (!socket || !isConnected) {
      toast({ title: "Erro de Conexão", description: "Socket não conectado. Tentando reconectar...", variant: "destructive" });
      // Don't navigate immediately, allow reconnection attempts
      // navigate('/');
      return;
    }

    if (!currentUserSid) {
        console.warn("Current user SID not available yet.");
        return; // Wait for SID
    }

    console.log("Socket connected, SID:", currentUserSid, "Requesting room status for", roomCode);
    socket.emit('get_room_status', { room_code: roomCode, sid: currentUserSid });

    // Register base event listeners
    socket.on('player_joined', handlePlayerJoined);
    socket.on('player_left', handlePlayerLeft);
    socket.on('room_status', handleRoomStatus);
    socket.on('chat_message', handleChatMessage);
    socket.on('error', handleError);
    socket.on('game_started', handleGameStarted); // Listen for the generic game start event

    // Cleanup listeners on component unmount
    return () => {
      console.log("Cleaning up GameRoomPage listeners for", roomCode);
      socket.off('player_joined', handlePlayerJoined);
      socket.off('player_left', handlePlayerLeft);
      socket.off('room_status', handleRoomStatus);
      socket.off('chat_message', handleChatMessage);
      socket.off('error', handleError);
      socket.off('game_started', handleGameStarted);
    };
  }, [socket, isConnected, currentUserSid, roomCode, navigate, toast, handlePlayerJoined, handlePlayerLeft, handleRoomStatus, handleChatMessage, handleError, handleGameStarted]);

  // --- Actions ---
  const sendMessage = () => {
    if (newMessage.trim() && socket && currentUserSid) {
      // Send SID instead of userId
      socket.emit('chat_message', { room_code: roomCode, sid: currentUserSid, message: newMessage });
      setNewMessage('');
    }
  };

  const leaveRoom = () => {
    if (socket && currentUserSid) {
      socket.emit('leave_room', { sid: currentUserSid, room_code: roomCode });
    }
    // Clear local storage related to this room/session if needed
    // localStorage.removeItem('username');
    // localStorage.removeItem('userId');
    navigate('/');
    toast({ title: "Você saiu da sala", description: `Você saiu da sala ${roomCode}.` });
  };

  const startGame = (gameType: string) => {
      if (socket && currentUserSid === hostSid) {
          // Emit an event to the backend to start the selected game
          // Construct event name based on gameType
          const eventName = `start_${gameType}_game`;
          console.log("Emitting start game event:", eventName, "for room", roomCode, "by host", currentUserSid);
          socket.emit(eventName, { room_code: roomCode, host_sid: currentUserSid });
          // Don't set currentGameType here; wait for 'game_started' event from backend
      } else if (currentUserSid !== hostSid) {
          toast({ title: "Ação não permitida", description: "Apenas o host pode iniciar o jogo.", variant: "destructive" });
      }
  };

  // --- Render Logic ---
  const renderGameComponent = () => {
    if (!currentGameType) return <p>Selecione um jogo para começar (apenas o Host pode iniciar).</p>;

    if (!currentUserSid || !socket || !roomCode) { // Added !roomCode check
        return <p>Erro: Informações do usuário, conexão ou código da sala não disponíveis.</p>;
    }

    // Dynamically render the component based on the game type from backend state
    switch (currentGameType) {
      case 'jogo_123': // Match backend type
        // Pass SID and initial state if available
        return <Jogo123Component roomCode={roomCode} currentUserSid={currentUserSid} userId={userId} socket={socket} initialGameState={currentGameInitialState} />;
      case 'jogo_eleitoral': // Match backend type
        return <JogoEleitoralComponent roomCode={roomCode} currentUserSid={currentUserSid} userId={userId} socket={socket} initialGameState={currentGameInitialState} />;
      case '5_5': // Match backend type
        return <Jogo55Component roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      case 'abrir_passar': // Match backend type
        return <JogoAbrirPassarComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      case 'abundancia_fome': // Match backend type
        return <JogoAbundanciaFomeComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      case 'corrida_cavalos_confinados': // Match backend type
        return <JogoCorridaCavalosConfinadosComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      case 'corrida_cavalos_golpistas': // Match backend type
        return <JogoCorridaCavalosGolpistasComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      case 'dilema_kong': // Match backend type
        return <JogoDilemaKongComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      // Add cases for other games using their backend game_type identifier
      // case 'jogo_zumbi':
      //   return <JogoZumbiComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      // case 'jogo_pegue_ladrao':
      //   return <JogoPegueLadraoComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      // case 'jogo_leilao_expressao':
      //   return <JogoLeilaoExpressaoComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      // case 'jogo_final':
      //   return <JogoFinalComponent roomCode={roomCode} currentUserSid={currentUserSid} initialGameState={currentGameInitialState} />;
      default:
        return <p>Interface para o jogo: {currentGameType} (Implementação Pendente)</p>;
    }
  };

  const currentHost = players.find(p => p.sid === hostSid);
  const currentGameDetails = gameList.find(g => g.type === currentGameType);

  return (
    <div className="container mx-auto p-4 flex flex-col md:flex-row gap-4 h-screen">
      {/* Left Panel: Players and Game Selection */}
      <Card className="w-full md:w-1/4 flex flex-col">
        <CardHeader>
          <CardTitle>Sala: {roomCode}</CardTitle>
          <CardDescription>Host: {currentHost?.username ?? '...'}</CardDescription>
        </CardHeader>
        <CardContent className="flex-grow overflow-y-auto">
          <h3 className="font-semibold mb-2">Jogadores ({players.length}):</h3>
          <ul>
            {players.map((player) => (
              <li key={player.sid} className={player.sid === hostSid ? 'font-bold' : ''}>
                {player.username} {player.sid === currentUserSid ? '(Você)' : ''} {player.sid === hostSid ? '(Host)' : ''}
              </li>
            ))}
          </ul>
        </CardContent>
        <CardFooter className="flex-col items-start">
            {/* Show game selection only if host and no game is currently running */}
            {currentUserSid === hostSid && !currentGameType && (
                <div className="w-full">
                    <h3 className="mb-2 font-semibold">Selecionar Jogo:</h3>
                    <ScrollArea className="h-40 w-full mb-2">
                        {gameList.map(game => (
                            <Button key={game.type} variant="ghost" className="w-full justify-start mb-1" onClick={() => startGame(game.type)}>
                                {game.name}
                            </Button>
                        ))}
                    </ScrollArea>
                </div>
            )}
            {/* Show current game name if a game is running */}
            {currentGameType && (
                <p className="mb-2 text-sm text-gray-600">Jogo atual: {currentGameDetails?.name ?? currentGameType}</p>
            )}
          <Button variant="destructive" onClick={leaveRoom} className="w-full mt-auto">Sair da Sala</Button>
        </CardFooter>
      </Card>

      {/* Right Panel: Game Area and Chat */}
      <div className="w-full md:w-3/4 flex flex-col gap-4">
        {/* Game Area */}
        <Card className="flex-grow">
          <CardHeader>
            <CardTitle>{currentGameDetails?.name ?? "Área do Jogo"}</CardTitle>
          </CardHeader>
          <CardContent>
            {renderGameComponent()}
          </CardContent>
        </Card>

        {/* Chat Area */}
        <Card className="h-1/3 flex flex-col">
          <CardHeader>
            <CardTitle>Chat</CardTitle>
          </CardHeader>
          <CardContent className="flex-grow overflow-y-auto">
            <ScrollArea className="h-full pr-4">
              {messages.map((msg, index) => (
                <p key={index}><strong>{msg.username}:</strong> {msg.message}</p>
              ))}
            </ScrollArea>
          </CardContent>
          <CardFooter>
            <div className="flex w-full space-x-2">
              <Input
                placeholder="Digite sua mensagem..."
                value={newMessage}
                onChange={(e) => setNewMessage(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
              />
              <Button onClick={sendMessage}>Enviar</Button>
            </div>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
};

export default GameRoomPage;

