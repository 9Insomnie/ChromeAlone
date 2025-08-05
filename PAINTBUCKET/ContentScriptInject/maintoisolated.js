// Bridge for MAIN world to communicate with extension
// Handles both sending messages to extension and relaying responses back

// Generate unique message IDs for correlation
let messageIdCounter = 0;
const pendingMessages = new Map();

// Listen for messages from MAIN world
window.addEventListener('message', (event) => {
    if (event.source === window && event.data.type === 'MAIN_TO_EXTENSION') {
        const messageData = event.data.payload;
        
        // Use requestId from message if it exists, otherwise generate messageId
        const messageId = messageData.requestId || ++messageIdCounter;
        messageData.messageId = messageId;
        
        // Send message to background script and handle response
        chrome.runtime.sendMessage(messageData, (response) => {
            // Check for chrome.runtime.lastError
            if (chrome.runtime.lastError) {
                // Send error response back to MAIN world
                window.postMessage({
                    type: 'EXTENSION_TO_MAIN',
                    messageId: messageId,
                    success: false,
                    error: chrome.runtime.lastError.message,
                    originalType: messageData.type
                }, '*');
                return;
            }
            
            // Send successful response back to MAIN world
            window.postMessage({
                type: 'EXTENSION_TO_MAIN',
                messageId: messageId,
                success: true,
                data: response,
                originalType: messageData.type
            }, '*');
        });
    }
});

