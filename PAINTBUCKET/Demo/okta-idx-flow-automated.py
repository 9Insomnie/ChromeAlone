import requests
import json
import re
import base64
import time
from urllib.parse import unquote, urlparse, parse_qs
from config import (
    OKTA_DOMAIN, OKTA_BASE_URL, USERNAME, PASSWORD,
    VAULT_BASE_URL, VAULT_REDIRECT_URI,
    BATTLEPLAN_BASE_URL, BATTLEPLAN_AUTH,
    AGENT_IP
)

def make_webauthn_request(request, domain):
    
    """
    Automate the WebAuthn request flow:
    1. Create task
    2. Poll for completion
    3. Return result.response
    
    Args:
        request (str): Base64-encoded WebAuthn request
        domain (str): Domain for the WebAuthn request
    """
    
    # Headers for all requests
    headers = {
        "Authorization": f"Basic {BATTLEPLAN_AUTH}",
        "Content-Type": "application/json"
    }
    
    # Step 1: Create the WebAuthn task
    print("Creating WebAuthn task... for properties:")
    print(f"domain: {domain}")
    print(f"request: {request}")
    
    payload = {
        "command": "webauthn",
        "payload": json.dumps({
            "domain": domain,
            "request": request
        }),
        "agentIp": AGENT_IP
    }
    
    try:
        response = requests.post(
            f"{BATTLEPLAN_BASE_URL}/command",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        # Extract taskId from response
        task_data = response.json()
        task_id = task_data.get("taskId")
        
        if not task_id:
            print("Error: No taskId received in response")
            print(f"Response: {task_data}")
            return None
            
        print(f"Task created successfully. TaskId: {task_id}")
        print(f"Status: {task_data.get('status')}")
        
    except requests.exceptions.RequestException as e:
        print(f"Error creating task: {e}")
        return None
    
    # Step 2: Poll for task completion
    print("Polling for task completion...")
    
    poll_url = f"{BATTLEPLAN_BASE_URL}/task/{task_id}"
    max_attempts = 60  # Maximum 5 minutes of polling (60 * 5 seconds)
    attempt = 0
    
    while attempt < max_attempts:
        try:
            poll_response = requests.get(poll_url, headers=headers)
            poll_response.raise_for_status()
            
            poll_data = poll_response.json()
            status = poll_data.get("status")
            
            print(f"Attempt {attempt + 1}: Status = {status}")
            
            # Check if we have a result
            if "result" in poll_data and poll_data["result"]:
                print("Task completed! Processing result...")
                
                # Parse the result (it's a JSON string)
                try:
                    result_data = json.loads(poll_data["result"])
                    response_data = result_data.get("response")
                    
                    if response_data:
                        print("\n" + "="*50)
                        print("RESULT.RESPONSE:")
                        print("="*50)
                        print(json.dumps(response_data, indent=2))
                        return response_data
                    else:
                        print("Error: No response field found in result")
                        print(f"Full result: {result_data}")
                        return None
                        
                except json.JSONDecodeError as e:
                    print(f"Error parsing result JSON: {e}")
                    print(f"Raw result: {poll_data['result']}")
                    return None
            
            # Check if task failed
            if status == "failed":
                print("Task failed!")
                print(f"Full response: {poll_data}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error polling task: {e}")
            
        # Wait 5 seconds before next poll
        time.sleep(5)
        attempt += 1
    
    print("Max polling attempts reached. Task may still be running.")
    return None

def format_idx_webauthn_challenge_for_browser(challenge_data):
    """Convert IDX WebAuthn challenge response to browser-compatible format and encode as base64"""
    
    # Extract challenge data from IDX response
    current_auth = challenge_data.get('currentAuthenticator', {}).get('value', {})
    challenge_info = current_auth.get('contextualData', {}).get('challengeData', {})
    
    challenge = challenge_info.get('challenge')
    user_verification = challenge_info.get('userVerification', 'preferred')
    
    if not challenge:
        raise ValueError("No challenge found in IDX response")
    
    print(f"🔑 Challenge: {challenge}")
    print(f"👤 User verification: {user_verification}")
    
    # Find the WebAuthn credential ID from authenticatorEnrollments
    enrollments = challenge_data.get('authenticatorEnrollments', {}).get('value', [])
    credential_id = None
    
    for enrollment in enrollments:
        if (enrollment.get('key') == 'webauthn' and 
            enrollment.get('type') == 'security_key' and 
            'credentialId' in enrollment):
            credential_id = enrollment['credentialId']
            print(f"🔐 Found credential ID: {credential_id}")
            break
    
    if not credential_id:
        raise ValueError("No WebAuthn credential ID found in response")
    
    # Extract rpId from the challenge URL (assuming it's trial-9881677.okta.com)
    rp_id = OKTA_DOMAIN
    
    # Format for navigator.credentials.get()
    webauthn_request = {
        "publicKey": {
            "challenge": challenge,  # Keep as base64url string - JS will convert
            "timeout": 60000,  # 60 seconds timeout
            "rpId": rp_id,
            "allowCredentials": [
                {
                    "type": "public-key",
                    "id": credential_id,  # Keep as base64url string - JS will convert
                    "transports": ["usb", "nfc", "ble", "hybrid"]
                }
            ],
            "userVerification": user_verification
        }
    }
    
    # Convert to JSON string
    json_string = json.dumps(webauthn_request)
    
    # Encode as base64
    encoded_string = base64.b64encode(json_string.encode('utf-8')).decode('utf-8')
    
    # Extract stateHandle for later use
    state_handle = challenge_data.get('stateHandle')
    
    # Get the answer URL from remediation
    answer_url = None
    remediation = challenge_data.get('remediation', {}).get('value', [])
    for remedy in remediation:
        if remedy.get('name') == 'challenge-authenticator':
            answer_url = remedy.get('href')
            break
    
    if not answer_url:
        raise ValueError("No challenge-authenticator URL found in response")
    
    verification_data = {
        "stateHandle": state_handle,
        "answerUrl": answer_url
    }
    
    return {
        "encoded_webauthn_options": encoded_string,
        "verification_data": verification_data
    }

def submit_idx_webauthn_response_to_okta(session, verification_data, webauthn_response):
    """Submit WebAuthn response to IDX challenge/answer endpoint"""
    
    # The IDX API expects the response in a specific format
    payload = {
        "credentials": {
            "clientData": webauthn_response['clientDataJSON'],
            "authenticatorData": webauthn_response['authenticatorData'],
            "signatureData": webauthn_response['signature']  # Note: IDX uses 'signatureData', not 'signature'
        },
        "stateHandle": verification_data['stateHandle']
    }
    
    # Include userHandle if present
    if 'userHandle' in webauthn_response and webauthn_response['userHandle']:
        payload['credentials']['userHandle'] = webauthn_response['userHandle']
        print(f"📎 Including userHandle: {webauthn_response['userHandle']}")
    
    headers = {
        "Accept": "application/json; okta-version=1.0.0",
        "Accept-Language": "en",
        "Content-Type": "application/json",
        "X-Okta-User-Agent-Extended": "okta-auth-js/7.11.0 okta-signin-widget-7.33.0",
        # "X-Device-Fingerprint": "vp7_x0b0dbi95vQeXg22pytWveCYiF1x|9aa6534f76ae4b035eb4fdb3bf11dda5faa1e765638735cceee34f35192168d4|244149bc78cafdb571d6fd63add4f442",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Origin": OKTA_BASE_URL,
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    print(f"🔗 Submitting to: {verification_data['answerUrl']}")
    print(f"📝 Payload structure:")
    print(f"   credentials.clientData length: {len(webauthn_response['clientDataJSON'])} chars")
    print(f"   credentials.authenticatorData length: {len(webauthn_response['authenticatorData'])} chars") 
    print(f"   credentials.signatureData length: {len(webauthn_response['signature'])} chars")
    print(f"   stateHandle: {verification_data['stateHandle'][:50]}...")
    
    # Debug: decode and show clientData
    try:
        client_data_decoded = base64.b64decode(webauthn_response['clientDataJSON']).decode('utf-8')
        client_data_json = json.loads(client_data_decoded)
        print(f"🔍 Decoded clientData:")
        print(f"   type: {client_data_json.get('type')}")
        print(f"   challenge: {client_data_json.get('challenge')}")
        print(f"   origin: {client_data_json.get('origin')}")
    except Exception as e:
        print(f"⚠️ Could not decode clientData: {e}")
    
    print(f"\n📡 Making POST request to {verification_data['answerUrl']}")
    
    response = session.post(
        verification_data['answerUrl'],
        headers=headers,
        json=payload
    )
    
    print(f"📡 Response status: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Error response: {response.text}")
        response.raise_for_status()
    
    result = response.json()
    
    print(f"🔍 Response details:")
    print(f"   Status: {result.get('status')}")
    if 'intent' in result:
        print(f"   Intent: {result.get('intent')}")
    
    return result

def handle_success_redirect(session, webauthn_result):
    """Handle the success redirect URL to complete the OAuth2 flow"""
    
    # Check if we have a success redirect
    success_data = webauthn_result.get('success', {})
    redirect_url = success_data.get('href')
    
    if not redirect_url:
        print("❌ No success redirect URL found in response")
        return None
    
    print(f"🔗 Found success redirect URL: {redirect_url}")
    
    # Make a GET request to the redirect URL while maintaining session
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "TE": "trailers"
    }
    
    print(f"🌐 Making GET request to redirect URL...")
    print(f"   URL: {redirect_url}")
    print(f"   Session cookies: {len(session.cookies)} cookies")
    
    # Log current cookies for debugging
    for cookie in session.cookies:
        print(f"   Cookie: {cookie.name}={cookie.value[:20]}...")
    
    # Specifically check for important cookies
    dt_cookie = None
    jsessionid_cookie = None
    ln_cookie = None
    
    for cookie in session.cookies:
        if cookie.name == 'DT':
            dt_cookie = cookie.value
        elif cookie.name == 'JSESSIONID':
            jsessionid_cookie = cookie.value
        elif cookie.name == 'ln':
            ln_cookie = cookie.value
    
    print(f"📋 Important cookies status:")
    print(f"   DT cookie: {'✅ Present' if dt_cookie else '❌ Missing'}")
    print(f"   JSESSIONID: {'✅ Present' if jsessionid_cookie else '❌ Missing'}")
    
    if dt_cookie:
        print(f"   DT value: {dt_cookie[:30]}{'...' if len(dt_cookie) > 30 else ''}")
    
    if not dt_cookie:
        print("⚠️ WARNING: DT cookie is missing! This may cause issues with the final redirect.")
        print("   The DT cookie should have been set during the initial auth URL request.")
    
    response = session.get(redirect_url, headers=headers, allow_redirects=True)
    
    print(f"📡 Redirect response status: {response.status_code}")
    print(f"🔗 Final URL after redirects: {response.url}")
    
    # Check if we got redirected to the Vault callback
    if "vault/auth/oidc/oidc/callback" in response.url:
        print("✅ Successfully redirected to Vault callback!")
        print(f"📋 Final callback URL: {response.url}")
        
        # Extract any query parameters from the final URL
        parsed_url = urlparse(response.url)
        query_params = parse_qs(parsed_url.query)
        
        if 'code' in query_params:
            auth_code = query_params['code'][0]
            print(f"🎯 Authorization code received: {auth_code[:20]}...")
            
            if 'state' in query_params:
                state = query_params['state'][0]
                print(f"🔐 State parameter: {state}")
            
            # Step 9: Complete Vault authentication to get client token
            vault_result = complete_vault_authentication(response.url)
            
            if vault_result and vault_result.get('success'):
                return {
                    'success': True,
                    'authorization_code': auth_code,
                    'state': query_params.get('state', [None])[0],
                    'callback_url': response.url,
                    'final_response': response,
                    'vault_result': vault_result,
                    'client_token': vault_result['client_token'],
                    'accessor': vault_result['accessor'],
                    'policies': vault_result['policies'],
                    'lease_duration': vault_result['lease_duration']
                }
            else:
                print("❌ Failed to complete Vault authentication")
                # Still return the authorization code in case manual completion is needed
                return {
                    'success': False,
                    'authorization_code': auth_code,
                    'state': query_params.get('state', [None])[0],
                    'callback_url': response.url,
                    'final_response': response,
                    'vault_error': 'Failed to complete Vault authentication'
                }
        else:
            print("⚠️ No authorization code found in callback URL")
            print(f"Query parameters: {query_params}")
    else:
        print(f"⚠️ Unexpected redirect destination: {response.url}")
    
    # Return response details for debugging
    return {
        'success': False,
        'final_url': response.url,
        'status_code': response.status_code,
        'response': response
    }

def complete_vault_authentication(callback_url):
    """Make the final callback request to Vault to get the client token"""
    
    print(f"🔐 Step 9: Completing Vault authentication...")
    print(f"📞 Extracting parameters from callback URL: {callback_url}")
    
    # Extract the host and parameters from the callback URL
    parsed_callback = urlparse(callback_url)
    vault_host = parsed_callback.netloc
    query_params = parse_qs(parsed_callback.query)
    
    # Extract code and state parameters
    code = query_params.get('code', [None])[0]
    state = query_params.get('state', [None])[0]
    
    if not code or not state:
        print(f"❌ Missing required parameters: code={code}, state={state}")
        return None
    
    print(f"📋 Extracted parameters:")
    print(f"   Code: {code[:20]}...")
    print(f"   State: {state}")
    
    # Construct the proper Vault API endpoint
    vault_api_url = f"https://{vault_host}/v1/auth/oidc/oidc/callback?code={code}&state={state}"
    print(f"🎯 Making request to Vault API: {vault_api_url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": f"https://{vault_host}/ui/vault/auth",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=4",
        "TE": "trailers"
    }
    
    # Create a new session for the Vault API call (different domain)
    vault_session = requests.Session()
    
    # Set the abuse_interstitial cookie if needed
    vault_session.cookies.set('abuse_interstitial', vault_host)
    
    try:
        response = vault_session.get(vault_api_url, headers=headers)
        
        print(f"📡 Vault API response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Error from Vault API: {response.text}")
            return None
        
        # Parse the JSON response
        vault_response = response.json()
        
        print("✅ Vault API callback successful!")
        
        # Extract the client token
        auth_data = vault_response.get('auth', {})
        client_token = auth_data.get('client_token')
        
        if client_token:
            print(f"🎯 Client token obtained: {client_token[:20]}...")
            
            # Also extract other useful info
            accessor = auth_data.get('accessor')
            policies = auth_data.get('policies', [])
            lease_duration = auth_data.get('lease_duration')
            
            print(f"📋 Vault authentication details:")
            print(f"   Accessor: {accessor[:20]}..." if accessor else "   Accessor: None")
            print(f"   Policies: {policies}")
            print(f"   Lease duration: {lease_duration} seconds" if lease_duration else "   Lease duration: Unknown")
            
            return {
                'success': True,
                'client_token': client_token,
                'accessor': accessor,
                'policies': policies,
                'lease_duration': lease_duration,
                'full_response': vault_response,
                'api_url': vault_api_url
            }
        else:
            print("❌ No client token found in Vault response")
            print(f"Full response: {json.dumps(vault_response, indent=2)}")
            return None
            
    except Exception as e:
        print(f"❌ Error making Vault API request: {e}")
        return None

def automate_okta_login():
    #     # Step 1: Get the auth URL from Vault
    vault_url = f"{VAULT_BASE_URL}/v1/auth/oidc/oidc/auth_url"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Origin": VAULT_BASE_URL,
        "Referer": f"{VAULT_BASE_URL}/ui/vault/auth",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    payload = {
        "role": "",
        "redirect_uri": VAULT_REDIRECT_URI
    }
    
    print("Step 1: Getting auth URL from Vault...")
    response = requests.post(vault_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error getting auth URL: {response.status_code}")
        return None
    
    auth_data = response.json()
    auth_url = auth_data['data']['auth_url']
    print(f"🔑 Using auth URL: {auth_url}")
    # auth_url = "https://trial-9881677.okta.com/oauth2/default/v1/authorize?client_id=0oat1yhqlmzIGmadU697&code_challenge=1zyhQgGtPym7ahgutC3VwqcmLjAGyyh5TRn_XvLj-RE&code_challenge_method=S256&nonce=n_PQTE41dZpZsBBo4XFLBE&redirect_uri=https%3A%2F%2F76abb9d6a38b.ngrok-free.app%2Fui%2Fvault%2Fauth%2Foidc%2Foidc%2Fcallback&response_type=code&scope=openid+profile+email&state=st_rHBr28pzMMIugUtI0ABM"
    print(f"Got auth URL: {auth_url}")
    
    # Step 2: Follow the auth URL to get the state token
    print("\nStep 2: Following auth URL to get state token...")
    
    # Create a session early to preserve all cookies including DT
    session = requests.Session()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Referer": f"{VAULT_BASE_URL}/",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1"
    }
    
    response = session.get(auth_url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error following auth URL: {response.status_code}")
        return None
    
    # Debug: Show cookies received from auth URL
    print(f"📋 Cookies received from auth URL ({len(session.cookies)} total):")
    for cookie in session.cookies:
        print(f"   {cookie.name}={cookie.value[:30]}{'...' if len(cookie.value) > 30 else ''}")
    
    # Extract state token from the response
    state_token = extract_state_token(response.text)
    
    if not state_token:
        print("Could not extract state token from response")
        return None
    
    print(f"Extracted state token: {state_token[:50]}...")
    
    # Step 3: Call the introspect endpoint
    print("\nStep 3: Calling introspect endpoint...")
    
    introspect_url = f"{OKTA_BASE_URL}/idp/idx/introspect"
    
    headers = {
        "Accept": "application/ion+json; okta-version=1.0.0",
        "Accept-Language": "en",
        "Content-Type": "application/ion+json; okta-version=1.0.0",
        "X-Okta-User-Agent-Extended": "okta-auth-js/7.11.0 okta-signin-widget-7.33.0",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Origin": OKTA_BASE_URL,
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    payload = {
        "stateToken": state_token
    }
    
    # Debug: Show cookies before introspect request
    print(f"📋 Cookies before introspect ({len(session.cookies)} total):")
    for cookie in session.cookies:
        print(f"   {cookie.name}={cookie.value[:20]}...")
    
    response = session.post(introspect_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error calling introspect: {response.status_code}")
        print(f"Response: {response.text}")
        return None
    
    print("Successfully called introspect endpoint!")
    introspect_data = response.json()
    
    # Step 4: Call the identify endpoint with credentials
    print("\nStep 4: Calling identify endpoint with credentials...")
    
    identify_url = f"{OKTA_BASE_URL}/idp/idx/identify"
    
    # Extract the new stateHandle from introspect response
    state_handle = introspect_data.get('stateHandle')
    
    headers = {
        "Accept": "application/json; okta-version=1.0.0",
        "Accept-Language": "en",
        "Content-Type": "application/json",
        "X-Okta-User-Agent-Extended": "okta-auth-js/7.11.0 okta-signin-widget-7.33.0",
        # "X-Device-Fingerprint": "vp7_x0b0dbi95vQeXg22pytWveCYiF1x|9aa6534f76ae4b035eb4fdb3bf11dda5faa1e765638735cceee34f35192168d4|244149bc78cafdb571d6fd63add4f442",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0",
        "Origin": OKTA_BASE_URL,
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    
    # Hardcoded credentials as requested
    payload = {
        "identifier": USERNAME,
        "credentials": {
            "passcode": PASSWORD
        },
        "stateHandle": state_handle
    }
    
    response = session.post(identify_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error calling identify: {response.status_code}")
        print(f"Response: {response.text}")
        return None
    
    print("Successfully called identify endpoint!")
    identify_data = response.json()
    
    # Step 5: Call the challenge endpoint for webauthn
    print("\nStep 5: Calling challenge endpoint for webauthn...")
    
    challenge_url = f"{OKTA_BASE_URL}/idp/idx/challenge"
    
    # Extract webauthn authenticator ID from the identify response
    webauthn_auth_id = extract_webauthn_authenticator_id(identify_data)
    
    if not webauthn_auth_id:
        print("Could not find webauthn authenticator ID in response")
        return None
    
    print(f"Found webauthn authenticator ID: {webauthn_auth_id}")
    
    # Update stateHandle from identify response
    state_handle = identify_data.get('stateHandle')
    
    payload = {
        "authenticator": {
            "id": webauthn_auth_id
        },
        "stateHandle": state_handle
    }
    
    response = session.post(challenge_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error calling challenge: {response.status_code}")
        print(f"Response: {response.text}")
        return None
    
    print("Successfully called challenge endpoint!")
    challenge_data = response.json()
    
    # Step 6: Format the WebAuthn challenge for the browser
    print("\nStep 6: Formatting WebAuthn challenge for browser...")
    
    try:
        formatted_challenge = format_idx_webauthn_challenge_for_browser(challenge_data)

        webauthn_response = make_webauthn_request(formatted_challenge['encoded_webauthn_options'], OKTA_DOMAIN)
        
        if webauthn_response:
            print("✅ WebAuthn response received!")
            print(f"Response: {webauthn_response}")
        else:
            print("❌ No webauthn response received")
            return None
        
        # Validate required fields
        required_fields = ['clientDataJSON', 'authenticatorData', 'signature']
        missing_fields = [field for field in required_fields if field not in webauthn_response]
        
        print("✅ Valid WebAuthn response received!")
        print(f"Response keys: {list(webauthn_response.keys())}")
        
        # Step 7: Submit to Okta IDX
        print("\n🔄 Submitting WebAuthn response to Okta IDX...")
        final_result = submit_idx_webauthn_response_to_okta(
            session, 
            formatted_challenge['verification_data'], 
            webauthn_response
        )
        
        print("🎉 WebAuthn authentication complete!")
        
        # Step 8: Handle the success redirect to complete OAuth2 flow
        print("\n🔄 Step 8: Following success redirect to complete OAuth2 flow...")
        
        if final_result.get('intent') == 'LOGIN' and 'success' in final_result:
            redirect_result = handle_success_redirect(session, final_result)
            
            if redirect_result and redirect_result.get('success'):
                print("🎉 OAuth2 flow completed successfully!")
                print(f"🔑 Authorization code: {redirect_result['authorization_code'][:20]}...")
                
                # Check if we got the final client token - if so, we're completely done!
                if 'client_token' in redirect_result:
                    print("🎉 Vault authentication completed successfully!")
                    
                    print("\n" + "="*60)
                    print("🏆 ULTIMATE SUCCESS: VAULT CLIENT TOKEN OBTAINED!")
                    print("="*60)
                    print(f"🔑 Client Token: {redirect_result['client_token']}")
                    
                    if 'accessor' in redirect_result and redirect_result['accessor']:
                        print(f"🆔 Accessor: {redirect_result['accessor']}")
                    if 'policies' in redirect_result and redirect_result['policies']:
                        print(f"📋 Policies: {redirect_result['policies']}")
                    if 'lease_duration' in redirect_result and redirect_result['lease_duration']:
                        print(f"⏰ Lease Duration: {redirect_result['lease_duration']} seconds")
                    
                    print("\n✅ Authentication flow complete! You can now use this client token with Vault.")
                    print("="*60)
                    
                    # Return immediately with complete success - no need to continue!
                    return {
                        'session': session,
                        'introspect_data': introspect_data,
                        'identify_data': identify_data,
                        'challenge_data': challenge_data,
                        'webauthn_result': final_result,
                        'oauth2_result': redirect_result,
                        'state_token': state_token,
                        'webauthn_auth_id': webauthn_auth_id,
                        'authorization_code': redirect_result['authorization_code'],
                        'vault_callback_url': redirect_result['callback_url'],
                        'client_token': redirect_result.get('client_token'),
                        'accessor': redirect_result.get('accessor'),
                        'policies': redirect_result.get('policies'),
                        'lease_duration': redirect_result.get('lease_duration'),
                        'vault_result': redirect_result.get('vault_result'),
                        'complete_success': True
                    }
                
                # If no client token yet, continue with normal flow
                print("🔄 Continuing authentication flow...")
                
                # Update return data with complete flow result
                return {
                    'session': session,
                    'introspect_data': introspect_data,
                    'identify_data': identify_data,
                    'challenge_data': challenge_data,
                    'webauthn_result': final_result,
                    'oauth2_result': redirect_result,
                    'state_token': state_token,
                    'webauthn_auth_id': webauthn_auth_id,
                    'authorization_code': redirect_result['authorization_code'],
                    'vault_callback_url': redirect_result['callback_url'],
                    'client_token': redirect_result.get('client_token'),
                    'accessor': redirect_result.get('accessor'),
                    'policies': redirect_result.get('policies'),
                    'lease_duration': redirect_result.get('lease_duration'),
                    'vault_result': redirect_result.get('vault_result')
                }
            else:
                print("⚠️ OAuth2 redirect flow encountered issues")
                if redirect_result:
                    print(f"Final URL: {redirect_result.get('final_url')}")
                    print(f"Status: {redirect_result.get('status_code')}")
        else:
            print("⚠️ No success redirect available - authentication may not be complete")
        
        # Update return data with final result
        return {
            'session': session,
            'introspect_data': introspect_data,
            'identify_data': identify_data,
            'challenge_data': challenge_data,
            'webauthn_result': final_result,
            'state_token': state_token,
            'webauthn_auth_id': webauthn_auth_id
        }
                    
    except Exception as e:
        print(f"❌ Error formatting WebAuthn challenge: {e}")
        print("Returning challenge data for manual processing...")
        return {
            'session': session,
            'introspect_data': introspect_data,
            'identify_data': identify_data,
            'challenge_data': challenge_data,
            'state_token': state_token,
            'webauthn_auth_id': webauthn_auth_id
        }
    
    return {
        'session': session,
        'introspect_data': introspect_data,
        'identify_data': identify_data,
        'challenge_data': challenge_data,
        'state_token': state_token,
        'webauthn_auth_id': webauthn_auth_id
    }

def extract_webauthn_authenticator_id(identify_data):
    """
    Extract the webauthn authenticator ID from the identify response.
    """
    try:
        # Look for authenticators in the response
        authenticators = identify_data.get('authenticators', {}).get('value', [])
        
        for auth in authenticators:
            if auth.get('key') == 'webauthn' and auth.get('type') == 'security_key':
                return auth.get('id')
        
        # Also check in authenticatorEnrollments if not found in authenticators
        enrollments = identify_data.get('authenticatorEnrollments', {}).get('value', [])
        
        for enrollment in enrollments:
            if enrollment.get('key') == 'webauthn' and enrollment.get('type') == 'security_key':
                return enrollment.get('id')
        
        # Check in remediation options as well
        remediation = identify_data.get('remediation', {}).get('value', [])
        
        for remedy in remediation:
            if remedy.get('name') == 'select-authenticator-authenticate':
                auth_options = remedy.get('value', [])
                for option in auth_options:
                    if option.get('name') == 'authenticator':
                        options = option.get('options', [])
                        for opt in options:
                            if opt.get('label') == 'Security Key or Biometric':
                                form_values = opt.get('value', {}).get('form', {}).get('value', [])
                                for form_val in form_values:
                                    if form_val.get('name') == 'id':
                                        return form_val.get('value')
        
        return None
    except Exception as e:
        print(f"Error extracting webauthn authenticator ID: {e}")
        return None

def extract_state_token(html_content):
    """
    Extract the state token from the HTML response.
    Handles the \x2D encoding and converts it to regular hyphens.
    """
    # Look for the stateToken variable in the HTML
    patterns = [
        r'var stateToken = [\'"]([^\'"]*)[\'"]',
        r'stateToken[\'"]?\s*[:=]\s*[\'"]([^\'"]*)[\'"]',
        r'stateToken\s*=\s*[\'"]([^\'"]*)[\'"]'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            token = match.group(1)
            # Replace \x2D with hyphens
            token = token.replace('\\x2D', '-')
            # Also handle URL encoding if present
            token = unquote(token)
            return token
    
    return None

if __name__ == "__main__":

    print(f"🔑 Using BATTLEPLAN_BASE_URL: {BATTLEPLAN_BASE_URL}")
    print(f"🔑 Using BATTLEPLAN_AUTH: {BATTLEPLAN_AUTH}")
    print(f"🔑 Using AGENT_IP: {AGENT_IP}")

    result = automate_okta_login()
    
    if result:
        # Check if we already completed everything successfully
        if result.get('complete_success'):
            print("\n🎊 Program completed successfully!")
            print("All authentication steps have been completed and the client token has been obtained.")
            available_data = list(result.keys())
            print(f"Available data: {', '.join(available_data)}")
        else:
            print("\n" + "="*50)
            print("SUCCESS: Workflow completed successfully!")
            
            if 'webauthn_result' in result:
                print("✅ WebAuthn authentication completed!")
                webauthn_result = result['webauthn_result']
                
                # Check if we have a session token or authorization success
                if webauthn_result.get('intent') == 'LOGIN':
                    print("🎯 Authentication successful - user is now logged in!")
                    
                    # Check for the final client token (most important result)
                    if 'client_token' in result and result['client_token']:
                        print("\n" + "="*60)
                        print("🏆 ULTIMATE SUCCESS: VAULT CLIENT TOKEN OBTAINED!")
                        print("="*60)
                        print(f"🔑 Client Token: {result['client_token']}")
                        
                        if 'accessor' in result and result['accessor']:
                            print(f"🆔 Accessor: {result['accessor']}")
                        if 'policies' in result and result['policies']:
                            print(f"📋 Policies: {result['policies']}")
                        if 'lease_duration' in result and result['lease_duration']:
                            print(f"⏰ Lease Duration: {result['lease_duration']} seconds")
                        
                        print("\n✅ You can now use this client token to authenticate with Vault!")
                        print("="*60)
                    # Check for OAuth2 completion
                    elif 'oauth2_result' in result and result['oauth2_result'].get('success'):
                        print("🚀 OAuth2 flow completed successfully!")
                        print(f"🔑 Authorization code: {result['authorization_code'][:20]}...")
                        print(f"🔗 Vault callback URL: {result['vault_callback_url']}")
                        if result['oauth2_result'].get('vault_error'):
                            print(f"⚠️ Vault authentication error: {result['oauth2_result']['vault_error']}")
                            print("💡 You may need to manually complete the Vault callback")
                    elif 'authorization_code' in result:
                        print(f"🔑 Authorization code: {result['authorization_code'][:20]}...")
                    else:
                        print("⚠️ OAuth2 flow may be incomplete")
                    
                    # Check for session tokens or continuation URLs
                    if 'sessionToken' in webauthn_result:
                        print(f"🔑 Session token available: {webauthn_result['sessionToken'][:20]}...")
                    
                    # Look for success state or next steps
                    if webauthn_result.get('success'):
                        print("🎉 Authentication flow has success redirect available!")
                    elif 'remediation' in webauthn_result:
                        print("➡️ Additional steps may be available in remediation")
                    
                    if 'oauth2_result' not in result:
                        print(f"\n📋 WebAuthn authentication result:")
                        print(json.dumps({k: v for k, v in webauthn_result.items() if k != 'stateHandle'}, indent=2))
                else:
                    print(f"ℹ️ Authentication status: {webauthn_result.get('intent', 'Unknown')}")
            else:
                print("⚠️ WebAuthn authentication was not completed")
            
            print("You can now use the session and response data for next steps.")
            available_data = list(result.keys())
            print(f"Available data: {', '.join(available_data)}")
            print("="*50)
    else:
        print("\n" + "="*50)
        print("FAILED: Workflow did not complete successfully.")
        print("="*50)