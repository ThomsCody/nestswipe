#!/usr/bin/env bash
# Explicit host maintenance, separate from routine application deployments.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077

[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
state=/var/lib/nestswipe-host-access
target=/etc/ssh/sshd_config.d/00-nestswipe-access.conf
installed=/usr/local/sbin/nestswipe-host-access
unit=nestswipe-ssh-rollback
install -d -m 700 "$state"
exec 9>"$state/lock"
flock -n 9 || { echo 'Another host-access operation is running.' >&2; exit 1; }

rollback() {
    [[ -f "$state/pending" ]] || return 0
    if [[ -f "$state/previous.conf" ]]; then
        install -m 600 "$state/previous.conf" "$target"
    else
        rm -f "$target"
    fi
    sshd -t
    systemctl reload ssh
    rm -f "$state/pending"
    echo 'Previous SSH configuration restored.'
}

case "${1:-}" in
    apply)
        [[ ! -f "$state/pending" ]] || {
            echo 'A change awaits confirmation or rollback.' >&2; exit 1;
        }
        source_dir=$(cd "$(dirname "$0")" && pwd)
        config=$source_dir/00-nestswipe-access.conf
        [[ -f "$config" && ! -L "$target" ]]
        sshd -t
        if [[ -f "$target" ]] && cmp -s "$config" "$target"; then
            echo 'SSH drop-in already installed; inspect sshd -T for effective policy.'
            exit 0
        fi
        systemctl stop "$unit.timer" 2>/dev/null || true
        if [[ -f "$target" ]]; then
            cp -p "$target" "$state/previous.conf"
        else
            rm -f "$state/previous.conf"
        fi
        install -m 700 "$0" "$installed"
        touch "$state/pending"
        trap 'rollback' ERR
        # The root-owned copy can recover even if the checkout/SSH session vanishes.
        systemd-run --quiet --unit="$unit" --on-active=5min \
            "$installed" rollback
        install -m 600 "$config" "$target"
        sshd -t
        for user in ubuntu root; do
            effective=$(sshd -T -C "user=$user,host=localhost,addr=127.0.0.1")
            for setting in 'permitrootlogin no' 'pubkeyauthentication yes' \
                'passwordauthentication no' 'kbdinteractiveauthentication no' \
                'authenticationmethods publickey'; do
                grep -qxF "$setting" <<< "$effective"
            done
        done
        systemctl reload ssh
        trap - ERR
        echo 'SSH reloaded. Test NEW login, sudo and backup key, then confirm within 5 minutes.'
        ;;
    confirm)
        [[ -f "$state/pending" ]] || { echo 'No pending SSH change.' >&2; exit 1; }
        sshd -t
        systemctl stop "$unit.timer"
        rm -f "$state/pending"
        echo 'SSH change confirmed; automatic rollback cancelled.'
        ;;
    rollback)
        rollback
        ;;
    *) echo 'Usage: host-access.sh apply|confirm|rollback' >&2; exit 2 ;;
esac
