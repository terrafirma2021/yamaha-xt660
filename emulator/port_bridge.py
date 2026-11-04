"""Test-only stdin/stdout adapter for the C# client; no physical serial access."""
import argparse
import base64
import sys
from boot_service import BootService


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ucsim',required=True)
    ap.add_argument('--wsl',action='store_true')
    ap.add_argument('--image',default='xt660-2004-2006-companion')
    args=ap.parse_args()
    with BootService(args.ucsim,args.image,args.wsl) as boot:
        print('READY',flush=True)
        for line in sys.stdin:
            if line.strip()=='QUIT': break
            try:
                request=base64.b64decode(line.strip(),validate=True)
                if len(request)<5 or len(request)>2053:raise ValueError('Invalid test frame')
                reply=boot.exchange(request,validate=False)
                print('REPLY '+base64.b64encode(reply).decode(),flush=True)
            except Exception as exc:
                print('ERROR '+str(exc),flush=True)
                return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
