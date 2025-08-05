import binascii
import base64
import os
import re
import json

def extract_manifest_from_bundle(bundle_path: str):
    """Read and parse the manifest file from within the .swbn bundle."""
    if not os.path.exists(bundle_path):
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")
    
    with open(bundle_path, 'rb') as f:
        bundle_data = f.read()
    
    # Convert binary data to string for regex matching
    bundle_str = None
    for encoding in ['utf-8', 'latin-1', 'cp1252']:
        try:
            bundle_str = bundle_data.decode(encoding, errors='ignore')
            break
        except UnicodeDecodeError:
            continue
    
    if bundle_str is None:
        raise ValueError("Could not decode bundle file with any supported encoding")
    
    # Look for JSON objects that contain fields and end with two newling separated }s
    # TODO: This is a hack to get the manifest. It's not a good solution.
    manifest_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(manifest_pattern, bundle_str, re.DOTALL)
    
    # Try to parse each match as JSON
    for match in matches:
        try:
            cleaned_match = re.sub(r'[^\x20-\x7E]', '', match)
            manifest = json.loads(cleaned_match)
            
            if 'name' in manifest and 'version' in manifest:
                return manifest
        except (json.JSONDecodeError, KeyError):
            continue
    
    raise ValueError("Could not find valid manifest JSON in bundle file")
        

def parse_signed_web_bundle_header(file_path: str):
    with open(file_path, 'rb') as f:
        # First byte 0x84 indicates a CBOR array of 4 elements
        # Then magic bytes "🖋📦" (F0 9F 96 8B F0 9F 93 A6)
        # Then version "2b\0\0" (44 32 62 00 00)
        # Then attributes map with webBundleId
        # Then signature array
        
        data = f.read(1024)  # Read enough for header
        
        # Skip CBOR array indicator
        pos = 2
        
        # Verify magic bytes
        magic = data[pos:pos+8]
        if magic != b'\xf0\x9f\x96\x8b\xf0\x9f\x93\xa6':
            raise ValueError("Invalid magic bytes")
        pos += 8
        
        # Verify version
        version = data[pos:pos+5]
        if version != b'D2b\x00\x00':
            raise ValueError(f"Invalid version: {binascii.hexlify(version)}")
        pos += 5
        
        # Parse webBundleId map
        # 0xa1 indicates map with 1 key-value pair
        if data[pos] != 0xa1:
            raise ValueError("Invalid attributes map")
        pos += 1
        
        # Skip 'webBundleId' key (0x6b = 11 bytes)
        pos += 12  # Skip "webBundleId"
        
        # Read the ID (0x78 = text string, next byte is length)
        id_len = data[pos + 1]
        pos += 2
        web_bundle_id = data[pos:pos+id_len].decode('ascii')
        pos += id_len
        
        # Parse signature array (0x81 = array of 1 element, 0x82 = map of 2 elements)
        if data[pos] != 0x81:
            raise ValueError("Invalid signature array")
        pos += 1
        
        # Parse signature map
        if data[pos] != 0x82:
            raise ValueError("Invalid signature map")
        pos += 1
        
        # Parse ed25519PublicKey (0xa1 = map with 1 pair)
        if data[pos] != 0xa1:
            raise ValueError("Invalid public key map")
        pos += 1
        
        # Skip "ed25519PublicKey" string
        pos += 16
        
        # Read public key (0x58 = bytes, next byte is length)
        key_len = data[pos + 2]
        pos += 3
        public_key = data[pos:pos+key_len]
        pos += key_len
        
        # Read signature (0x58 = bytes, next byte is length)
        sig_len = data[pos + 1]
        pos += 2
        signature = data[pos:pos+sig_len]
        
        return {
            'web_bundle_id': web_bundle_id,
            'public_key': base64.b64encode(public_key).decode('ascii'),
            'signature': binascii.hexlify(signature).decode('ascii')
        }

def main():
    path = "/Users/weber/Projects/iwa/git/DomusAeterna/dist/app.swbn"

    manifest = extract_manifest_from_bundle(path)
    print(manifest)

    result = parse_signed_web_bundle_header(path)
    print("Web Bundle ID:", result['web_bundle_id'])
    print("Public Key (base64):", result['public_key'])
    print("Signature (hex):", result['signature'])

if __name__ == "__main__":
    main()