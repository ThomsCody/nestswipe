# Production kernel lockdown

Datadog rule `def-000-3oj` requires kernel lockdown in `integrity` mode. This
restricts unsigned kernel modules and kernel modification interfaces. Use
`integrity`: `confidentiality` additionally restricts tracing used by monitoring.
This host maintenance is separate from application deployments.

## Production verification, 2026-11-19

Applied to `nestswipe-vnic`, running `6.8.0-1067-oracle` on ARM64. The live mode
and Datadog's `KernelLockdown` status both report `integrity`. All loaded modules
had signatures and the kernel taint value was zero before activation.

A fresh SSH login and sudo succeeded. All five application containers remained
healthy and `/api/v1/health` returned `{"status":"ok"}`. Datadog system-probe
restarted successfully under lockdown; USM reported `Running`, and the `open`,
`chmod` and `chown` workload-security self-tests all passed. No kernel lockdown
denials were observed during verification.

The installed drop-in matches this repository's file. `grub-script-check` passed,
and all seven generated kernel entries include `lockdown=integrity`. The original
GRUB configuration is backed up at `/var/lib/nestswipe-lockdown/grub.cfg.before`.
The VM was not rebooted; boot persistence has been configured and validated but
has not yet been exercised by a reboot.

## Apply

Before enabling it, check `/sys/kernel/security/lockdown`, kernel support, loaded
module signatures, SSH access, application health and Datadog probe status.
Confirm that required modules are trusted by the running kernel. Raising the
lockdown level takes effect immediately and cannot be reversed without rebooting.
Obtain approval for the production kernel change before proceeding.

Enable the live setting:

```sh
sudo sh -c 'printf "%s\n" integrity > /sys/kernel/security/lockdown'
cat /sys/kernel/security/lockdown
```

The expected result is `none [integrity] confidentiality`. Verify a fresh SSH
login, healthy Docker containers, the API health endpoint, Datadog Agent services
and system-probe network/workload-security status. Check the kernel journal for
new lockdown denials. If checks pass, persist the setting from the repository root:

```sh
sudo install -o root -g root -m 644 deploy/security/99-nestswipe-lockdown.cfg \
  /etc/default/grub.d/99-nestswipe-lockdown.cfg
sudo update-grub
sudo grub-script-check /boot/grub/grub.cfg
sudo grep -E '^[[:space:]]*linux' /boot/grub/grub.cfg
```

Verify that generated kernel entries include `lockdown=integrity` and preserve
the existing root-device and console arguments. No reboot is needed to activate
the live setting. Boot persistence is only fully exercised by a subsequent boot.

## Rollback

Remove only this drop-in, regenerate and validate GRUB, and arrange an approved
reboot. Removing the boot setting alone does not lower the running lockdown level:

```sh
sudo rm /etc/default/grub.d/99-nestswipe-lockdown.cfg
sudo update-grub
sudo grub-script-check /boot/grub/grub.cfg
```

After the approved reboot, check the live mode and application/monitoring health
again. Secure Boot or other kernel policy can independently enforce lockdown.

References:
- [Datadog rule](https://docs.datadoghq.com/security/default_rules/def-000-3oj/)
- [Linux kernel parameters](https://docs.kernel.org/admin-guide/kernel-parameters.html)
