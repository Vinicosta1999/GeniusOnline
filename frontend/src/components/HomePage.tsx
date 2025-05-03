import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { useSocket } from '@/context/SocketContext'; // Assuming SocketContext provides the socket instance

const HomePage = () => {
  const [username, setUsername] = useState('');
  const [roomCode, setRoomCode] = useState('');
  const navigate = useNavigate();
  const { toast } = useToast();
  const { socket /*, isConnected*/ } = useSocket();

  const handleCreateRoom = async () => {
    if (!username.trim()) {
      toast({ title: "Erro", description: "Por favor, insira um nome de usuário.", variant: "destructive" });
      return;
    }
    try {
      // Use fetch to call the backend API endpoint for creating a room
      const response = await fetch("/api/game/rooms", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ max_players: 13 }), // Max players for Genius games can vary, using 13 as a placeholder
      });
      const data = await response.json();
      if (response.ok) {
        const newRoomCode = data.room_code;
        const userId = data.host_id; // Assuming the creator is the host
        localStorage.setItem('username', username);
        localStorage.setItem('userId', userId.toString()); // Store user ID
        toast({ title: "Sala Criada", description: `Sala ${newRoomCode} criada com sucesso.` });
        // Automatically join the created room via Socket.IO
        if (socket) {
          socket.emit('join_room', { user_id: userId, room_code: newRoomCode });
          navigate(`/room/${newRoomCode}`);
        } else {
           toast({ title: "Erro de Conexão", description: "Não foi possível conectar ao servidor.", variant: "destructive" });
        }
      } else {
        toast({ title: "Erro ao Criar Sala", description: data.message || "Ocorreu um erro.", variant: "destructive" });
      }
    } catch (error) {
      console.error("Error creating room:", error);
      toast({ title: "Erro de Rede", description: "Não foi possível conectar ao servidor para criar a sala.", variant: "destructive" });
    }
  };

  const handleJoinRoom = async () => {
    if (!username.trim() || !roomCode.trim()) {
      toast({ title: "Erro", description: "Por favor, insira nome de usuário e código da sala.", variant: "destructive" });
      return;
    }
    try {
        // Simulate user creation/login or retrieve existing user ID if implementing auth later
        // For now, let's assume a simple user creation/retrieval or pass username
        // A proper implementation would involve user registration/login
        // Let's try to get a user ID first, or create one (placeholder logic)
        let userId = localStorage.getItem('userId');
        if (!userId) {
             // Simple placeholder: create a user on the fly (replace with actual auth)
             const userResponse = await fetch('/api/register', { // Assuming a simple registration endpoint
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username, password: 'password' }) // Placeholder password
             });
             const userData = await userResponse.json();
             if (userResponse.ok) {
                 userId = userData.user_id;
                 if (userId) {
                     localStorage.setItem("userId", userId.toString());
                 }
             } else {
                 // Try logging in if registration failed (maybe user exists)
                 const loginResponse = await fetch('/api/login', { // Assuming a simple login endpoint
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ username: username, password: 'password' })
                 });
                 const loginData = await loginResponse.json();
                 if (loginResponse.ok) {
                     userId = loginData.user_id;
                     if (userId) {
                         localStorage.setItem("userId", userId.toString());
                     }
                 } else {
                     toast({ title: "Erro de Autenticação", description: "Não foi possível criar ou encontrar usuário.", variant: "destructive" });
                     return;
                 }
             }
        }

        localStorage.setItem('username', username);

        // Join room via Socket.IO
        if (socket && userId) {
          socket.emit('join_room', { user_id: parseInt(userId, 10), room_code: roomCode });
          // Listen for confirmation or error from backend before navigating
          socket.once('room_status', (statusData) => {
            if (statusData.room_code === roomCode) {
                 toast({ title: "Entrou na Sala", description: `Você entrou na sala ${roomCode}.` });
                 navigate(`/room/${roomCode}`);
            } else {
                 // Handle cases where status is for a different room?
            }
          });
          socket.once('error', (errorData) => {
             toast({ title: "Erro ao Entrar na Sala", description: errorData.message || "Ocorreu um erro.", variant: "destructive" });
          });
        } else {
           toast({ title: "Erro de Conexão", description: "Não foi possível conectar ao servidor ou obter ID de usuário.", variant: "destructive" });
        }
    } catch (error) {
        console.error("Error joining room:", error);
        toast({ title: "Erro de Rede", description: "Não foi possível conectar ao servidor para entrar na sala.", variant: "destructive" });
    }
  };

  return (
    <div className="flex justify-center items-center min-h-screen bg-gray-100">
      <Card className="w-[350px]">
        <CardHeader>
          <CardTitle>Genius Online Lobby</CardTitle>
          <CardDescription>Crie ou entre em uma sala para jogar.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid w-full items-center gap-4">
            <div className="flex flex-col space-y-1.5">
              <Input
                id="username"
                placeholder="Seu nome de usuário"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="flex flex-col space-y-1.5">
              <Input
                id="roomCode"
                placeholder="Código da sala (para entrar)"
                value={roomCode}
                onChange={(e) => setRoomCode(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button onClick={handleCreateRoom}>Criar Sala</Button>
          <Button variant="outline" onClick={handleJoinRoom} disabled={!roomCode.trim()}>Entrar na Sala</Button>
        </CardFooter>
      </Card>
    </div>
  );
};

export default HomePage;

