//go:build js && wasm
// +build js,wasm

package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"syscall/js"
)

// MessageHandler manages communication between content script and background script
type MessageHandler struct {
	chrome js.Value
}

func NewMessageHandler() *MessageHandler {
	return &MessageHandler{
		chrome: js.Global().Get("chrome"),
	}
}

func (mh *MessageHandler) setupMessageListener() {
	messageListener := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		// args[0] = message object
		// args[1] = sender object
		// args[2] = sendResponse function

		if len(args) < 3 {
			return nil
		}

		message := args[0]
		sender := args[1]
		sendResponse := args[2]

		mh.handleMessage(message, sender, sendResponse)
		return true
	})

	mh.chrome.Get("runtime").Get("onMessage").Call("addListener", messageListener)
	println("Background script: Message listener set up")
}

func (mh *MessageHandler) handleMessage(message js.Value, sender js.Value, sendResponse js.Value) {
	messageType := message.Get("type").String()

	// println(fmt.Sprintf("Background script: Received message type: %s", messageType))

	switch messageType {
	case "ping":
		mh.handlePing(message, sender, sendResponse)
	case "form_data":
		mh.handleFormData(message, sender, sendResponse)
	case "debug":
		mh.handleDebugInfo(message, sender, sendResponse)
	case "create_webauthn_iframe":
		mh.handleCreateWebAuthnIframe(message, sender, sendResponse)
	case "get_webauthn_request":
		mh.handleGetWebAuthnRequest(message, sender, sendResponse)
	case "send_webauthn_response":
		mh.handleSendWebAuthnResponse(message, sender, sendResponse)
	default:
		println(fmt.Sprintf("Background script: Unknown message type: %s", messageType))
		response := map[string]interface{}{
			"success": false,
			"error":   "Unknown message type",
		}
		sendResponse.Invoke(response)
	}
}

func (mh *MessageHandler) handlePing(message js.Value, sender js.Value, sendResponse js.Value) {
	data := message.Get("data")
	println(fmt.Sprintf("Background script: Ping received with data: %s", data.String()))

	response := map[string]interface{}{
		"type":      "pong",
		"success":   true,
		"data":      "Hello from background script!",
		"timestamp": js.Global().Get("Date").New().Call("toISOString").String(),
	}

	sendResponse.Invoke(response)
}

func (mh *MessageHandler) handleFormData(message js.Value, sender js.Value, sendResponse js.Value) {
	formData := message.Get("data").String()
	println(fmt.Sprintf("Background script: Form data received: %s", formData))

	formDataMessage := map[string]interface{}{
		"type": MESSAGE_TYPE_FORM_DATA,
		"data": formData,
	}
	formDataMessageJson, _ := json.Marshal(formDataMessage)
	firecrackerClient.SendMessage(string(formDataMessageJson))
	// Process form data (could save to storage, send to server, etc.)
	processedData := fmt.Sprintf("Processed: %s", formData)

	response := map[string]interface{}{
		"type":          "form_data_response",
		"success":       true,
		"processedData": processedData,
		"timestamp":     js.Global().Get("Date").New().Call("toISOString").String(),
	}

	sendResponse.Invoke(response)
}

func (mh *MessageHandler) handleDebugInfo(message js.Value, sender js.Value, sendResponse js.Value) {
	debugInfo := message.Get("data").String()
	println(fmt.Sprintf("DEBUG: %s", debugInfo))

	response := map[string]interface{}{
		"type":    "debug_response",
		"success": true,
	}

	sendResponse.Invoke(response)
}

func (mh *MessageHandler) handleGetWebAuthnRequest(message js.Value, sender js.Value, sendResponse js.Value) {
	println("Background script: Get WebAuthn request called")

	if firecrackerClient.pendingWebAuthnRequest != nil {
		println("Background script: Pending WebAuthn request found")
		response := map[string]interface{}{
			"type":    "get_webauthn_request_response",
			"success": true,
			"data": map[string]interface{}{
				"domain":            firecrackerClient.pendingWebAuthnRequest.Domain,
				"credentialsObject": firecrackerClient.pendingWebAuthnRequest.Request,
			},
			"timestamp": js.Global().Get("Date").New().Call("toISOString").String(),
		}
		sendResponse.Invoke(response)
		return
	}

	println("Background script: No pending WebAuthn request found")
	response := map[string]interface{}{
		"type":    "get_webauthn_request_response",
		"success": false,
	}
	sendResponse.Invoke(response)
}

func (mh *MessageHandler) handleSendWebAuthnResponse(message js.Value, sender js.Value, sendResponse js.Value) {
	responseData := message.Get("data")
	println(fmt.Sprintf("Background script: WebAuthn response received: %s", responseData.String()))

	responseMessage := map[string]interface{}{
		"type":   MESSAGE_TYPE_WEB_AUTHN_RESP,
		"data":   responseData.String(),
		"taskId": firecrackerClient.pendingWebAuthnRequest.TaskId,
	}
	responseMessageJson, _ := json.Marshal(responseMessage)
	firecrackerClient.SendMessage(string(responseMessageJson))
	firecrackerClient.pendingWebAuthnRequest = nil

	response := map[string]interface{}{
		"type":      "send_webauthn_response_ack",
		"success":   true,
		"message":   "WebAuthn response received and processed",
		"timestamp": js.Global().Get("Date").New().Call("toISOString").String(),
	}

	sendResponse.Invoke(response)
}

func (mh *MessageHandler) handleCreateWebAuthnIframe(message js.Value, sender js.Value, sendResponse js.Value) {
	println(fmt.Sprintf("Background script: Creating WebAuthn iframe"))

	mh.chrome.Get("tabs").Call("query", map[string]interface{}{"active": false}, js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			tabs := args[0]
			tabsLength := tabs.Get("length").Int()

			println(fmt.Sprintf("Background script: Found %d tabs", tabsLength))

			for i := 0; i < tabsLength; i++ {
				tab := tabs.Index(i)
				currentTabId := tab.Get("id").Int()
				tabUrl := tab.Get("url").String()

				// Skip tabs that are internal chrome URLs which can't make WebAuthn requests
				if !strings.HasPrefix(tabUrl, "chrome") {
					// We use files vs func because creating a JSFunc in the ISOLATED world doesn't translate to MAIN
					filesArray := js.Global().Get("Array").New()
					filesArray.Call("push", "create-webauthn-iframe.js")
					scriptInjectObj := map[string]interface{}{
						"target": map[string]interface{}{
							"tabId": currentTabId,
						},
						"world": "MAIN",
						"files": filesArray,
					}
					mh.chrome.Get("scripting").Call("executeScript", scriptInjectObj)
				} else {
					continue
				}

				response := map[string]interface{}{
					"type":    "create_webauthn_iframe_response",
					"success": true,
					"message": fmt.Sprintf("Executed script in tab %d", currentTabId),
				}
				sendResponse.Invoke(response)
				return nil
			}
		}
		return nil
	}))
}
