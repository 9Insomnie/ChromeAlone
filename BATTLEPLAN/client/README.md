# ChromeAlone Web Frontend

A web-based dashboard for interacting with the ChromeAlone relay server endpoints.

## Features

- **Agent Management**: View all connected agents with real-time status updates
- **Quick Commands**: Predefined buttons for common operations (ls, shell, cookies, history, webauthn)
- **Command Execution**: Send commands to specific agents with JSON payloads
- **Real-time Task Events**: Live notifications for task queuing and completion via Server-Sent Events
- **Task History**: Persistent task tracking with results stored in localStorage (survives page refreshes)
- **Captured Data Monitoring**: Real-time display of unprompted data captured from agents (form submissions, etc.)
- **Interactive Shell Terminal**: Terminal-style interface for executing shell commands with command history and real-time output
- **Tabbed Interface**: Separate tabs for task history, captured data, file browser, and interactive shell
- **Task Tracking**: Monitor task execution status and results
- **Auto-refresh**: Automatic agent list updates every 10 seconds
- **Persistent Configuration**: Settings saved to browser localStorage

## Available Commands

### Quick Commands
The webapp includes predefined quick command buttons for common operations:

- **📁 List Directory (ls)** - Lists files and directories
- **💻 Shell Command (whoami)** - Executes shell commands 
- **🍪 Dump Cookies** - Extracts browser cookies
- **📜 Dump History** - Extracts browser history
- **🔐 WebAuthn Challenge** - Handles WebAuthn authentication requests

### Command Details

#### 1. List Directory (`ls`)
```
Command: "ls"
Payload: {}
```

#### 2. Shell Command (`shell`)
```
Command: "shell"
Payload: "whoami|"
```
Shell commands use a special format where the command and arguments are separated by a `|` character:
- `"whoami|"` - Run whoami with no arguments
- `"ipconfig|/all"` - Run ipconfig with /all argument
- `"dir|C:\\"` - Run dir command on C:\ drive
- `"ps|aux"` - Run ps with aux arguments (Linux/Mac)

The webapp provides separate fields for the shell command and arguments for easier input.

**Note**: Shell command results are returned base64-encoded by the server, but the webapp automatically decodes them for display in both the task history and task response sections.

#### 3. Dump Cookies (`cookies`)
```
Command: "cookies"
Payload: {}
```

#### 4. Dump History (`history`)
```
Command: "history"
Payload: {}
```

#### 5. WebAuthn (`webauthn`)
```
Command: "webauthn"
Payload: "{\"domain\": \"example.com\", \"request\": \"eyJwdWJsaWNLZXkiOnsic...\"}"
```
The `request` field should contain a base64-encoded WebAuthn challenge.

**Important:** The payload field expects a **JSON string**, not a JSON object. For simple commands like `ls`, `cookies`, and `history`, use `{}`. For commands that need parameters like `shell` and `webauthn`, use escaped JSON strings.

## Tabbed Interface

The dashboard features a tabbed interface with four main sections:

### Task History Tab
- Displays all executed commands and their results
- Filter by agent IP address
- Shows task status (pending, completed, failed)
- Displays command payloads and results
- Clear all task history

### Captured Data Tab
- Displays data automatically captured from agents (form submissions, etc.)
- **Filter by Agent IP**: Shows only data from specific agents
- **Filter by Content**: Search for specific keywords in captured data (e.g., "password", "username", "email")
- **Filter by Data Type**: Filter by the type of captured data
- Clear captured data independently from task history

Content filtering is particularly useful for security monitoring - you can quickly find captured credentials or sensitive information by searching for keywords like "password", "username", "email", "ssn", etc.

### File Browser Tab
- Browse files and directories on remote agents using `ls` commands
- Navigate directories with clickable folder entries and breadcrumb navigation
- "Traverse up" button for parent directory navigation
- Agent selection and starting path configuration

### Interactive Shell Tab
- **Terminal-style interface** simulating a command-line terminal
- **Command History Navigation**: Use up/down arrow keys to navigate through previously executed commands
- **Real-time Output**: Command results appear directly in the terminal as they complete
- **ASCII Spinner**: Visual indicator while commands are executing
- **Agent Selection**: Choose which agent to connect to for shell commands
- **Quick Command Integration**: Terminal-specific quick command buttons for instant execution
- **Auto-scroll**: Terminal automatically scrolls to show latest output
- **Clear Terminal**: Reset terminal display while preserving command history

The Interactive Shell provides a familiar terminal experience for executing shell commands, complete with command history, real-time feedback, and visual execution indicators.

## Usage

1. Open `index.html` in your web browser
2. Configure server settings (host, port, credentials)
3. Use the dashboard to:
   - View connected agents
   - Execute quick commands or custom commands
   - Monitor task status
   - View task history with filtering by agent IP in the "Task History" tab
   - View captured data with content and type filtering in the "Captured Data" tab
   - Browse files and directories in the "File Browser" tab
   - Use the "Interactive Shell" tab for terminal-style command execution
   - Clear task history or captured data independently

## Server Endpoints

The frontend interacts with these relay server endpoints:

- `GET /info` - Agent information and status
- `POST /command` - Execute commands on agents
- `GET /task/:taskId` - Check task execution status
- `GET /events` - Server-Sent Events stream for real-time task notifications

## Configuration

The application loads default settings from `config.js`. This JavaScript-based approach avoids CORS issues when loading files locally and centralizes all configuration for easy customization.

### Default Configuration
- **Host**: 18.223.36.246
- **Port**: 1080
- **Username**: admin
- **Password**: wpMtNeiMla3orv1nD62xQ9Rjn6Be/HaLehZHeQPyevc=

### Customization
To customize default settings:
1. Edit `config.js` with your preferred values
2. The application will load these as defaults
3. Users can still override settings in the UI (saved to localStorage)

See `CONFIG.md` for detailed configuration documentation.

## Keyboard Shortcuts

- `Ctrl+R` - Refresh agent list
- `Ctrl+Enter` - Execute command (when in command or payload field)

## Security Note

This frontend uses Basic Authentication to communicate with the relay server. Ensure you're using HTTPS in production environments.