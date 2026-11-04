"""In-process ECU boot-protocol peer. Operates only on simulated memory."""
import re
from runner import prepare, registered_image
from session import Session
from crank import events, hex_memory


def frame(command, parameter=0, payload=b''):
    if not 0<=command<=15 or not 0<=parameter<=255 or len(payload)>2048:
        raise ValueError('Invalid boot request')
    body=bytes([command,parameter])+ (len(payload)+5).to_bytes(2,'big')+bytes(payload)
    return body+bytes([-sum(body)&255])


class BootService:
    def __init__(self, executable, image, wsl=False):
        record,setup=prepare(image,wsl)
        self.record=record
        _,data=registered_image(image)
        self.original=bytes(record['base_address'])+data
        self.session=Session(executable,wsl,image+'-boot-service.log')
        self.transcript=[]
        loop=0x538b if record['application_entry']==0x5000 else 0x4bc5
        try:
            text=self.session.command(setup+'set memory xtboot_0_cfg 9 224\nset memory xtboot_0_cfg 13 16\n'+f'break {loop} 100\nstep 2000000\ndelete\nset memory xtboot_0_cfg 34 1\n')
            if f'Stop at 0x{loop:06x}: (104)' not in text:
                raise RuntimeError('Boot startup did not reach main loop')
        except BaseException:
            self.close()
            raise

    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def close(self): self.session.close()

    def exchange(self, request, expected=0, budget=30000000, validate=True):
        self.session.command('set memory xtboot_0_cfg 25 0\nset memory xtboot_0_cfg 25 1\n'+
                             ''.join(f'set memory xtboot_0_cfg 26 {v}\n' for v in request))
        reply=[]
        for _ in range((budget+999999)//1000000):
            text=self.session.command('set memory xtboot_0_cfg 25 0\nset memory xtboot_0_cfg 25 1\nstep 1000000\ninfo hardware xtboot')
            stops=re.findall(r'Stop at 0x[0-9a-f]+: \((\d+)\)',text)
            if stops!=['109']: raise RuntimeError('Unexpected boot execution stop: '+str(stops))
            reply.extend(e['value'] for e in events(text) if e['kind']=='serial_tx' and e['channel']==0)
            if len(reply)>=5 and len(reply)>=reply[2]*256+reply[3]:break
        result=bytes(reply)
        self.transcript.append(dict(command=request[0],parameter=request[1],request_length=len(request),
                                    reply_length=len(reply),status=reply[1] if len(reply)>1 else None))
        if len(result)<5 or len(result)!=int.from_bytes(result[2:4],'big') or sum(result)&255:
            raise RuntimeError('Invalid boot reply: '+result[:32].hex())
        if not validate: return result
        if result[0]!=request[0] or result[1] or len(result)!=expected+5:
            raise RuntimeError('Rejected boot request: '+result[:32].hex())
        return result[4:-1]

    def connect(self):
        self.exchange(frame(1,0,self.original[0xff10:0xff20]))
        self.exchange(frame(2,1))

    def read(self,address,mode=2):
        lengths=[2,16,512,2048,256,1024]
        if type(mode) is not int or not 0<=mode<len(lengths) or type(address) is not int or not 0<=address<=65536-lengths[mode]:
            raise ValueError('Read outside address space')
        return self.exchange(frame(3,mode,address.to_bytes(2,'big')),lengths[mode])

    def program(self,address,data,command=9):
        if type(address) is not int or address%2048 or not 0x1800<=address<0xf800 or len(data)!=2048:
            raise ValueError('Only aligned application blocks are accepted')
        if command not in (9,14):raise ValueError('Unsupported program command')
        self.exchange(frame(5,1,bytes.fromhex('08205aa5')))
        self.exchange(frame(command,address>>8,data))

    def flash(self):
        m=hex_memory(self.session.command('dump /i rom 0x1800 0xffff 16'))
        return bytes(m[a] for a in range(0x1800,0x10000))
