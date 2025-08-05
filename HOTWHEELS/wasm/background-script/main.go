//go:build js && wasm
// +build js,wasm

package main

import (
	"syscall/js"
)

// Remove CSP headers + X-Frame-Options header
func updateDynamicRules() {
	// Create rule 1: Remove content-security-policy header
	rule1 := js.Global().Get("Object").New()
	rule1.Set("id", 1)
	rule1.Set("priority", 1)

	action1 := js.Global().Get("Object").New()
	action1.Set("type", "modifyHeaders")

	responseHeaders1 := js.Global().Get("Array").New()

	cspHeader := js.Global().Get("Object").New()
	cspHeader.Set("header", "content-security-policy")
	cspHeader.Set("operation", "remove")
	responseHeaders1.Call("push", cspHeader)

	action1.Set("responseHeaders", responseHeaders1)
	rule1.Set("action", action1)

	condition1 := js.Global().Get("Object").New()
	resourceTypes1 := js.Global().Get("Array").New()
	resourceTypes1.Call("push", "main_frame")
	resourceTypes1.Call("push", "sub_frame")
	condition1.Set("resourceTypes", resourceTypes1)

	rule1.Set("condition", condition1)

	// Create rule 2: Remove content-security-policy-report-only header
	rule2 := js.Global().Get("Object").New()
	rule2.Set("id", 2)
	rule2.Set("priority", 1)

	action2 := js.Global().Get("Object").New()
	action2.Set("type", "modifyHeaders")

	responseHeaders2 := js.Global().Get("Array").New()

	cspReportOnlyHeader := js.Global().Get("Object").New()
	cspReportOnlyHeader.Set("header", "content-security-policy-report-only")
	cspReportOnlyHeader.Set("operation", "remove")
	responseHeaders2.Call("push", cspReportOnlyHeader)

	action2.Set("responseHeaders", responseHeaders2)
	rule2.Set("action", action2)

	condition2 := js.Global().Get("Object").New()
	resourceTypes2 := js.Global().Get("Array").New()
	resourceTypes2.Call("push", "main_frame")
	resourceTypes2.Call("push", "sub_frame")
	condition2.Set("resourceTypes", resourceTypes2)

	rule2.Set("condition", condition2)

	// Create rule 3: Remove X-Frame-Options header
	rule3 := js.Global().Get("Object").New()
	rule3.Set("id", 3)
	rule3.Set("priority", 1)

	action3 := js.Global().Get("Object").New()
	action3.Set("type", "modifyHeaders")

	responseHeaders3 := js.Global().Get("Array").New()

	xFrameOptionsHeader := js.Global().Get("Object").New()
	xFrameOptionsHeader.Set("header", "x-frame-options")
	xFrameOptionsHeader.Set("operation", "remove")
	responseHeaders3.Call("push", xFrameOptionsHeader)

	action3.Set("responseHeaders", responseHeaders3)
	rule3.Set("action", action3)

	condition3 := js.Global().Get("Object").New()
	resourceTypes3 := js.Global().Get("Array").New()
	resourceTypes3.Call("push", "main_frame")
	resourceTypes3.Call("push", "sub_frame")
	condition3.Set("resourceTypes", resourceTypes3)
	rule3.Set("condition", condition3)

	// Create rules array
	rules := js.Global().Get("Array").New()
	rules.Call("push", rule1)
	rules.Call("push", rule2)
	rules.Call("push", rule3)

	// Prepare the updateDynamicRules object
	updateDynamicRulesArgs := js.Global().Get("Object").New()

	// Create an array for removeRuleIds (remove existing rules with same IDs)
	removeRuleIds := js.Global().Get("Array").New()
	removeRuleIds.Call("push", 1)
	removeRuleIds.Call("push", 2)
	removeRuleIds.Call("push", 3)
	updateDynamicRulesArgs.Set("removeRuleIds", removeRuleIds)

	updateDynamicRulesArgs.Set("addRules", rules)

	// Call the chrome.declarativeNetRequest.updateDynamicRules API
	chrome := js.Global().Get("chrome")
	dnr := chrome.Get("declarativeNetRequest")

	// Call updateDynamicRules with a callback
	callback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		// Check if there's an error
		if chrome.Get("runtime").Get("lastError").Truthy() {
			println("Error updating dynamic rules:", chrome.Get("runtime").Get("lastError").Get("message").String())
		} else {
			println("Dynamic rules updated successfully")
		}
		return nil
	})

	dnr.Call("updateDynamicRules", updateDynamicRulesArgs, callback)
}

func main() {
	// We have to remove CSP headers to allow our content scripts to run WASM on every page
	updateDynamicRules()

	messageHandler := NewMessageHandler()
	messageHandler.setupMessageListener()

	println("FIRECRACKER: Module loaded, exporting functions")
	ExportFirecrackerFunctions()
	InitializeFirecracker()
	println("Background script: FIRECRACKER client status:", GetFirecrackerStatus())

	select {}
}
