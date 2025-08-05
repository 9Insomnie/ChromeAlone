import hashlib
import base64
import urllib.parse

def hex_to_chrome_alphabet(hex_string):
    """Convert hex string to Chrome's a-p alphabet."""
    result = ""
    for hex_char in hex_string:
        val = int(hex_char, 16)
        result += chr(val + ord('a'))
    return result

def generate_id_from_hash(hash_bytes):
    """Generate Chrome extension ID from first 16 bytes of hash."""
    first_16_bytes = hash_bytes[:16]
    hex_string = ''.join([f'{b:02x}' for b in first_16_bytes])
    return hex_to_chrome_alphabet(hex_string)

def create_web_bundle_id_from_public_key(public_key_bytes):
    """Create a web bundle ID from an Ed25519 public key."""
    # Add the type suffix for Ed25519 (0x00, 0x01, 0x02)
    type_suffix = bytes([0x00, 0x01, 0x02])
    full_id = public_key_bytes + type_suffix
    # Base32 encode without padding and convert to lowercase
    encoded_id = base64.b32encode(full_id).decode('ascii').lower().rstrip('=')
    return encoded_id

def get_chrome_app_id(public_key_base64):
    """Generate Chrome app ID from base64-encoded public key."""
    # Decode base64 public key
    public_key_bytes = base64.b64decode(public_key_base64)
    
    # Create web bundle ID
    web_bundle_id = create_web_bundle_id_from_public_key(public_key_bytes)
    
    # Create manifest ID (the origin URL with trailing slash)
    manifest_id = f"isolated-app://{web_bundle_id}/"
    
    # First hash - generate manifest ID hash
    manifest_id_hash = hashlib.sha256()
    manifest_id_hash.update(manifest_id.encode('utf-8'))
    first_hash = manifest_id_hash.digest()
    
    # Second hash - generate final app ID
    app_id_hash = hashlib.sha256()
    app_id_hash.update(first_hash)
    second_hash = app_id_hash.digest()
    
    return generate_id_from_hash(second_hash)

def main():
    # Test with the provided public key
    public_key = "kWvk3oUYfDR//zE9nJhA8CgIMulCPzXrWkMpXWRxp+g="
    
    web_bundle_id = create_web_bundle_id_from_public_key(base64.b64decode(public_key))
    print(f"Public Key (base64): {public_key}")
    print(f"Web Bundle ID: {web_bundle_id}")
    
    manifest_id = f"isolated-app://{web_bundle_id}/"
    print(f"Manifest ID: {manifest_id}")
    
    app_id = get_chrome_app_id(public_key)
    print(f"Generated App ID: {app_id}")
    print(f"LevelDB Key: web_apps-dt-{app_id}")

if __name__ == "__main__":
    main()