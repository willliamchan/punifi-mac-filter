"""pfSense has no mutation surface: one fixed read-only XML-RPC collector."""

import xmlrpc.client
from xml.parsers.expat import ExpatError

import aiohttp

from .policy import ProviderError, parse_source
from .transport import Transport

# Fixed code, not a template: no interface, host, credential or caller input is
# interpolated into PHP. kern.hostuuid is stable across endpoint/name changes.
COLLECTOR = """$ifs=config_get_path('interfaces', []);
$vlans=config_get_path('vlans/vlan', []);
$rows=[];
foreach(config_get_path('dhcpd', []) as $id=>$d){
 $i=$ifs[$id] ?? [];
 $device=$i['if'] ?? '';
 $tag='';
 foreach($vlans as $v){if(($v['vlanif'] ?? '')===$device){$tag=(string)($v['tag'] ?? '');}}
 $macs=[];
 foreach(($d['staticmap'] ?? []) as $m){$macs[]=(string)($m['mac'] ?? '');}
 $rows[]=['id'=>(string)$id,'interface'=>(string)($i['descr'] ?? $id),
 'ip_address'=>(string)($i['ipaddr'] ?? ''),'subnet_prefix'=>(string)($i['subnet'] ?? ''),
 'vlan_id'=>$tag,'policy'=>(string)($d['denyunknown'] ?? 'disabled'),'mac_addresses'=>$macs];
}
$toreturn=['identity'=>trim(shell_exec('/sbin/sysctl -n kern.hostuuid')), 'interfaces'=>$rows];"""
PAYLOAD = xmlrpc.client.dumps((COLLECTOR,), methodname="pfsense.exec_php", allow_none=False).encode()


class PfSense:
    def __init__(self, session, data):
        if not data.get("pfsense_username") or ":" in data["pfsense_username"]:
            raise ProviderError("invalid_auth", "pfsense")
        self.transport = Transport(
            session,
            data["pfsense_host"],
            data["pfsense_port"],
            "pfsense",
            {
                "Content-Type": "text/xml",
                "Accept": "text/xml",
                "Authorization": aiohttp.encode_basic_auth(
                    data["pfsense_username"], data["pfsense_password"]
                ),
            },
        )

    async def read(self):
        body = await self.transport.request("POST", "/xmlrpc.php", data=PAYLOAD)
        try:
            # Reject DTD/entity payloads before parsing bounded input.
            if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
                raise ValueError
            params, _ = xmlrpc.client.loads(body)
            if len(params) != 1:
                raise ValueError
            return parse_source(params[0])
        except ProviderError as exc:
            exc.provider = "pfsense"
            raise
        except xmlrpc.client.Error, ExpatError, ValueError, TypeError:
            raise ProviderError("unsupported_schema", "pfsense") from None
