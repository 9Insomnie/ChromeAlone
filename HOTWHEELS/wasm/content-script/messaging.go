//go:build js && wasm
// +build js,wasm

package main

import (
	"fmt"
	"syscall/js"
)

type ContentMessageHandler struct {
	chrome js.Value
}

func NewContentMessageHandler() *ContentMessageHandler {
	return &ContentMessageHandler{
		chrome: js.Global().Get("chrome"),
	}
}

func (cmh *ContentMessageHandler) setupMessageListener() {
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

		cmh.handleMessage(message, sender, sendResponse)
		return true
	})

	cmh.chrome.Get("runtime").Get("onMessage").Call("addListener", messageListener)
	println("Content script: Message listener set up")
}

func (cmh *ContentMessageHandler) handleMessage(message js.Value, sender js.Value, sendResponse js.Value) {
	messageType := message.Get("type").String()

	println(fmt.Sprintf("Content script: Received message type: %s", messageType))

	switch messageType {
	case "pong":
		cmh.handlePong(message, sender, sendResponse)
	default:
		println(fmt.Sprintf("Content script: Unknown message type: %s", messageType))
		response := map[string]interface{}{
			"success": false,
			"error":   "Unknown message type",
		}
		sendResponse.Invoke(response)
	}
}

func (cmh *ContentMessageHandler) handlePong(message js.Value, sender js.Value, sendResponse js.Value) {
	data := message.Get("data").String()
	println(fmt.Sprintf("Content script: Pong received: %s", data))

	response := map[string]interface{}{
		"success": true,
		"data":    "Pong acknowledged",
	}
	sendResponse.Invoke(response)
}

func (cmh *ContentMessageHandler) sendMessage(messageType string, data interface{}) {
	message := map[string]interface{}{
		"type":      messageType,
		"data":      data,
		"timestamp": js.Global().Get("Date").New().Call("toISOString").String(),
	}

	callback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			response := args[0]
			if response.Get("success").Bool() {
				var responseData string
				if !response.Get("data").IsUndefined() {
					responseData = response.Get("data").String()
				} else if !response.Get("processedData").IsUndefined() {
					responseData = response.Get("processedData").String()
				} else {
					responseData = "Success"
				}
				println(fmt.Sprintf("Content script: Message sent successfully, response: %s", responseData))
			} else {
				println(fmt.Sprintf("Content script: Message failed, error: %s",
					response.Get("error").String()))
			}
		}
		return nil
	})

	cmh.chrome.Get("runtime").Call("sendMessage", message, callback)
}

func (cmh *ContentMessageHandler) sendPing(data string) {
	cmh.sendMessage("ping", data)
}

func (cmh *ContentMessageHandler) sendFormData(formData string) {
	cmh.sendMessage("form_data", formData)
}

func (cmh *ContentMessageHandler) sendDebugInfo(debugInfo string) {
	cmh.sendMessage("debug", debugInfo)
}
