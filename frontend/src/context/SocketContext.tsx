import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import io, { Socket } from 'socket.io-client';

// Define the shape of the context value
interface SocketContextType {
  socket: Socket | null;
  isConnected: boolean;
  sid: string | null;
}

// Create the context with a default value
export const SocketContext = createContext<SocketContextType>({ 
  socket: null, 
  isConnected: false,
  sid: null
});

// Custom hook to use the socket context
export const useSocket = (): SocketContextType => {
  return useContext(SocketContext);
};

// Define props for the provider
interface SocketProviderProps {
  children: ReactNode;
}

// Socket Provider component
export const SocketProvider: React.FC<SocketProviderProps> = ({ children }) => {
  const [socket, setSocket] = useState<Socket | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  useEffect(() => {
    // Retrieve the JWT token from localStorage
    const jwtToken = localStorage.getItem('jwtToken');

    // Initialize socket connection with authentication token if available
    // The backend needs to be configured to expect the token in `auth.token`
    const newSocket: Socket = io(import.meta.env.VITE_API_URL || window.location.origin, {
      path: "/socket.io",
      transports: ['websocket'],
      auth: {
        token: jwtToken // Send the token for authentication
      }
    });

    newSocket.on('connect', () => {
      console.log('Socket connected:', newSocket.id);
      setIsConnected(true);
      // No need to emit 'authenticate_socket' anymore, authentication happens on connection
    });

    newSocket.on('disconnect', (reason: Socket.DisconnectReason) => {
      console.log('Socket disconnected:', reason);
      setIsConnected(false);
      // Handle potential token expiration or invalidation leading to disconnect
      if (reason === 'io server disconnect') {
        // Server disconnected the client, possibly due to invalid token
        // Consider clearing the token and redirecting to login
        localStorage.removeItem('jwtToken');
        // Potentially navigate('/auth'); // Requires access to navigate hook, might need context/prop drilling
        console.warn('Disconnected by server, possibly invalid token.');
      }
    });

    newSocket.on('connect_error', (error: Error) => {
      console.error('Socket connection error:', error.message);
      // Handle specific authentication errors if the server sends them
      // Example: if (error.message.includes('Authentication error')) { ... }
      setIsConnected(false);
      // If connection fails due to auth, clear token and redirect might be needed
      // localStorage.removeItem('jwtToken');
      // navigate('/auth');
    });

    // Set the socket state
    setSocket(newSocket);

    // Cleanup function
    return () => {
      console.log('Disconnecting socket...');
      newSocket.disconnect();
    };
  }, []); // Rerun effect if token changes? Consider dependencies if token refresh is implemented

  // Value provided by the context
  const value: SocketContextType = {
    socket,
    isConnected,
    sid: socket?.id ?? null
  };

  return (
    <SocketContext.Provider value={value}>
      {children}
    </SocketContext.Provider>
  );
};

