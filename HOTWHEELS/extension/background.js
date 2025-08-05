try {
    importScripts('./wasm/wasm_exec.js')
} catch (e) {
    console.error(e);
}

globalThis.started = false;

async function Startup() {
    if (globalThis.started) {
        console.log("HOTWHEELS: ALREADY STARTED - SKIPPING STARTUP");
        return;
    }
    globalThis.started = true;

    const go = new Go();
    WebAssembly.instantiateStreaming(fetch('./wasm/background.wasm'), go.importObject).then(result => {
        go.run(result.instance);
    });
}

chrome.runtime.onInstalled.addListener(async function() {
    await Startup();
});

chrome.runtime.onStartup.addListener(async function() {
    await Startup();
});

console.log("HOTWHEELS: RUNNING BACKGROUND SCRIPT");

// On initial sideload there is a race condition where the chrome.runtime listeners don't run - this handles that case
setTimeout(async () => {    
    await Startup();
    console.log("HOTWHEELS: INVOKED DELAYED STARTUP");
}, 5000);

// Hack to prevent the background script from being killed via
// https://stackoverflow.com/questions/66618136/persistent-service-worker-in-chrome-extension
const keepAlive = () => setInterval(chrome.runtime.getPlatformInfo, 20e3);
chrome.runtime.onStartup.addListener(keepAlive);
keepAlive();