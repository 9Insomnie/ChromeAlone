import re
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from datetime import datetime
import random

@dataclass
class ProtobufValue:
    wire_type: int
    value: Any
    nested_message: Optional['ProtobufMessage'] = None
    field_path: List[int] = None

    def __post_init__(self):
        if self.field_path is None:
            self.field_path = []

class ProtobufMessage:
    def __init__(self, parent_path: List[int] = None):
        self.fields: Dict[int, List[ProtobufValue]] = {}
        self.parent_path = parent_path or []
    
    def add_field(self, field_number: int, wire_type: int, value: Any, nested_message: Optional['ProtobufMessage'] = None):
        if field_number not in self.fields:
            self.fields[field_number] = []
        
        # Create full field path by combining parent path with current field number
        field_path = self.parent_path + [field_number]
        self.fields[field_number].append(ProtobufValue(wire_type, value, nested_message, field_path))
    
    def get_field(self, field_path: Union[int, List[int]]) -> List[ProtobufValue]:
        """Get field by number or full path."""
        if isinstance(field_path, int):
            return self.fields.get(field_path, [])
        
        if not field_path:
            return []
        
        # Get first level field
        current_fields = self.fields.get(field_path[0], [])
        
        # If we want deeper fields, traverse nested messages
        if len(field_path) > 1:
            result = []
            for field in current_fields:
                if field.nested_message:
                    nested_results = field.nested_message.get_field(field_path[1:])
                    result.extend(nested_results)
            return result
        
        return current_fields
    
    def serialize(self) -> bytes:
        """Serialize the message back to protobuf wire format."""
        result = bytearray()
        for field_number, values in sorted(self.fields.items()):
            for value in values:
                # Encode field header (field number and wire type)
                field_header = (field_number << 3) | value.wire_type
                result.extend(encode_varint(field_header))
                
                # Encode field value based on wire type
                if value.wire_type == 0:  # Varint
                    result.extend(encode_varint(value.value))
                elif value.wire_type == 1:  # 64-bit
                    result.extend(value.value.to_bytes(8, 'little'))
                elif value.wire_type == 2:  # Length-delimited
                    # Always use the original bytes if we have them
                    if value.value is not None:
                        serialized = value.value
                    elif value.nested_message:
                        serialized = value.nested_message.serialize()
                    else:
                        raise ValueError("Length-delimited field has no value or nested message")
                    
                    result.extend(encode_varint(len(serialized)))
                    result.extend(serialized)
                elif value.wire_type == 5:  # 32-bit
                    result.extend(value.value.to_bytes(4, 'little'))
                else:
                    raise ValueError(f"Invalid wire type {value.wire_type}")
        return bytes(result)

    def format_structure(self, indent: str = "") -> List[str]:
        """Format the message structure recursively."""
        lines = []
        for field_number, values in sorted(self.fields.items()):
            for value in values:
                path_str = '.'.join(str(n) for n in value.field_path)
                if value.nested_message:
                    lines.append(f"{indent}Field path {path_str}: <nested message>")
                    nested_lines = value.nested_message.format_structure(indent + "  ")
                    lines.extend(nested_lines)
                else:
                    # Try to decode bytes for display
                    display_value = value.value
                    if isinstance(display_value, bytes):
                        try:
                            display_value = display_value.decode('utf-8')
                        except UnicodeDecodeError:
                            display_value = value.value  # Keep as bytes if can't decode
                    lines.append(f"{indent}Field path {path_str}: {display_value}")
        return lines

    def update_field(self, field_path: List[int], value: Any, transform: Optional[callable] = None):
        """Update a field value by its path."""
        if not field_path:
            return
        
        # Get the first level field
        field_number = field_path[0]
        fields = self.fields.get(field_number, [])
        
        if len(field_path) == 1:
            # Direct field update
            for field in fields:
                if transform:
                    field.value = transform(value, field.value)
                else:
                    field.value = value
        else:
            # Nested field update
            for field in fields:
                if field.nested_message:
                    field.nested_message.update_field(field_path[1:], value, transform)

def encode_varint(value: int) -> bytes:
    """Encode an integer as a varint."""
    result = []
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)

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
    if data[0] < 32 or (data[0] & 0x07) <= 5:
        return False
    printable_chars = sum(32 <= b <= 126 or b in (9, 10, 13) for b in data)
    return printable_chars / len(data) > 0.9

def try_parse_nested(data, depth):
    """Try to parse data as a nested message, return True if successful."""
    try:
        offset = 0
        while offset < len(data):
            field_header = data[offset]
            wire_type = get_wire_type(field_header)
            if wire_type > 5:
                return False
            offset += 1
            
            if wire_type == 0:
                _, offset = parse_varint(data, offset)
            elif wire_type == 1:
                offset += 8
            elif wire_type == 2:
                length, offset = parse_varint(data, offset)
                offset += length
            elif wire_type == 5:
                offset += 4
            
            if offset > len(data):
                return False
                
        return True
    except:
        return False
    
