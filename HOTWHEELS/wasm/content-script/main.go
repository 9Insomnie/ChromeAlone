//go:build js && wasm
// +build js,wasm

package main

import (
	"syscall/js"
)

// Global variables
var (
	document          js.Value
	window            js.Value
	observer          js.Value
	processor         *FormProcessor
	msgHandler        *ContentMessageHandler
	submissionTracker *SubmissionTracker
)

// main function sets up the WASM module and starts the form highlighter
func main() {
	document = js.Global().Get("document")
	window = js.Global().Get("window")
	processor = NewFormProcessor()
	msgHandler = NewContentMessageHandler()
	msgHandler.setupMessageListener()
	submissionTracker = NewSubmissionTracker()

	js.Global().Set("handleFormSubmission", js.FuncOf(handleFormSubmission))
	js.Global().Set("handleEnhancedMutations", js.FuncOf(handleEnhancedMutations))
	js.Global().Set("startFormInterceptor", js.FuncOf(startFormInterceptor))
	js.Global().Set("interceptAllForms", js.FuncOf(interceptAllForms))
	js.Global().Set("handleButtonClick", js.FuncOf(handleButtonClick))
	js.Global().Set("handleEnterKeySubmission", js.FuncOf(handleEnterKeySubmission))

	initializeFormInterceptor()

	initialPingCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		msgHandler.sendPing("Content script initialized and ready")
		return nil
	})
	js.Global().Call("setTimeout", initialPingCallback, 1000)

	select {}
}
