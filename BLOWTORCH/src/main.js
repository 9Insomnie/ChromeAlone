import { startProxy, stopProxy, getRelayServer } from './app.js';
import {FirecrackerWebSocketServer, initializeFirecrackerServer, getFirecrackerServer} from'./websocket-server.js';

let firecrackerServer = null;

// Firecracker logging callback that outputs to main console
function firecrackerLogCallback(message, ...args) {
    console.log(message, ...args);
}

// Export getFirecrackerServer for external access
export function getFirecrackerServerInstance() {
    return firecrackerServer || getFirecrackerServer();
}

async function initializeApp() {
    console.log("Initializing app...");
    const startButton = document.getElementById('startProxy');
    const stopButton = document.getElementById('stopProxy');
    
    if (startButton && stopButton) {
        startButton.removeEventListener('click', startProxy);
        stopButton.removeEventListener('click', stopProxy);
        
        startButton.addEventListener('click', startProxy);
        stopButton.addEventListener('click', stopProxy);

        await startProxy();
        firecrackerServer = await initializeFirecrackerServer(firecrackerLogCallback);
    }
}

// Expose functions globally for devtools access
window.getFirecrackerServerInstance = getFirecrackerServerInstance;
window.broadcastToFirecracker = async function(message) {
    const server = getFirecrackerServerInstance();
    if (server && server.clientConnections) {
        let sent = 0;
        for (const [connectionId, connectionInfo] of server.clientConnections) {
            if (connectionInfo.isWebSocket) {
                await server.sendWebSocketMessage(connectionInfo, message);
                sent++;
            }
        }
        console.log(`Broadcast sent to ${sent} WebSocket connections`);
        return sent;
    } else {
        console.log("Server not available or no connections");
        return 0;
    }
};

window.getRelayServer = getRelayServer;

// Wait for DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeApp);
} else {
    initializeApp();
}