#!/usr/bin/python3
"""Install renewed TLS atomically and reload only the subscription service."""
import os, pwd, ssl, subprocess, tempfile
from pathlib import Path

source = Path(os.environ.get('RENEWED_LINEAGE','/etc/letsencrypt/live/personal-vps-ip'))
destination = Path('/var/lib/personal-vps-subscription/tls')
identity = pwd.getpwnam('private-subscription')
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(source/'fullchain.pem',source/'privkey.pem')
for name in ['fullchain.pem','privkey.pem']:
    fd, temporary = tempfile.mkstemp(dir=destination,prefix='.renew-')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write((source/name).read_bytes())
            stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o600)
        os.chown(temporary,identity.pw_uid,identity.pw_gid)
        os.replace(temporary,destination/name)
    finally:
        Path(temporary).unlink(missing_ok=True)
subprocess.run(['systemctl','try-restart','personal-vps-subscription'],check=True)
