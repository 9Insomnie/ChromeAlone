import re
from typing import Dict, List, Optional, Tuple

class ProtoField:
    def __init__(self, name: str, number: int, type_name: Optional[str] = None):
        self.name = name
        self.number = number
        self.type_name = type_name

class ProtoMessage:
    def __init__(self, name: str):
        self.name = name
        self.fields: Dict[int, ProtoField] = {}
        self.reserved_fields: set[int] = set()
        self.nested_types: Dict[str, 'ProtoMessage'] = {}

def parse_varint(data, offset):
    """Parse a varint from the data starting at offset."""
    result = 0
    shift = 0
    while True:
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset

def get_wire_type(byte):
    """Extract wire type from a field's first byte."""
    return byte & 0x07

def get_field_number(data, offset):
    """Extract field number from a varint."""
    field_number, _ = parse_varint(data, offset)
    return field_number >> 3

def is_printable_ascii(data):
    """Check if data is likely a printable ASCII string."""
    if not data:
        return False
    # Reject if first byte looks like a protobuf field marker
    if data[0] < 32 or (data[0] & 0x07) <= 5:  # Check if low 3 bits are a valid wire type
        return False
    # Check if data is mostly printable ASCII
    printable_chars = sum(32 <= b <= 126 or b in (9, 10, 13) for b in data)
    return printable_chars / len(data) > 0.9  # Increased threshold

def format_bytes(data):
    """Format bytes as hex and ASCII."""
    hex_str = ' '.join(f'{b:02x}' for b in data)
    if is_printable_ascii(data):
        try:
            ascii_str = data.decode('utf-8')
            return f"String: {ascii_str!r}"
        except UnicodeDecodeError:
            pass
    
    # If not a string, show hex with ASCII representation
    ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)
    return f"Hex: {hex_str}\nASCII: {ascii_str}"

def parse_length_delimited(data, offset):
    """Parse a length-delimited field."""
    length, new_offset = parse_varint(data, offset)
    value = data[new_offset:new_offset + length]
    return value, new_offset + length

def try_parse_nested(data, depth):
    """Try to parse data as a nested message, return True if successful."""
    try:
        # Check if data looks like a valid protobuf message
        offset = 0
        while offset < len(data):
            field_header = data[offset]
            wire_type = get_wire_type(field_header)
            if wire_type > 5:  # Invalid wire type
                return False
            offset += 1
            
            if wire_type == 0:  # Varint
                _, offset = parse_varint(data, offset)
            elif wire_type == 1:  # 64-bit
                offset += 8
            elif wire_type == 2:  # Length-delimited
                length, offset = parse_varint(data, offset)
                offset += length
            elif wire_type == 5:  # 32-bit
                offset += 4
            
            if offset > len(data):
                return False
                
        return True
    except:
        return False

def parse_proto_file(file_path: str) -> Dict[str, ProtoMessage]:
    """Parse a .proto file and return a mapping of message types."""
    messages: Dict[str, ProtoMessage] = {}
    current_message = None
    in_enum = False
    pending_field = ''
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            # Try with latin-1 encoding if UTF-8 fails
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading proto file: {e}")
            return {}

    # First remove multi-line comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    
    # Process line by line to handle single-line comments and continuation lines
    lines = []
    continued_line = ''
    
    for line in content.split('\n'):
        # Remove single-line comments
        line = re.sub(r'//.*$', '', line)
        line = line.strip()
        
        if not line:
            continue
            
        # Handle line continuation
        if line.endswith('\\'):
            continued_line += line[:-1] + ' '
            continue
            
        # Complete the line if it was continued
        if continued_line:
            line = continued_line + line
            continued_line = ''
            
        lines.append(line)
    
    # Process the cleaned lines
    for line in lines:
        # Check for message start
        if line.startswith('message '):
            message_match = re.match(r'message\s+(\w+)\s*\{', line)
            if message_match:
                message_name = message_match.group(1)
                current_message = ProtoMessage(message_name)
                messages[message_name] = current_message
                in_enum = False
                pending_field = ''
            continue
        
        # Check for message end
        if line == '}':
            if in_enum:
                in_enum = False
                continue
            current_message = None
            pending_field = ''
            continue
        
        # Skip if not in a message
        if not current_message:
            continue
            
        # Handle reserved statements - complete statement on one line
        if 'reserved' in line and ';' in line:
            numbers = re.findall(r'\b(\d+)\b(?!\s*-)', line)
            if numbers:
                for num in numbers:
                    current_message.reserved_fields.add(int(num))
            continue
            
        # Handle enum blocks
        if line.startswith('enum '):
            in_enum = True
            continue
            
        if in_enum:
            continue
            
        # Accumulate multi-line field definitions
        if pending_field:
            line = pending_field + ' ' + line
            pending_field = ''
        
        # Check if this is a partial field definition
        if not line.endswith(';'):
            pending_field = line
            continue
            
        # Try to parse field definition
        if not in_enum:  # Add this check to be explicit
            field_match = re.match(
                r'''^\s*                                   # Leading whitespace
                    (reserved|optional|required|repeated)?\s+       # Field modifier (made capturing)
                    ([\w\.\[\]]+)\s+                      # Type name
                    (\w+)\s*=\s*                          # Field name
                    (\d+)                                 # Field number
                    (?:\s*\[.*\])?;?                      # Optional attributes
                ''', line, re.VERBOSE)
                
            if field_match:
                modifier = field_match.group(1) or ''
                field_type = field_match.group(2)
                field_name = field_match.group(3)
                field_number = int(field_match.group(4))
                field = ProtoField(field_name, field_number, field_type)
                current_message.fields[field_number] = field
            elif not line.startswith(('enum', 'reserved', '}')):
                print(f"  Warning: Could not parse field line: {line!r}")
                print(f"  Current state: in_enum={in_enum}, pending_field={pending_field!r}")
    
    for msg_name, msg in messages.items():
        # Find the highest field number to know our range
        max_field = max(msg.fields.keys()) if msg.fields else 0
        for field_num in range(1, max_field + 1):
            if field_num in msg.fields:
                field = msg.fields[field_num]
    
    return messages

