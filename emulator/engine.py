"""Run unchanged firmware against explicit external storage, sensors and peers."""
import re
import uuid
from collections import deque
from crank import events, hex_memory
from runner import prepare, registered_image
from session import Session
from storage import factory_storage, storage_commands


class Engine:
    def __init__(self, executable, image, wsl=False, storage=None, registered=True, port_b=None):
        if port_b is not None and (type(port_b) is not int or not 0 <= port_b <= 255):
            raise ValueError('Initial PORTB fixture must be a byte')
        self.record, setup = prepare(image, wsl)
        self.image = image
        self.early = self.record['application_entry'] == 0x5000
        _, data = registered_image(image)
        config = data[(0x4e7d if self.early else 0x4619)-self.record['base_address']]
        if config not in (0,128):
            raise ValueError('Unreviewed authentication configuration')
        self.authentication_required = config == 0
        self.loop = 0x538b if self.early else 0x4bc5
        self.adc = [512]*8
        self.crank_pitch = 1600
        self.trace = deque(maxlen=10000)
        self.transcript = []
        if storage is None:
            storage, self.storage_origin = factory_storage(executable, image, wsl)
        else:
            self.storage_origin = {'origin': 'User-supplied external storage image'}
        self.session = Session(executable, wsl, image+'-engine-'+uuid.uuid4().hex[:8]+'.log')
        try:
            command = setup + storage_commands(storage, registered)
            command += 'set memory xtboot_0_cfg 9 224\nset memory xtboot_0_cfg 13 16\n'
            if port_b is not None:
                command += f'set memory xtboot_0_cfg 10 {port_b}\n'
            command += f'break {self.loop} 1000\nstep 2000000\ndelete\ninfo hardware xtboot\n'
            result = self.session.command(command)
            if f'Stop at 0x{self.loop:06x}: (104)' not in result:
                raise RuntimeError('Firmware did not reach its main loop')
            self.cycles = int(re.findall(r'BUS_CYCLES=(\d+)',result)[-1])
            self.session.command('set memory xtboot_0_cfg 25 1')
        except BaseException:
            self.close()
            raise

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def step(self, instructions=20000):
        if type(instructions) is not int or not 1 <= instructions <= 1000000:
            raise ValueError('Use 1..1000000 instructions per step')
        text = self.session.command(f'set memory xtboot_0_cfg 25 0\nset memory xtboot_0_cfg 25 1\nstep {instructions}')
        stops = re.findall(r'Stop at 0x([0-9a-f]+): \((\d+)\)', text)
        if not stops or stops[-1][1] != '109':
            raise RuntimeError('Unexpected firmware stop: '+str(stops))
        self.cycles += int(re.findall(r'stepped (\d+) ticks',text)[-1])
        rows = events(text)
        self.trace.extend(rows)
        return rows

    def wait_cycles(self, cycles):
        """Run instructions until a minimum simulated bus-clock delay elapsed."""
        deadline = self.cycles + cycles
        while self.cycles < deadline:
            self.step(min(100000,max(1,(deadline-self.cycles)//4)))

    def set_adc(self, channel, value):
        if type(channel) is not int or not 0 <= channel < 8 or type(value) is not int or not 0 <= value <= 1023:
            raise ValueError('ADC channel 0..7 and integer value 0..1023 required')
        self.session.command(f'adc{channel}={value}')
        self.adc[channel] = value

    def set_port(self, port, value):
        ports = {'A':9, 'B':10, 'E':11, 'T':12, 'S':13, 'P':14}
        if port not in ports or type(value) is not int or not 0 <= value <= 255:
            raise ValueError('Choose GPIO port A/B/E/T/S/P and byte 0..255')
        self.session.command(f'set memory xtboot_0_cfg {ports[port]} {value}')

    def crank(self, pitch=1600, patterns=24, uniform=False):
        if type(pitch) is not int or not 400 <= pitch <= 4000 or type(patterns) is not int or not 1 <= patterns <= 4096//11:
            raise ValueError('Pitch 400..4000 timer ticks; 1..372 patterns')
        command = 'set memory xtboot_0_cfg 24 0\n'
        for offset,value in [(19,pitch*32),(20,pitch*16),(21,0 if uniform else 11),(22,2),(23,patterns*11),(24,1)]:
            command += f'set memory xtboot_0_cfg {offset} {value}\n'
        self.session.command(command)
        self.crank_pitch = pitch

    def stop_crank(self):
        self.session.command('set memory xtboot_0_cfg 24 0\nset memory xtboot_0_cfg 37 0\nset memory xtboot_0_cfg 35 0')

    def drive(self, pitch=None, road=False):
        """External rotating-engine fixture. No firmware variables are altered."""
        if pitch is None:
            self.stop_crank()
            self.session.command('set memory xtboot_0_cfg 36 0')
            return
        if type(pitch) is not int or not 400 <= pitch <= 4000:
            raise ValueError('Use a tooth interval of 400..4000 timer ticks')
        self.session.command(f'set memory xtboot_0_cfg 35 {pitch*32}\n'
                             f'set memory xtboot_0_cfg 36 {pitch*32*3 if road else 0}')
        self.crank_pitch = pitch

    def start_drive(self, pitch=2800):
        self.crank(pitch, patterns=372)
        self.session.command('set memory xtboot_0_cfg 37 1')

    def exchange(self, byte, channel=1, count=5, budget=500000):
        if type(byte) is not int or not 0 <= byte <= 255 or channel not in (0,1):
            raise ValueError('Serial byte 0..255 and channel 0/1 required')
        # Give the receiver one idle frame to leave RWU after the previous reply.
        self.step(10000)
        self.session.command(f'set memory xtboot_0_cfg {26+channel} {byte}')
        received = []
        for remaining in range(budget,0,-25000):
            received.extend(e['value'] for e in self.step(min(25000,remaining))
                            if e['kind']=='serial_tx' and e['channel']==channel)
            if len(received) >= count:
                break
        row = dict(channel=channel, request=f'{byte:02X}', reply=' '.join(f'{v:02X}' for v in received))
        self.transcript.append(row)
        del self.transcript[:-256]
        if len(received) != count:
            raise RuntimeError('Serial reply length mismatch: '+str(row))
        if channel == 1 and count == 5 and sum(received[:4]) & 255 != received[4]:
            raise RuntimeError('Firmware reply checksum mismatch')
        return received

    def authenticate(self, corrupt=False):
        if not self.authentication_required:
            raise ValueError('This BIN disables authentication; its serial receiver uses the normal meter handler')
        challenge = self.exchange(0x3e)
        if challenge[2] != 0x43:
            raise RuntimeError('Expected authentication challenge: '+str(challenge))
        record = self.exchange(0x3d)
        if record[2] != 0x4b:
            raise RuntimeError('Synthetic registered record not accepted: '+str(record))
        a,b,_,c,_ = challenge
        response = a*b+b*c+c*a
        if corrupt:
            response ^= 1
        for shift in (12,6,0):
            if self.exchange(0x80|((response>>shift)&63)) != [0x47]*4+[0x1c]:
                raise RuntimeError('Challenge chunk rejected')
        polls = [self.exchange(0x3f) for _ in range(4 if not corrupt else 1)]
        expected = [0x46]*4+[0x18] if corrupt else [0x45]*4+[0x14]
        if any(p != expected for p in polls):
            raise RuntimeError('Authentication result differs from code trace: '+str(polls))
        return dict(accepted=not corrupt, transcript=list(self.transcript))

    def snapshot(self):
        text = self.session.command('info hardware xtboot\ndump /i rom 0x800 0xfff 16')
        memory = hex_memory(text)
        if len(memory) != 2048:
            raise RuntimeError('Incomplete RAM snapshot')
        word = lambda a: memory[a]*256+memory[a+1]
        counts = {k.lower():int(v) for k,v in re.findall(r'\b([A-Z][A-Z0-9_]+)=(\d+)\b',text)
                  if k not in ('TIMER_OUT','CCF','IRQ_VECTOR')}
        if counts['bus_cycles'] != self.cycles:
            raise RuntimeError('Host cycle accounting differs from the MCU model')
        return dict(image=self.image, adc=list(self.adc), counts=counts, crank_pitch=self.crank_pitch,
                    authentication_required=self.authentication_required,
                    synchronized=bool(memory[0xbfe if self.early else 0xc20]&128),
                    pitch_ticks=word(0xa2e if self.early else 0xa38),
                    authentication_inhibit=bool(memory[0xd08 if self.early else 0xd21]&1),
                    authentication_complete=bool(memory[0xd06 if self.early else 0xd1f]&128),
                    lean_sensor_fault=bool(memory[0x8b1 if self.early else 0x8b3]&16),
                    sidestand_inhibit=bool(memory[0x88c]&128),
                    faults=[memory[a] for a in range(0x8af if self.early else 0x8b1,0x8b3 if self.early else 0x8b5)],
                    output_transitions={str(n):sum(e['kind']=='output' and e['channel']==n for e in self.trace) for n in (3,6,7)})

    def external_storage(self):
        m = hex_memory(self.session.command('dump /i eeprom 0 511 16'))
        return bytes(m[i] for i in range(512))

    def verify_flash(self):
        _, data = registered_image(self.image)
        expected = (bytes(self.record['base_address'])+data)[0x1800:]
        m = hex_memory(self.session.command('dump /i rom 0x1800 0xffff 16'))
        if len(m)!=len(expected) or bytes(m[a] for a in range(0x1800,0x10000))!=expected:
            raise RuntimeError('Emulator flash differs from registered source')
        return len(expected)
