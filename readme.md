# Local Dns Server

A simple dns server writing in python for running in localhost.

Use upstream dns servers, with various Dns protocol (UDP, TCP, DOH, DOT).

Supports Dns blocking, cloaking, forwarding.

* * *

## Prerequisites

* Latest version of python.
* pip: `python -m pip install pip --upgrade`.
* pipenv: `python -m pip install pipenv --upgrade`.

## Development & Build

```shell
pipenv install --dev
```

```shell
pipenv run dev
```

```shell
pipenv run build
```

## Usage

### Command line

```
usage: LocalDnsServer [-h] [--data-dir DATA_DIR] [--port PORT] [--service {install,start,stop,remove,restart,run}]

options:
  -h, --help            show this help message and exit
  --data-dir DATA_DIR   directory for config files and temp files. default: data
  --port PORT           which port the server should listen, default: 53
  --service {install,start,stop,remove,restart,run}
                        windows only. manage windows service

```

server listen to all ipv4 and ipv6 addresses, `0.0.0.0` and `::`.

### Config file

**config.json** should be located in **data-dir**.

```json
{
    "ipv6": false,
    "default": [ "cloudflare", "google" ],
    "upstream": {
        "cloudflare": [ "1.0.0.1", "1.1.1.1", "2606:4700:4700::1001", "2606:4700:4700::1111" ],
        "adguard": [ "94.140.14.140", "94.140.14.141", "2a10:50c0::1:ff", "2a10:50c0::2:ff" ],
        "opendns": [ "208.67.220.220", "208.67.222.222", "2620:119:35::35", "2620:119:53::53" ],
        "quad9": [ "9.9.9.10", "149.112.112.10", "2620:fe::10", "2620:fe::fe:10" ],
        "google": { "ip": [ "8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844" ], "preferred_protocol": "udp" }
    },
    "rules": {
        "allowed_ips": "allowed-ips.txt",
        "allowed_names": "allowed-names.txt",
        "blocked_ips": "blocked-ips.txt",
        "blocked_names": { "default": "blocked-names.txt", "temp": "blocked-names-temp.txt" },
        "cloaking_rules": "cloaking-rules.txt",
        "forwarding_rules": { "google": "forwarding-rules.txt" }
    }
}
```

* `ipv6`: set to `false` to disable ipv6 if you don't have ipv6 connectivity, this will make ipv6 server return `NOTIMP` for all dns query.
* `default`: keys in `upstream`, required, the default upstream dns servers to use.
* `upstream`: object, required. *DOH* that use domain names are not supported.
    * value is an `array` of ip addresses. protocol by default is `https`.
    * value is an `object` contains `ip` and `preferred_protocol`.
        * `ip` is an `array` of ip addresses.
        * `preferred_protocol` should be one of `udp` / `tcp` / `https` /`tls`.
* `rules`: each key specify the dns rule files, relative to **data-dir**. See below for more information about those files.

### Dns Manipulation

Each key in `rules` specify the dns rule files, each value can be

* just a plain filename (the key is `defalut`)
* an `array` of filenames (the key is `defalut`)
* an `object` of key-value pairs (value can also be just a plain filename or an `array` of filenames)

```json
{
    "rules": {
        "allowed_ips": "allowed-ips.txt",
        "allowed_names": "allowed-names.txt",
        "blocked_ips": [ "blocked-ips.txt" ],
        "blocked_names": { "default": "blocked-names.txt", "temp": "blocked-names-temp.txt" },
        "cloaking_rules": "cloaking-rules.txt",
        "forwarding_rules": { "google": [ "forwarding-rules.txt" ] }
    }
}
```

rule syntax use *exact match* or *glob pattern* or *prefix match*.

```
example.com
=www.example.com
ww*.example.com    # inline comments
# some comments
```

* Blank lines are ignored
* Lines that starts with `#` are also ignored, and anything after `#` is ignored.
* `example.com` use *prefix match*, matches `example.com` and all its subdomains, but not `1example.com`.
* `=www.example.com` use *exact match*, matches only `www.example.com`.
* `ww*.example.com` use *glob pattern*, matches `ww1.example.com` and `ww2.example.com` and others.

#### DNS Blocking

The value for `allowed_ips` / `allowed_names` / `blocked_ips` / `blocked_names` can be an `object` of key-value pairs.

Key `default` and `temp` are special names, apply to all clients.

Other keys should be a *glob pattern string* or a simple *client ip address* that matches *client ip*,
this rule file only apply to this client.

`allowed_ips` have priority over `blocked_ips`.

`blocked_ips` are removed from dns response, if the remaining is not a valid dns response, `REFUSED` is returned.

`allowed_names` have priority over `blocked_names`.

* `allowed_ips` / `blocked_ips` rule syntax use *exact match* or *glob pattern*.

    ```
    192.168.1.1
    192.168.1.[12]
    192.168.1.*
    ```

* `allowed_names` / `blocked_names` rule syntax use *exact match* or *glob pattern* or *prefix match*.

    ```
    example.com
    =www.example.com
    ww*.example.com
    ```

#### DNS Cloaking

Keys in `cloaking_rules` have no special meaning.

`cloaking_rules` rule syntax use *exact match* or *glob pattern* or *prefix match*.

```
example.com                 192.168.1.1
=www.example.com            192.168.1.1
ww*.example.com             192.168.1.1
ww*.example.com             cname.example.com
```

CNAME cloaking can also be used, upstream dns server will be used if this CNAME can not be resolved in `cloaking_rules`.

CNAME cloaking limits up to 5 levels.

#### DNS Forwarding

Keys in `forwarding_rules` means the upstream server this rule file forwards to.

`{"google": "forwarding-rules.txt"}` means rules in `forwarding-rules.txt` should forward to upstream `google`.

`forwarding_rules` rule syntax similar to `blocked_names`.

### Windows setup

See https://learn.microsoft.com/en-us/powershell/module/dnsclient

* [Get-DnsClient](https://learn.microsoft.com/en-us/powershell/module/dnsclient/get-dnsclient)
* [Set-DnsClientServerAddress](https://learn.microsoft.com/en-us/powershell/module/dnsclient/set-dnsclientserveraddress)
* [Clear-DnsClientCache](https://learn.microsoft.com/en-us/powershell/module/dnsclient/clear-dnsclientcache)
* [Get-DnsClientServerAddress](https://learn.microsoft.com/en-us/powershell/module/dnsclient/get-dnsclientserveraddress)

Set default dns to `127.0.0.1` / `::1` and clear dns cache:

```powershell
function Step1 {
    $dnsServers = @('127.0.0.1', '::1')
    Write-Host ($dnsServers -join ', ')
    Write-Host ''

    Get-DnsClient | ForEach-Object {
        if (($_.InterfaceAlias -notlike 'Local Area Connection*') -and ($_.InterfaceAlias -notlike 'Loopback Pseudo-Interface*')) {
            Write-Host $_.InterfaceAlias
            Set-DnsClientServerAddress -InterfaceIndex $_.InterfaceIndex -ServerAddresses $dnsServers
        }
    }
}

function Step2 {
    1..5 | ForEach-Object {
        Write-Host $_
        Clear-DnsClientCache
        Start-Sleep -Milliseconds 100
    }
}

Write-Host 'Step1'
Step1

Write-Host "`nStep2"
Step2
```

Get current dns:

```powershell
function Step3 {
    Get-DnsClientServerAddress | ForEach-Object {
        Write-Host (($_.InterfaceAlias.PadRight(30)) + ' ' + ($_.ServerAddresses -join ', '))
    }
}

Write-Host "Step3"
Step3
```
