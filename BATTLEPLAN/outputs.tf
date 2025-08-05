output "relay_public_ip" {
  description = "Public IP of the relay server"
  value       = aws_eip.relay_ip.public_ip
}

output "relay_websocket_url" {
  description = "WebSocket URL for agent connections"
  value       = var.domain_name != "" ? "wss://${var.domain_name}:443" : "ws://${aws_eip.relay_ip.public_ip}:8080"
  sensitive   = true
}

output "socks_proxy_address" {
  description = "SOCKS proxy address"
  value       = "${aws_eip.relay_ip.public_ip}:1080"
}

output "relay_instance_id" {
  description = "Instance ID of the relay server"
  value       = aws_instance.relay_server.id
}