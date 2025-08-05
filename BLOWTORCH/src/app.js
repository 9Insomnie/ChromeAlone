import { SocksServer } from './socks-server.js';

let socksServer = null;

export async function startProxy() {
    try {
        console.log("Starting proxy...");
        // Use environment variables injected by webpack
        const wsUrl = "wss://" + process.env.WS_DOMAIN + ":443";
        const relayToken = process.env.RELAY_TOKEN;
        
        console.log(`Connecting to WebSocket URL: ${wsUrl}`);
        
        if (socksServer) {
            console.log("Proxy already exists, stopping first...");
            socksServer.stop();
        }
        
        socksServer = new SocksServer(
            {
                "websocketUrl": wsUrl,
                "relayToken": relayToken
            }
        );
        updateStatus(`Creating WS Relay connection to ${wsUrl}`);
        await socksServer.start();        
    } catch (err) {
        updateStatus(`Failed to start proxy: ${err.message}`);
    }
}

export function stopProxy() {
    if (socksServer) {
        socksServer.stop();
        socksServer = null;
        updateStatus('Proxy server stopped');
    }
}

export function getRelayServer() {
    return socksServer;
}

function updateStatus(message) {
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = message;
    }
} 