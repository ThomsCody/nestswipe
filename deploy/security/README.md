# Production host access

SSH stays available from any network, using keys only. Direct root login is
disabled; administrators use `ubuntu` and sudo. The backup key remains restricted
by its existing forced command. This configuration does not alter authorized
keys, SSH forwarding, Oracle rules, Docker networking or application containers.

Host maintenance is deliberately separate from the application deploy: SSH
changes need a fresh login check before they are accepted.

## Apply SSH policy

Copy this directory to the VM, then from the existing administrative connection:

```sh
sudo bash deploy/security/host-access.sh apply
```

The installer validates syntax and effective policy for ubuntu/root, then reloads
SSH. A root-owned systemd timer restores the previous drop-in after five minutes
unless explicitly confirmed. Keep the original session open. From a second Mac
terminal, force a new connection (no multiplexing) and verify sudo:

```sh
ssh -o ControlMaster=no -o ControlPath=none -o BatchMode=yes ubuntu@145.241.161.221 'sudo -n true'
```

Check the backup key without downloading or creating an archive, from the repo:

```sh
ssh -F /dev/null -i backups/.keys/download_ed25519 \
  -o IdentityAgent=none -o IdentitiesOnly=yes -o BatchMode=yes \
  -o StrictHostKeyChecking=yes -o UserKnownHostsFile=backups/.keys/known_hosts \
  ubuntu@145.241.161.221 latest
```

Only after both work, confirm through the new administrative connection:

```sh
sudo /usr/local/sbin/nestswipe-host-access confirm
```

If either fails, run `sudo /usr/local/sbin/nestswipe-host-access rollback` in the
original connection or wait for the timer. The timer requires the VM to stay
running: do not reboot during verification. `rollback` acts only on a pending
change. The previous drop-in, when present, is retained under the root-only
`/var/lib/nestswipe-host-access/` directory. Do not confirm if another SSH policy
change occurred during the verification window.

## Unused RPC services

Before disabling RPC, verify that `findmnt -t nfs,nfs4` finds no NFS mounts,
`rpcinfo -p 127.0.0.1` lists only portmapper, and that service dependencies and
configured mounts/exports do not require RPC. Then:

```sh
sudo systemctl mask --now rpcbind.socket rpcbind.service
```

Confirm no TCP/UDP 111 listener remains. On this VM both units were enabled and
active beforehand; to restore that state if NFS is intentionally introduced:

```sh
sudo systemctl unmask rpcbind.socket rpcbind.service
sudo systemctl enable --now rpcbind.socket rpcbind.service
```

## Network review, 2026-10-25

The live VNIC has no NSGs and uses only `nestswipe-public-sl`. Its ingress rules
permit TCP 22/80/443 from any IPv4 address and ICMP type 3/code 4. Egress permits
all IPv4 traffic. The subnet has no IPv6 CIDR and the host has no global IPv6
address. Review IPv6 firewall policy before enabling IPv6.

Host UFW is inactive, but Oracle's existing iptables INPUT rules reject other
unsolicited traffic. Docker publishes only web ports 80/443 through its forwarding
rules. Preserve the Oracle `InstanceServices` rules. The TCP checks from the Mac
reached 22/80/443; 111, 5432, 9000, 9001 and 8126 timed out. This was a targeted
check from one network, not a comprehensive scan.

No new Oracle resources or paid services are required for these changes.