def get_field_name(field_number: int, message_type: str, proto_types: Dict[str, ProtoMessage]) -> str:
    """Get the field name for a given field number and message type."""
    if message_type in proto_types:
        message = proto_types[message_type]
        if field_number in message.fields:
            return message.fields[field_number].name
    return str(field_number)

def parse_protobuf(data, offset=0, depth=0, max_length=None, field_path=None, 
                  proto_types=None, current_type=None, field_names=None):
    """Recursively parse protobuf binary data."""
    indent = '  ' * depth
    start_offset = offset
    field_path = field_path or []
    field_names = field_names or []  # Track field names through recursion
    
    if max_length is None:
        max_length = len(data) - offset
    
    if depth == 0 and proto_types and current_type in proto_types:
        print(f"\nParsing {current_type} message")
    
    while offset < start_offset + max_length:
        if offset >= len(data):
            break
            
        field_header = data[offset]
        wire_type = get_wire_type(field_header)
        field_number = get_field_number(data, offset)
        
        # Get field name if type information is available
        if proto_types and current_type:
            field_name = get_field_name(field_number, current_type, proto_types)
            # Try to get the type of the nested message if it's a nested field
            nested_type = None
            if current_type in proto_types:
                message = proto_types[current_type]
                if field_number in message.fields:
                    nested_type = message.fields[field_number].type_name
        else:
            field_name = str(field_number)
            nested_type = None
        
        # Create the field path string using the tracked field names
        field_str = '.'.join(field_names + [field_name])
        
        # Skip past the field number varint
        _, offset = parse_varint(data, offset)
        
        print(f"{indent}Field {field_str} (Wire Type {wire_type}) at offset 0x{offset-1:04x}:")
        
        if wire_type == 0:  # Varint
            value, offset = parse_varint(data, offset)
            print(f"{indent}  Varint: {value} (0x{value:x})")
            
        elif wire_type == 1:  # 64-bit
            value = int.from_bytes(data[offset:offset + 8], 'little')
            # If field 16, treat as timestamp
            if field_number == 16:
                timestamp_seconds = value // 1000000  # Convert microseconds to seconds
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(timestamp_seconds, timezone.utc)
                microseconds = value % 1000000
                print(f"{indent}  64-bit timestamp: {dt.strftime('%Y-%m-%d %H:%M:%S')}.{microseconds:06d} UTC")
            else:
                print(f"{indent}  64-bit: {value} (0x{value:x})")
            offset += 8
            
        elif wire_type == 2:  # Length-delimited
            length, new_offset = parse_varint(data, offset)
            print(f"{indent}  Length: {length} bytes")
            value = data[new_offset:new_offset + length]
            
            # First try to parse as string if it looks printable
            if is_printable_ascii(value):
                try:
                    string_value = value.decode('utf-8')
                    print(f"{indent}  String: {string_value!r}")
                    offset = new_offset + length
                    continue
                except UnicodeDecodeError:
                    pass
            
            # Then try to parse as nested message
            if try_parse_nested(value, depth + 1):
                print(f"{indent}  Nested message:")
                parse_protobuf(value, 0, depth + 1, length, 
                             field_path + [field_number], 
                             proto_types, 
                             nested_type,
                             field_names + [field_name])  # Pass the current field name
            else:
                # If not a nested message, show raw bytes
                print(f"{indent}  {format_bytes(value)}")
            
            offset = new_offset + length
            
        elif wire_type == 5:  # 32-bit
            value = int.from_bytes(data[offset:offset + 4], 'little')
            print(f"{indent}  32-bit: {value} (0x{value:x})")
            offset += 4
            
        else:
            print(f"{indent}  Unknown wire type {wire_type}")
            return
            
def main():
    import sys
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('binary_file', help='The binary protobuf file to parse')
    parser.add_argument('--proto', default='web_app.proto', help='Path to .proto file with message definitions')
    parser.add_argument('--type', default='WebAppProto', help='Root message type name')
    args = parser.parse_args()
    
    proto_types = None
    if args.proto:
        proto_types = parse_proto_file(args.proto)
    
    with open(args.binary_file, 'rb') as f:
        data = f.read()
    
    print(f"Parsing {len(data)} bytes of protobuf data:")
    parse_protobuf(data, proto_types=proto_types, current_type=args.type)

if __name__ == '__main__':
    main()
