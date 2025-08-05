# DOORKNOB - Browser Extension & IWA Persistence Component

## Overview
DOORKNOB is the persistence and installation component of ChromeAlone that bypasses Chrome's security mechanisms to install unauthorized extensions and Isolated Web Applications (IWAs). It manipulates Chrome's internal databases and configuration files to achieve persistence without user consent.

## What is DOORKNOB?

DOORKNOB implements two primary attack vectors:
1. **Chrome Extension Sideloading** - Installing malicious extensions by manipulating Chrome's preference files and cryptographic verification
2. **Isolated Web App (IWA) Installation** - Deploying web applications with native-like privileges through Chrome's internal databases

## Technical Deep Dive

### Chrome Extension Sideloading

#### Understanding Chrome's Security Model

Chrome uses several layers to prevent unauthorized extension installation:

**1. Preferences File Structure**
Chrome stores extension metadata in JSON files located at:
- `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Preferences`
- `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Secure Preferences`

The `Preferences` file contains basic settings, while `Secure Preferences` contains security-critical data that's cryptographically protected. Depending on which version of Windows is in use, information traditionally stored in `Secure Preferences` may instead be written into `Preferences` instead. From testing it appears that
Windows 11 Chrome can work entirely from the `Preferences` file while earlier versions require configuration
information for extensions to be stored in `Secure Preferences`.

