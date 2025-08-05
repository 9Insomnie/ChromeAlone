(function() {
    'use strict';
    async function loadWASM() {
        try {
           const go = new Go();
           const wasmModule = await WebAssembly.instantiateStreaming(
                    fetch(chrome.runtime.getURL('wasm/') + 'main.wasm'),
                    go.importObject
           );
           go.run(wasmModule.instance);
        } catch (error) {
            console.error('Failed to load WASM module.');
            console.error('Full error details:', {
                name: error.name,
                message: error.message,
                stack: error.stack,
                toString: error.toString()
            });
            return false;
        }
        return true;
    }
    
    // Load WASM and provide user feedback
    loadWASM().then(success => {
        if (success) {
            console.log('Content Script loaded successfully');
        } else {
            console.warn('Content Script failed to load WASM - some features may not work');
        }
    }).catch(error => {
        console.error('WASM loading failed:', error);
    });
})();