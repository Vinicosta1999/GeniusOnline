import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import './App.css';

// Import pages/components
import HomePage from './components/HomePage'; // Corrected path
import GameRoomPage from './components/GameRoomPage'; // Corrected path
import AuthPage from './pages/AuthPage'; // Import the new AuthPage
import { Toaster } from "@/components/ui/toaster"; // Import Toaster
import { Button } from "@/components/ui/button"; // Import Button for logout example


// Placeholder for NotFoundPage
const NotFoundPage = () => <div><h1>404 - Page Not Found</h1></div>;

// Updated check for authentication status using JWT token
const isAuthenticated = () => !!localStorage.getItem('jwtToken');

// Protected Route Component
const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
    if (!isAuthenticated()) {
        // Redirect them to the /auth page if no JWT token is found
        return <Navigate to="/auth" replace />;
    }
    return children;
};

// Simple Logout Button Component (Example - can be placed elsewhere)
const LogoutButton = () => {
    const navigate = useNavigate();
    const handleLogout = () => {
        localStorage.removeItem('jwtToken'); // Clear the token
        // Optionally disconnect socket or perform other cleanup
        navigate('/auth'); // Redirect to login page
        // Force a reload if socket context needs full reset
        // window.location.reload(); 
    };
    return <Button onClick={handleLogout} variant="outline" size="sm" className="absolute top-4 right-4">Logout</Button>; // Example positioning
}

function App() {
    return (
        <div className="App relative"> {/* Added relative positioning for logout button example */}
            {isAuthenticated() && <LogoutButton />} {/* Show logout button only if authenticated */}
            <Routes>
                <Route path="/auth" element={<AuthPage />} />
                <Route 
                    path="/" 
                    element={
                        <ProtectedRoute>
                            <HomePage />
                        </ProtectedRoute>
                    } 
                />
                <Route 
                    path="/room/:roomCode" 
                    element={
                        <ProtectedRoute>
                            <GameRoomPage />
                        </ProtectedRoute>
                    } 
                />
                {/* Add other protected routes here */}
                <Route path="*" element={<NotFoundPage />} /> {/* Catch-all route */}
            </Routes>
            <Toaster /> {/* Add Toaster here for global toasts */}
        </div>
    );
}

export default App;