**2. MAC (Message Authentication Code) Protection**
Chrome protects the `Secure Preferences` file using HMAC-SHA256 hashes. This ensures file integrity by:
- Computing a hash of the file contents using a machine-specific key (derived in step 3) and device ID (on Windows this is the user's SID)
- Storing this hash alongside the data
- Verifying the hash on each startup - if it doesn't match, Chrome resets the file

The input value for a hash calculation concatenates all of the inputs before hashing against the machine key. Here's an example input value to the HMAC calculation:

```
S-1-5-21-2926226500-289407501-1878376096fieebjmodjmimefnlpbfdihkehpelgcc{"account_extension_type":0,"active_permissions":{"api":["activeTab","background","clipboardRead","cookies","history","nativeMessaging","tabs","declarativeNetRequest","scripting"],"explicit_host":["\u003Call_urls>"],"scriptable_host":["\u003Call_urls>"]},"creation_flags":38,"first_install_time":"13397690747955841","from_webstore":false,"granted_permissions":{"api":["activeTab","background","clipboardRead","cookies","history","nativeMessaging","tabs","declarativeNetRequest","scripting"],"explicit_host":["\u003Call_urls>"],"scriptable_host":["\u003Call_urls>"]},"last_update_time":"13397690747955841","location":4,"newAllowFileAccess":true,"service_worker_registration_info":{"version":"1.0"},"serviceworkerevents":["runtime.onInstalled","runtime.onStartup"],"was_installed_by_default":false,"was_installed_by_oem":false,"withholding_permissions":false}
```

**3. Machine Key Extraction**
The HMAC key is stored within Chrome's `resources.pak` file, which contains compressed browser resources. DOORKNOB:
- Parses the PAK file format to locate a specific 64-byte resource
- Extracts this machine-specific key
- Uses it to generate valid HMAC signatures for modified preference files
- Technically this is identical across all chrome installs, so for now Machine Key is really just a hardcoded value.

#### The Sideloading Process

**Step 1: Chrome Discovery**
```powershell
# Locates Chrome installation and extracts the resources.pak file for Machine Key calculation
$chromePath = Get-ChromeApplicationPath
$resourcesPath = "$chromePath\resources.pak"
```

**Step 2: Machine Key + Device ID Extraction**
```powershell
# Parses PAK file structure to find the 64-byte machine key
$resourceBytes = [System.IO.File]::ReadAllBytes($ResourcePath)
$machineKey = Extract-64ByteResource($resourceBytes)
```

```powershell
$deviceId = ([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value -split '-')[0..6] -join '-'
```

**Step 3: Preference Manipulation**
The script modifies Chrome's preferences to include the malicious extension:
```json
{
  "extensions": {
    "settings": {
      "malicious_extension_id": {
        "account_extension_type": 0,
        "active_permissions": {
          "api": [
            "management",
            "system.display",
            "system.storage",
            "webstorePrivate",
            "system.cpu",
            "system.memory",
            "system.network"
          ],
          "explicit_host": [],
          "manifest_permissions": [],
          "scriptable_host": []
        },
        "app_launcher_ordinal": "t",
        "commands": {},
        ...
        "manifest": {...},
        "path": "C:\\path\\to\\extension",
        "state": 1
      }
    }
  }
}

Note that in some cases this may be in the `Preferences` file (appears to be the case on Windows 11), while in most cases
it's stored in the `Secure Preferences` file (all other Windows versions).
```

**Step 4: HMAC Regeneration**
```powershell
# Computes new HMAC for the modified file
$hmac = [System.Security.Cryptography.HMACSHA256]::new($machineKey)
$newHash = $hmac.ComputeHash($modifiedPreferences)
```

**Step 5: HMAC Insertion**
We take the MAC from Step 4, and insert it into the `protection.macs` location for the appropriate extension id.

For example, say our hash is `9773F872715710627B9986B2E953AE331CB36A1B42952D038A34876AF63DDC72` for `ahfgeienlihckogmohjhadlkjgocpleb`, we would insert it into `protection.macs.extensions.settings.ahfgeienlihckogmohjhadlkjgocpleb` as `9773F872715710627B9986B2E953AE331CB36A1B42952D038A34876AF63DDC72`.

Similar to step 3, sometimes this change is made in the `Preferences` file (in Windows 11), while it's normally
stored in `Secure Preferences` for earlier versions.

### Isolated Web App (IWA) Installation

#### Understanding IWAs

Isolated Web Apps are Chrome's mechanism for installing web applications with native-like privileges. They:
- Run in isolated contexts with enhanced permissions
- Can access system APIs normally restricted to native applications
- Are distributed as signed web bundles (`.swbn` files)

#### Chrome's Internal Storage Systems

**1. LevelDB Database**
Chrome uses LevelDB (a key-value database) to store application metadata:
- Location: `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Sync Data\LevelDB\`
- Contains IWA installation records, permissions, and metadata
- Uses binary-encoded keys and protobuf-encoded values

The `LevelDB` folder will contain a series of `.log` files, which when processed together will be treated
as the database. The powershell implementation in Doorknob assumes there is only one of these `.log` files -
we're assuming that we're working with a fresh database versus one with more keys and a longer usage timeframe.

**2. Protocol Buffers (Protobuf)**
Chrome serializes complex data structures using protobuf, Google's language-neutral serialization format:
- Compact binary encoding of structured data
- Schema-defined message formats
- Used for IWA metadata, permissions, and installation records

#### The IWA Installation Process

**Step 1: Initialize a fresh Chrome User Profile**
In order to run Chrome Isolated Web Apps, we need to enable certain flags, specifically:

```
--enable-isolated-web-app-dev-mode
--enable-isolated-web-apps
```

In order to avoid needing a special shortcut to run Chrome, we can just force these flags to load every time
by editing the `Local State` JSON file in `<CHROME PROFILE>\User Data\Local State`. We can set a handful of properties which make sure Chrome will silently launch properly:

```powershell
$jsonContent.browser = @{
    default_browser_infobar_declined_count = 1
    default_browser_infobar_last_declined_time = $currentTimeMs
    enabled_labs_experiments = @(
        "enable-isolated-web-app-dev-mode@1"
        "enable-isolated-web-apps@1"
    )
    first_run_finished = $true
}
```

Unfortunately, even though we set several UI properties, the user will still be warned every time that the 
application launches. Additionally - if Chrome has already been launched and we try to launch with these flags,
it will have no effect unless the entire app is restarted. Because of this, it actually is easier for us to create a separate user profile entirely on disk and work from there. By using the `--user-data-dir` flag, we can force Chrome to create a parallel user profile that won't affect the main Chrome installation on disk. It's very common to create new user profiles as well so even though this creates a TON of files on disk, it's still safe against inspection. The full code for this process can be found in `initializeIWAChrome.ps1`.

So we create our evil parallel user profile, modify it to enable IWAs, and then we can move onto actually sideloading. Note that the following steps will describe the literal code to invoke the relevant behavior - their implementation details can be found within the codebase for those who are curious.

**Step 2: Web Bundle Analysis**
```python
# Parses signed web bundle to extract cryptographic information
bundle_info = parse_signed_web_bundle_header(bundle_path)
public_key = bundle_info['public_key']
signature = bundle_info['signature']
```

**Step 3: Application ID Generation**
```python
# Creates Chrome-compatible app ID from public key
web_bundle_id = create_web_bundle_id_from_public_key(public_key)
app_id = get_chrome_app_id(public_key)
origin = f"isolated-app://{web_bundle_id}"
```

**Step 4: Protobuf Record Creation**
The system creates protobuf records containing:
- Application metadata (name, version, origin)
- Installation timestamp and source
- Cryptographic signatures and public keys
- Permission grants and isolation settings

For this project a base protobuf built on a legitimate application has been extracted and stored as
`app.pb`. The python code in `protobufUpdater.py` opens this file, then makes all the appropriate
changes based on our generated signed web bundle to make sure that loading proceeds as desired.

**Step 5: LevelDB Injection**
```python
# Directly writes protobuf data to Chrome's LevelDB
db_key = generate_leveldb_key(app_id)
protobuf_data = serialize_app_metadata(app_info)
leveldb_write(db_path, db_key, protobuf_data)
```

**Step 6: Opening the Application Stealthily**

Chrome Isolated Web Apps are run from the legacy Chrome Apps interface at `chrome://apps`. This normally
requires the user to navigate to the page and click an icon which will launch the application in its own
window. There are several problems here, for our purposes:

1. It requires user interaction
2. It opens a visible window

Luckily for us, there is a flag built into chrome for launching Chrome Apps, `-app-id`. We run chrome (along with several other flags for performance) that help minimize its profile. Note that we also specify our `--user-data-dir` flag from step 1.

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --allow-no-sandbox-job --disable-3d-apis --disable-gpu --disable-d3d11 --disable-accelerated-layers --disable-accelerated-plugins --disable-accelerated-2d-canvas --disable-deadline-scheduling --disable-ui-deadline-scheduling --aura-no-shadows --user-data-dir="C:\Users\localuser\AppData\Local\com.chrome.alone" --profile-directory=Default --app-id=gckefbcfobglggkfpcigmmjaekledman
```

This solves part of the issue, but we still get a visible window. This is where we rely on a tried and true red teaming tactic - [Hidden Desktop abuse](https://github.com/WKL-Sec/HiddenDesktop). Essentially we invoke specific Windows APIs to create a new Desktop handle which isn't shown to the user, then when we invoke process creation APIs, we pass in the alternate handle so the user isn't shown the window. This works perfectly for our purposes. The code we use for this can be seen in `startIWAApp.ps1`.

**Step 7: Add the application to run on startup**

Unlike Chrome extensions, which we can simply apply `background` permissions to in order to guarantee running on startup - there is no default mechanism to run Chrome Apps that will perform everything we need in step 6. This means that we need to add `startIWAApp.ps1` to our startup process. There are a myriad of ways to enable persistence, but for this release we have chosen to update the `Microsoft\Windows\CurrentVersion\Run` key to run our app. 

## EDR Detection Signatures

### Runtime File System Activities

#### Chrome Preference File Tampering
```yaml
rule: DOORKNOB_Runtime_Preference_Manipulation
events:
  - file_modification:
      file_path:
        - "*\\Google\\Chrome\\User Data\\Default\\Preferences"
        - "*\\Google\\Chrome\\User Data\\Default\\Secure Preferences"
      process_name_not:
        - chrome.exe
        - msedge.exe
      access_type: WRITE
    followed_by:
      - process_creation:
          process_name: chrome.exe
          within: 60s
```

#### LevelDB Database Tampering
```yaml
rule: DOORKNOB_Runtime_LevelDB_Manipulation
events:
  - file_access:
      file_path_contains:
        - "\\Chrome\\User Data\\Default\\Sync Data\\"
        - "\\LevelDB\\"
      file_extension:
        - ".ldb"
        - ".log"
      process_name_not: chrome.exe
      access_type: WRITE
```