def parse_protobuf(data: bytes, offset: int = 0, max_length: Optional[int] = None, 
                parent_path: List[int] = None) -> ProtobufMessage:
    """Parse protobuf binary data into a ProtobufMessage object."""
    message = ProtobufMessage(parent_path)
    start_offset = offset
    
    if max_length is None:
        max_length = len(data) - offset
    
    while offset < start_offset + max_length:
        if offset >= len(data):
            break
            
        field_header = data[offset]
        wire_type = get_wire_type(field_header)
        field_number = get_field_number(data, offset)
        
        # Skip past field header
        _, offset = parse_varint(data, offset)
        
        # Calculate current field path
        current_path = (parent_path or []) + [field_number]
        
        if wire_type == 0:  # Varint
            value, offset = parse_varint(data, offset)
            message.add_field(field_number, wire_type, value)
            
        elif wire_type == 1:  # 64-bit
            value = int.from_bytes(data[offset:offset + 8], 'little')
            message.add_field(field_number, wire_type, value)
            offset += 8
            
        elif wire_type == 2:  # Length-delimited
            length, new_offset = parse_varint(data, offset)
            value = data[new_offset:new_offset + length]
            
            if try_parse_nested(value, 0):
                nested_msg = parse_protobuf(value, 0, length, current_path)
                # Store only the nested message, not the raw bytes
                message.add_field(field_number, wire_type, None, nested_msg)
            else:
                # Try to decode as string if it looks like one
                if is_printable_ascii(value):
                    try:
                        value = value.decode('utf-8')
                    except UnicodeDecodeError:
                        pass
                message.add_field(field_number, wire_type, value)
            
            offset = new_offset + length
            
        elif wire_type == 3:  # Start group (deprecated in proto3)
            print(f"Warning: Start group wire type (3) encountered at offset {offset}. This is deprecated.")
            group_level = 1
            while group_level > 0 and offset < len(data):
                next_header = data[offset]
                next_wire_type = get_wire_type(next_header)
                if next_wire_type == 3:
                    group_level += 1
                elif next_wire_type == 4:
                    group_level -= 1
                offset += 1
            
        elif wire_type == 4:  # End group (deprecated in proto3)
            print(f"Warning: End group wire type (4) encountered at offset {offset}. This is deprecated.")
            break
            
        elif wire_type == 5:  # 32-bit
            value = int.from_bytes(data[offset:offset + 4], 'little')
            message.add_field(field_number, wire_type, value)
            offset += 4
            
        elif wire_type in (6, 7):  # Reserved for future use
            raise ValueError(f"Wire type {wire_type} is reserved for future use")
            
        else:
            raise ValueError(f"Invalid wire type {wire_type}")
    
    return message

def update_with_origin(origin: str, old_value: Any) -> bytes:
    """Transform function to replace origin in URL while keeping the path."""
    if isinstance(old_value, bytes):
        try:
            # Decode bytes to string for manipulation
            old_str = old_value.decode('utf-8')
            parts = old_str.split('/')
            if len(parts) >= 4:
                # Keep everything after the host part
                path = '/'.join(parts[3:])
                new_str = f"{origin}/{path}"
                # Return as bytes since that's our storage format
                return new_str.encode('utf-8')
        except UnicodeDecodeError:
            pass
    return f"{origin}/".encode('utf-8')

def main():
    import argparse
    import json
    
    parser = argparse.ArgumentParser()
    parser.add_argument('binary_file', help='The binary protobuf file to parse')
    parser.add_argument('--output', help='Output file for modified protobuf')
    args = parser.parse_args()
    
    try:
        with open(args.binary_file, 'rb') as f:
            data = f.read()
        

        
        # Placeholder values
        ORIGIN = "isolated-app://test-manifest-id"
        PUBLIC_KEY = "base64-encoded-test-key"
        SIGNATURE_INFO = "hex-encoded-test-signature"
        APP_NAME = "Test App"
        VERSION = "1.0.0"
        INSTALL_TIME = int(datetime.now().timestamp())
        IWA_FOLDER_NAME = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))
        
        # Parse into intermediate representation
        message = parse_protobuf(data)
        
        # Print original structure
        print("Original message structure:")
        for line in message.format_structure():
            print(line)
        
        # Track jitter count for field 59.1.3.2
        jitter_count = 0
        def add_jitter(base_time: int, _) -> int:
            nonlocal jitter_count
            jitter_count += 1
            return base_time + jitter_count + random.randint(5, 10)
        
        # Convert string values to bytes for length-delimited fields
        def to_bytes(s: str) -> bytes:
            return s.encode('utf-8')
        
        # Perform field updates
        updates = [
            ([1, 1], to_bytes(f"{ORIGIN}/")),
            ([1, 2], to_bytes(APP_NAME)),
            ([1, 5], to_bytes(f"{ORIGIN}/")),
            ([1, 6, 2], ORIGIN, update_with_origin),
            ([2], to_bytes(APP_NAME)),
            ([6], to_bytes(f"{ORIGIN}/")),
            ([10, 2], ORIGIN, update_with_origin),
            ([16], INSTALL_TIME),
            ([30], ORIGIN, update_with_origin),
            ([49, 2], to_bytes(ORIGIN)),
            ([59, 1, 3, 2], INSTALL_TIME, add_jitter),
            ([59, 1, 1], to_bytes(APP_NAME)),
            ([59, 5, 2], to_bytes(APP_NAME)),
            ([60, 1, 1], to_bytes(IWA_FOLDER_NAME)),
            ([60, 7, 1, 1, 1], to_bytes(PUBLIC_KEY)),
            ([60, 7, 1, 1, 2], to_bytes(SIGNATURE_INFO)),
            ([64], INSTALL_TIME),
        ]
        
        for field_path, value, *transform in updates:
            message.update_field(field_path, value, transform[0] if transform else None)
        
        # Print updated structure
        print("\nUpdated message structure:")
        for line in message.format_structure():
            print(line)
        
        # Serialize and save
        serialized = message.serialize()
        print(f"\nSerialized back to {len(serialized)} bytes")
        
        if args.output:
            with open(args.output, 'wb') as f:
                f.write(serialized)
            print(f"Written to {args.output}")
                
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
