import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
// Removed useSocket import as authentication will happen via token on connection

const AuthPage: React.FC = () => {
    const [loginUsername, setLoginUsername] = useState('');
    const [loginPassword, setLoginPassword] = useState('');
    const [registerUsername, setRegisterUsername] = useState('');
    const [registerPassword, setRegisterPassword] = useState('');
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();
    const { toast } = useToast();
    // Removed socket instance retrieval

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username: loginUsername, password: loginPassword }),
            });
            const data = await response.json();
            if (response.ok && data.access_token) { // Check for access_token
                toast({ title: "Login bem-sucedido!", description: `Bem-vindo de volta!` }); // Removed username display here for simplicity
                // Store the JWT token
                localStorage.setItem('jwtToken', data.access_token);
                // Removed old localStorage items for userId and username

                // Removed socket authentication logic here
                // Navigation happens after token is stored
                navigate('/'); // Navigate to home/dashboard after successful login

            } else {
                setError(data.message || 'Falha no login. Verifique suas credenciais ou a resposta da API.');
                toast({ title: "Erro de Login", description: data.message || 'Credenciais inválidas ou token não recebido.', variant: "destructive" });
            }
        } catch (err) {
            console.error("Login error:", err);
            setError('Ocorreu um erro ao tentar fazer login.');
            toast({ title: "Erro", description: 'Não foi possível conectar ao servidor.', variant: "destructive" });
        }
    };

    const handleRegister = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        try {
            const response = await fetch('/api/auth/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username: registerUsername, password: registerPassword }),
            });
            const data = await response.json();
            if (response.ok && data.access_token) { // Check for access_token after registration
                toast({ title: "Registro bem-sucedido!", description: `Bem-vindo! Você está logado.` });
                // Store the JWT token
                localStorage.setItem('jwtToken', data.access_token);
                // Removed old localStorage items

                // Removed socket authentication logic here
                navigate('/'); // Navigate to home/dashboard
            } else {
                setError(data.message || 'Falha no registro. Verifique a resposta da API.');
                toast({ title: "Erro de Registro", description: data.message || 'Não foi possível registrar ou token não recebido.', variant: "destructive" });
            }
        } catch (err) {
            console.error("Registration error:", err);
            setError('Ocorreu um erro ao tentar registrar.');
            toast({ title: "Erro", description: 'Não foi possível conectar ao servidor.', variant: "destructive" });
        }
    };

    return (
        <div className="flex items-center justify-center min-h-screen bg-gray-100">
            <Card className="w-full max-w-md">
                <CardHeader>
                    <CardTitle className="text-center text-2xl font-bold">Genius Online</CardTitle>
                    <CardDescription className="text-center">Faça login ou registre-se para jogar</CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs defaultValue="login" className="w-full">
                        <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="login">Login</TabsTrigger>
                            <TabsTrigger value="register">Registrar</TabsTrigger>
                        </TabsList>
                        <TabsContent value="login">
                            <form onSubmit={handleLogin} className="space-y-4 mt-4">
                                <Input
                                    type="text"
                                    placeholder="Nome de usuário"
                                    value={loginUsername}
                                    onChange={(e) => setLoginUsername(e.target.value)}
                                    required
                                />
                                <Input
                                    type="password"
                                    placeholder="Senha"
                                    value={loginPassword}
                                    onChange={(e) => setLoginPassword(e.target.value)}
                                    required
                                />
                                {error && <p className="text-red-500 text-sm">{error}</p>}
                                <Button type="submit" className="w-full">Entrar</Button>
                            </form>
                        </TabsContent>
                        <TabsContent value="register">
                            <form onSubmit={handleRegister} className="space-y-4 mt-4">
                                <Input
                                    type="text"
                                    placeholder="Nome de usuário"
                                    value={registerUsername}
                                    onChange={(e) => setRegisterUsername(e.target.value)}
                                    required
                                />
                                <Input
                                    type="password"
                                    placeholder="Senha"
                                    value={registerPassword}
                                    onChange={(e) => setRegisterPassword(e.target.value)}
                                    required
                                />
                                {error && <p className="text-red-500 text-sm">{error}</p>}
                                <Button type="submit" className="w-full">Registrar</Button>
                            </form>
                        </TabsContent>
                    </Tabs>
                </CardContent>
            </Card>
        </div>
    );
};

export default AuthPage;

