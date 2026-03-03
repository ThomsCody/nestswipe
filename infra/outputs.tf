output "public_ip" {
  description = "Public IP address of the Nestswipe instance"
  value       = oci_core_instance.nestswipe.public_ip
}

output "instance_id" {
  description = "OCID of the compute instance"
  value       = oci_core_instance.nestswipe.id
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh ubuntu@${oci_core_instance.nestswipe.public_ip}"
}
