# htb-terminal

Client terminal Python pour quelques workflows courants de l'API HTB Labs v4:
machines, VPN, fichiers OVPN et appels bruts.

## Sources utilisées

- Documentation officielle HTB Enterprise Public API: https://enterprise-help.hackthebox.com/en/articles/13375637-introduction-to-enterprise-public-api
- Article officiel HTB sur l'accès Lab/OpenVPN: https://help.hackthebox.com/en/articles/5185687-gs-introduction-to-lab-access
- Collection Postman v4 fournie dans la demande: https://documenter.getpostman.com/view/13129365/TVeqbmeq
- Référence communautaire lisible des endpoints Labs v4: https://github.com/D3vil0p3r/HackTheBox-API

Note: HTB documente officiellement l'API Enterprise. Les endpoints Labs v4 utilisés ici viennent de la collection Postman et de références communautaires; ils peuvent changer sans préavis.

## Installation

Le projet n'a pas de dépendance externe.

```bash
chmod +x ./htb
./htb --help
```

Par défaut, le token est lu depuis `api.token` dans le dossier courant. Tu peux aussi utiliser:

```bash
export HTB_API_TOKEN="..."
```

## Exemples

```bash
./htb machine active
./htb machine profile "BoardLight"
./htb machine list
./htb machine list --retired --page 1
./htb machine list --sp-tier 1

./htb machine start "BoardLight" --mode auto
./htb machine start 444 --mode play
./htb machine start 478 --mode spawn
./htb machine stop
./htb machine reset
./htb machine submit 444 HTB{flag} --difficulty 50

./htb vpn servers
./htb vpn switch us-free-1
./htb vpn download us-free-1 -o lab-vpn.ovpn
./htb vpn connect us-free-1 -o lab-vpn.ovpn

./htb raw GET /machine/active
./htb raw POST /vm/spawn --data '{"machine_id":478}'
```

## Architecture

- `htb_terminal/config.py`: chargement du token et de l'URL API.
- `htb_terminal/http.py`: client HTTP authentifie.
- `htb_terminal/services/machines.py`: operations machines.
- `htb_terminal/services/vpn.py`: operations VPN et OVPN.
- `htb_terminal/cli.py`: parsing CLI et orchestration.

Chaque module garde une responsabilite unique pour faciliter les evolutions si HTB change un endpoint.

