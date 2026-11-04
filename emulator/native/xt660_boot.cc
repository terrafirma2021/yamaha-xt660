// SPDX-License-Identifier: GPL-2.0-or-later
// XT660 peripheral harness for uCsim 0.9.12. This is NOT a full ECU.
// Device semantics: MC9S12T64 Rev 1.1.1, CRG, ECT, PIM and ATD chapters.
#include <cstdio>
#include "globals.h"
#include "utils.h"
#include "m68hc12cl.h"
#include "simcl.h"

class xt_cpu;
class xt_boot_hw: public cl_hw {
public:
  xt_cpu *xt;
  cl_memory_cell *regs[0x200];
  unsigned load, count, prescaler, phase, pll_delay;
  bool counting, fault;
  unsigned adc_left, adc_slot, adc_done, adc_length, adc_armed, adc_period;
  unsigned adc_sample_left, adc_sample, adc_sequences, adc_conversions;
  bool adc_running;
  unsigned irq_count, irq_vector;
  unsigned timer_phase, timer_output, timer_edges, timer_matches, last_pt;
  unsigned osc_phase, rti_phase, rti_events, cop_elapsed, cop_services;
  bool cop_written, cop_armed;
  unsigned spi_left, spi_tx, spi_pending, spi_armed, spi_count, spi_dropped;
  bool spi_queued;
  unsigned long long bus_cycles;
  unsigned pulse_left, pulse_count, trace_count, observed_outputs;
  bool pulse_low;
  unsigned cfg_size(void) { return 26; }
  void advance(unsigned cycles);
  void pulse_tick(void);
  void trace(const char *kind, unsigned channel, unsigned value);
  void observe_outputs(void);
  void timer_tick(unsigned cycles);
  void timer_compare(unsigned channel);
  unsigned timer_pins(unsigned pins);
  void clock_tick(unsigned cycles);
  void spi_tick(unsigned cycles);
  void spi_begin(unsigned value);
  unsigned word(unsigned a) { return regs[a]->get()*256+regs[a+1]->get(); }
  void set_word(unsigned a, unsigned value) { regs[a]->set(value>>8); regs[a+1]->set(value&255); }
  const char *cfg_help(t_addr a);
  t_mem conf_op(cl_memory_cell *cell, t_addr a, t_mem *v);
  void adc_start(bool fresh);
  void adc_tick(unsigned cycles);
  void adc_flags(void);
  unsigned pending_vector(void);
  unsigned gpio(unsigned a);
  xt_boot_hw(xt_cpu *cpu);
  int init(void);
  void reset(void);
  t_mem read(cl_memory_cell *cell);
  void write(cl_memory_cell *cell, t_mem *value);
  int tick(int cycles);
  void print_info(cl_console_base *con);
  unsigned address(cl_memory_cell *cell);
  bool supported(unsigned addr);
  void unsupported(unsigned addr, const char *operation);
};

class xt_cpu: public cl_m68hc12 {
public:
  xt_boot_hw *device;
  bool executing;
  xt_cpu(cl_sim *sim): cl_m68hc12(sim), device(NULL), executing(false) {
    cpu12= NULL;
  }
  const char *id_string(void) { return "XT660 partial MCU model (MC9S12T64 reference)"; }
  void make_cpu_hw(void) { cl_uc::make_cpu_hw(); }
  void mk_hw_elements(void) {
    // Exclude generic HC12 page registers and inherited 6800 CIA/PIA devices:
    // those addresses overlap T64 clock registers and the ECU's program flash.
    cl_uc::mk_hw_elements();
    device= new xt_boot_hw(this);
    init_add_hw(device);
  }
  bool interrupts_masked(void) { return rCC & flagI; }
  int do_interrupt(void) {
    // CPU12 has one global I mask. The MCU selects simultaneous requests;
    // software can explicitly re-enable I-masked sources inside a handler.
    if (device->fault || (rCC & flagI) || block_irq) return resGO;
    unsigned vector= device->pending_vector();
    if (!vector) return resGO;
    executing= true;
    push_regs(true);
    vc.wr += 9;
    rCC |= flagI;
    PC= read_addr(rom, vector);
    executing= false;
    ++device->irq_count;
    device->irq_vector= vector;
    device->trace("irq",vector,PC);
    // Instruction-boundary functional delivery. Exception entry bus cycles
    // and RTI tail chaining are not timed in this stage.
    return device->fault ? resHALT : resGO;
  }
  int rti(void) {
    // RTI may clear X, but cannot set an X mask already cleared by software.
    unsigned old_x= rCC & flagX;
    pull_regs(true);
    vc.rd += 9;
    if (!old_x) rCC &= ~flagX;
    return resGO;
  }
  int exec_inst(void) {
    if (device->fault) return resHALT;
    unsigned op= rom->get(PC);
    if (op==0x4a || op==0x4b || op==0x0a) {
      fprintf(stderr, "XT660 unsupported banked CALL/RTC at %04x\n", unsigned(PC));
      device->fault= true;
      return resHALT;
    }
    executing= true;
    int result= cl_m68hc12::exec_inst();
    executing= false;
    return device->fault ? resHALT : result;
  }
};

xt_boot_hw::xt_boot_hw(xt_cpu *cpu): cl_hw(cpu, HW_DUMMY, 0, "xtboot"), xt(cpu) {}
int xt_boot_hw::init(void) {
  cl_hw::init();
  for (unsigned a=0; a<0x200; ++a) regs[a]= register_cell(uc->rom, a);
  for (unsigned a=0x1800; a<0x10000; ++a) register_cell(uc->rom, a);
  for (unsigned n=0; n<8; ++n) {
    chars name("", "adc%u", n);
    uc->vars->add(name, cfg, n+1, "Raw 10-bit ADC input (0..1023), not a physical-unit sensor scale");
  }
  return 0;
}
void xt_boot_hw::reset(void) {
  for (unsigned a=0; a<0x200; ++a) regs[a]->set(0);
  regs[0x37]->set(0x40); // CRGFLG.PORLVDRF
  regs[0x3a]->set(0xf1); // PLLCTL reset value
  regs[0x76]->set(0xff); regs[0x77]->set(0xff);
  regs[0x83]->set(0x20); regs[0x84]->set(5);
  regs[0x1f]->set(0xf2); // HPRIO reset: external IRQ highest
  adc_left= adc_slot= adc_done= adc_armed= adc_period= 0;
  adc_sample_left= adc_sample= adc_sequences= adc_conversions= 0;
  adc_length=8; adc_running=false;
  irq_count= irq_vector=0;
  timer_phase=timer_output=timer_edges=timer_matches=last_pt=0;
  osc_phase=rti_phase=rti_events=cop_elapsed=cop_services=0;
  cop_written=cop_armed=false;
  regs[0x3c]->set(0x43);
  spi_left=spi_tx=spi_pending=spi_armed=spi_count=spi_dropped=0;
  spi_queued=false;
  bus_cycles=0; pulse_left=pulse_count=trace_count=observed_outputs=0; pulse_low=false;
  regs[0xdb]->set(0x20); // SPTEF
  regs[0xd4]->set(0xc0); // SCI1 idle; no external serial traffic
  cfg_set(17,255); cfg_set(18,0); // Unconnected/pulled-high MISO, no EEPROM invented.
  // Explicit, deterministic raw input fixtures; no inferred temperature/RPM.
  for (unsigned n=1; n<=8; ++n) cfg_set(n,512);
  for (unsigned n=9; n<=16; ++n) cfg_set(n,0);
  cfg_set(19,51200); cfg_set(20,25600); cfg_set(21,11); cfg_set(22,2);
  cfg_set(23,132); cfg_set(24,0); cfg_set(25,0);
  regs[0xcc]->set(0xc0); // SCI0 TDRE/TC idle; no serial transfer model yet
  load= count= 0xffff;
  prescaler= 1; phase= pll_delay= 0;
  counting= fault= false;
}
unsigned xt_boot_hw::address(cl_memory_cell *cell) {
  t_addr a;
  if (uc->rom->is_owned(cell, &a)) return a;
  return 0xffff;
}
bool xt_boot_hw::supported(unsigned a) {
  // Explicitly supported registers only; other device accesses stop execution.
  return a<=3 || a==8 || a==9 || a==0x1e || a==0x1f || (a>=0x20 && a<=0x27)
    || (a>=0x82 && a<=0x86) || a==0x8b || a==0x8d || a==0x8f
    || (a>=0x90 && a<=0x9f)
    || a==0xe0 || a==0xe1 || a==0xe2 || a==0xe8 || a==0xe9 || a==0xea
    || a==0xf0 || a==0xf1 || a==0xf2
    || (a>=0x32 && a<=0x35) || (a>=0x37 && a<=0x3c) || a==0x3f
    || (a>=0x40 && a<=0x5f) || a==0x66 || a==0x67 || a==0x76 || a==0x77
    || (a>=0xc8 && a<=0xd5) || a==0xd7 || (a>=0xd8 && a<=0xdb) || a==0xdd || a==0xee || a==0xf8 || a==0x100;
}
void xt_boot_hw::unsupported(unsigned a, const char *operation) {
  if (!fault) fprintf(stderr, "XT660 unmodelled %s at register %04x, instruction %04x\n",
                      operation, a, unsigned(uc->instPC));
  fault= true;
}
t_mem xt_boot_hw::read(cl_memory_cell *cell) {
  unsigned a= address(cell);
  if (conf(cell,NULL)) return cell->get();
  if (!xt->executing) return cell->get(); // debugger reads have no side effects
  if (a>=0x1800) return cell->get();
  if (!supported(a)) { unsupported(a, "read"); return cell->get(); }
  if (a==0x32) return ((regs[0x32]->get()&regs[0x33]->get()) | (cfg_get(15)&~regs[0x33]->get()))&0x80;
  if (a==0x3f || a==0x41) return 0;
  if (a==0 || a==1 || a==8 || a==0xe0 || a==0xe1 || a==0xe8 || a==0xe9 || a==0xf0 || a==0xf1)
    return gpio(a);
  if ((a==0x44 || a==0x45) && (regs[0x46]->get()&0x10)) regs[0x4f]->set(0);
  if (a>=0x50 && a<=0x5f && (regs[0x46]->get()&0x10) && !(regs[0x40]->get()&(1<<((a-0x50)/2))))
    regs[0x4e]->set(regs[0x4e]->get()&~(1<<((a-0x50)/2)));
  if (a==0xdb) spi_armed |= cell->get();
  if (a==0xdd && (spi_armed&0x80)) {
    regs[0xdb]->set(regs[0xdb]->get()&~0x80); spi_armed &= ~0x80;
  }
  if (a==0x8f) return cfg_get(16) & regs[0x8d]->get();
  if (a==0x8b) adc_armed |= cell->get();
  if (a>=0x90 && a<=0x9f) {
    unsigned bit= 1<<((a-0x90)/2);
    if ((regs[0x82]->get()&0x40) || (adc_armed&bit)) {
      regs[0x8b]->set(regs[0x8b]->get()&~bit);
      adc_armed &= ~bit;
    }
    if (regs[0x82]->get()&0x40) {
      regs[0x86]->set(regs[0x86]->get()&~0x80);
      adc_flags();
    }
  }
  if (a==0x76 || a==0x77) {
    unsigned value= (regs[0x66]->get()&0x20) ? load : count;
    if (regs[0x46]->get()&0x10) regs[0x67]->set(regs[0x67]->get()&~0x80);
    return a==0x76 ? value>>8 : value&0xff;
  }
  return cell->get();
}
void xt_boot_hw::write(cl_memory_cell *cell, t_mem *v) {
  if (conf(cell,v)) return;
  unsigned a= address(cell);
  if (!xt->executing) return; // fixture/debugger memory setup, never an ECU write
  if (a>=0x1800) { unsupported(a, "CPU flash write"); *v=cell->get(); return; }
  if (!supported(a)) { unsupported(a, "write"); *v=cell->get(); return; }
  unsigned old= cell->get();
  if (a==0x32 || a==0x33) {
    *v &= 0x80;
  } else if (a==0x3b) {
    *v &= 0x7f; rti_phase=0;
  } else if (a==0x3c) {
    if (cop_written) *v=old;
    else { *v &= 0xc7; cop_written=true; cop_elapsed=0; cop_armed=false; }
  } else if (a==0x3f) {
    unsigned rate=regs[0x3c]->get()&7;
    if (rate) {
      static unsigned shifts[]={0,14,16,18,20,22,23,24};
      unsigned period=1u<<shifts[rate];
      if ((*v!=0x55 && *v!=0xaa) || ((regs[0x3c]->get()&0x80) && cop_elapsed<period*3/4))
        unsupported(a,"COP reset request (invalid service)");
      else if (*v==0x55) cop_armed=true;
      else if (cop_armed) { cop_elapsed=0; cop_armed=false; ++cop_services; }
    }
    *v=0;
  } else if (a==0x41) {
    for (unsigned n=0;n<8;++n) if ((*v&regs[0x40]->get())&(1<<n)) timer_compare(n);
    *v=0; // Forced compare does not set an interrupt flag.
  } else if (a==0x44 || a==0x45) {
    if (regs[0x46]->get()&0x10) regs[0x4f]->set(0);
    *v=old; // TCNT is read-only in normal mode.
  } else if (a==0x46) {
    *v &= 0xf0;
  } else if (a==0x4d) {
    *v &= 0x8f;
  } else if (a==0x4e || a==0x4f) {
    *v=old & ~(*v & (a==0x4e ? 255 : 128));
  } else if (a>=0x50 && a<=0x5f) {
    unsigned bit=1<<((a-0x50)/2);
    if (!(regs[0x40]->get()&bit)) *v=old;
    else if (regs[0x46]->get()&0x10) regs[0x4e]->set(regs[0x4e]->get()&~bit);
  } else if (a==0xcc || a==0xcd || a==0xce || a==0xd4 || a==0xd5) {
    *v=old; // Idle SCI status / receive data. No serial peer is attached.
  } else if (a==0xcf || a==0xd7) {
    unsupported(a,"SCI transmit (no serial transfer model)"); *v=old;
  } else if (a==0xcb || a==0xd3) {
    if (*v&0xd3) { unsupported(a,"SCI interrupt/break/wakeup mode"); *v=old; }
  } else if (a==0xca || a==0xd2) {
    if (*v&0x93) { unsupported(a,"SCI framing/loop mode"); *v=old; }
  } else if (a==0xd8) {
    if ((*v&0x40) && !(*v&0x10)) { unsupported(a,"SPI slave mode"); *v=old; return; }
    if (!(*v&0x40)) { spi_left=0; spi_queued=false; spi_armed=0; regs[0xdb]->set(0x20); }
  } else if (a==0xd9) {
    if (*v) { unsupported(a,"SPI mode configuration"); *v=old; }
  } else if (a==0xda) {
    *v &= 0x77;
  } else if (a==0xdb) {
    *v=old;
  } else if (a==0xdd) {
    if ((regs[0xd8]->get()&0x50)==0x50 && (regs[0xdb]->get()&0x20) && (spi_armed&0x20)) {
      spi_armed &= ~0x20;
      regs[0xdb]->set(regs[0xdb]->get()&~0x20);
      if (!spi_left) spi_begin(*v);
      else { spi_pending=*v; spi_queued=true; }
    }
    *v=old; // Separate receive data and transmit buffer share the address.
  } else if (a>=0x82 && a<=0x84) {
    if (a==0x82 && (*v&0x04)) { unsupported(a,"external ATD trigger configuration"); *v=old; return; }
    adc_running=false;
    regs[0x86]->set(regs[0x86]->get()&~0x20);
    if (a==0x82) {
      *v &= 0xfe;
      if ((*v&2) && (regs[0x86]->get()&0x80)) *v |= 1;
    }
    if (a==0x83) *v &= 0x7f;
  } else if (a==0x85) {
    *v &= 0xf7;
    adc_start(true);
  } else if (a==0x86) {
    *v=old & ~(*v&0xb0);
    regs[0x82]->set((regs[0x82]->get()&~1) | (((*v&0x80) && (regs[0x82]->get()&2)) ? 1:0));
  } else if (a==0x8b || a==0x8f || (a>=0x90 && a<=0x9f) || a==0xe1 || a==0xe9 || a==0xf1) {
    *v=old; // Read-only result/status/input registers.
  } else if (a==0x1f) {
    // Writes are permitted only with I set (normal single-chip mode).
    if (!(xt->interrupts_masked())) *v=old;
    else *v &= 0xfe;
  } else if (a==0x37) { // LOCK/TRACK read-only; interrupt flags write-one-to-clear
    *v= old & ~(*v & 0xd2);
  } else if (a==0x34 || a==0x35 || a==0x3a) {
    if (a==0x34 || a==0x35 || ((old^*v)&0x40)) {
      regs[0x37]->set(regs[0x37]->get()&~0x0c);
      pll_delay= 64; // deterministic acquisition fixture, NOT measured lock time
    }
  } else if (a==0x67) {
    *v= old & ~(*v & 0x80);
  } else if (a==0x66) {
    if (!(*v&4)) { count=0xffff; counting=false; phase=0; }
    if ((*v&0x0c)==0x0c) {
      static unsigned divisors[4]= {1,4,8,16};
      count=load; prescaler=divisors[*v&3]; phase=0; counting=count!=0;
    }
    *v &= ~0x18; // ICLAT/FLMC strobes read as zero
  } else if (a==0x76 || a==0x77) {
    load= a==0x76 ? ((*v&0xff)<<8)|(load&0xff) : (load&0xff00)|(*v&0xff);
    if (a==0x77 && !(regs[0x66]->get()&0x40)) {
      count=load; phase=0; counting=(regs[0x66]->get()&4) && count;
    }
    if (regs[0x46]->get()&0x10) regs[0x67]->set(regs[0x67]->get()&~0x80);
  }
}
int xt_boot_hw::tick(int cycles) {
  if (fault) return 0;
  // A driven waveform / trace uses individual bus ticks. CPU register accesses
  // and interrupt delivery still occur at instruction boundaries.
  if (cfg_get(24) || cfg_get(25)) {
    for (int n=0;n<cycles && !fault;++n) {
      advance(1);
      pulse_tick();
      observe_outputs();
    }
  } else advance(cycles);
  return 0;
}
void xt_boot_hw::advance(unsigned cycles) {
  bus_cycles+=cycles;
  adc_tick(cycles);
  timer_tick(cycles);
  spi_tick(cycles);
  clock_tick(cycles);
  if (pll_delay && (regs[0x3a]->get()&0x40)) {
    if (unsigned(cycles)>=pll_delay) { pll_delay=0; regs[0x37]->set(regs[0x37]->get()|0x1c); }
    else pll_delay-=cycles;
  }
  if (counting && (regs[0x66]->get()&4)) {
    phase+=cycles;
    while (counting && phase>=prescaler) {
      phase-=prescaler;
      if (count) --count;
      if (!count) {
        regs[0x67]->set(regs[0x67]->get()|0x80);
        if ((regs[0x66]->get()&0x40) && load) count=load;
        else counting=false;
      }
    }
  }
}
void xt_boot_hw::trace(const char *kind, unsigned channel, unsigned value) {
  if (!cfg_get(25)) return;
  if (++trace_count>20000) { unsupported(0xffff,"event trace limit"); return; }
  printf("XT_EVENT cycle=%llu kind=%s channel=%u value=%u pc=%04x\n",
         bus_cycles,kind,channel,value,unsigned(uc->instPC));
}
void xt_boot_hw::observe_outputs(void) {
  unsigned pins=gpio(0xe0), changed=(pins^observed_outputs)&regs[0x40]->get();
  for (unsigned n=0;n<8;++n) if (changed&(1<<n)) trace("output",n,(pins>>n)&1);
  observed_outputs=pins;
}
void xt_boot_hw::pulse_tick(void) {
  if (!cfg_get(24) || !pulse_left || --pulse_left) return;
  pulse_low=!pulse_low;
  cfg_set(12,pulse_low ? cfg_get(12)&~2u : cfg_get(12)|2u);
  trace("input",1,pulse_low ? 0 : 1);
  timer_tick(0); // Capture the edge at this counter value, without an extra tick.
  if (pulse_low) { ++pulse_count; pulse_left=cfg_get(20); }
  else if (pulse_count>=cfg_get(23)) cfg_set(24,0);
  else {
    unsigned interval=cfg_get(19);
    if (cfg_get(21) && ((pulse_count+1)%cfg_get(21)==0)) interval*=cfg_get(22);
    pulse_left=interval-cfg_get(20);
  }
}
void xt_boot_hw::print_info(cl_console_base *con) {
  con->dd_printf("XT660 partial peripherals; not a full engine model\n");
  con->dd_printf("PLL_LOCK=%u MCCNT=%u MC_LOAD=%u MCZF=%u FAULT=%u\n",
    (regs[0x37]->get()>>3)&1, count, load, (regs[0x67]->get()>>7)&1, fault);
  con->dd_printf("ADC_BUSY=%u ADC_SLOT=%u ADC_CONVERSIONS=%u ADC_SEQUENCES=%u SCF=%u CCF=%02x IRQ_COUNT=%u IRQ_VECTOR=%04x\n",
    adc_running, adc_slot, adc_conversions, adc_sequences, (regs[0x86]->get()>>7)&1,
    unsigned(regs[0x8b]->get()), irq_count, irq_vector);
  con->dd_printf("TCNT=%u TIMER_OUT=%02x CAPTURES=%u COMPARES=%u RTI_EVENTS=%u COP_SERVICES=%u SPI_BYTES=%u SPI_DROPPED=%u\n",
    word(0x44), timer_output, timer_edges, timer_matches, rti_events, cop_services, spi_count, spi_dropped);
  con->dd_printf("BUS_CYCLES=%llu PULSES=%u PULSE_RUNNING=%u\n",bus_cycles,pulse_count,unsigned(cfg_get(24)));
}


const char *xt_boot_hw::cfg_help(t_addr a) {
  if (a>=1 && a<=8) return "Raw ADC channel 0..7: integer 0..1023";
  if (a==17) return "SPI external MISO byte (default 255: pulled-high disconnected bus)";
  if (a==18) return "SPI fixture: 0 external byte, 1 internal test loopback (not EEPROM)";
  if (a==19) return "PT1 fixture: ordinary falling-edge interval in bus cycles";
  if (a==20) return "PT1 fixture: low pulse width in bus cycles";
  if (a==21) return "PT1 fixture: every Nth interval is long; 0 means uniform";
  if (a==22) return "PT1 fixture: long-interval multiplier";
  if (a==23) return "PT1 fixture: number of falling edges";
  if (a==24) return "PT1 fixture: 1 starts, 0 stops; no firmware/RAM edits";
  if (a==25) return "Emit bounded input/capture/output/IRQ event trace";
  if (a>=9) return "Driven GPIO input byte: PA, PB, PE, PT, PS, PP, PK7, PTAD";
  return "XT660 fixture configuration";
}
t_mem xt_boot_hw::conf_op(cl_memory_cell *cell, t_addr a, t_mem *v) {
  if (v && a) {
    unsigned max= a<=8 ? 1023 : (a==18 || a>=24) ? 1 :
                  (a==19 || a==20) ? 1000000 : a==21 ? 64 : a==22 ? 8 : a==23 ? 4096 : 255;
    if (*v>max) {
      fprintf(stderr,"XT660 fixture input %u outside 0..%u; unchanged\n",unsigned(a),max);
      *v=cell->get();
    }
    if (a>=19 && a<=23 && cfg_get(24)) {
      fprintf(stderr,"XT660 stop the PT1 fixture before changing its timing\n"); *v=cell->get();
    }
    if (a==25 && *v && !cell->get()) observed_outputs=gpio(0xe0);
    if (a==24 && *v && !cell->get()) {
      if (cfg_get(19)<32 || !cfg_get(20) || cfg_get(20)>=cfg_get(19) ||
          cfg_get(21)==1 || !cfg_get(22) || !cfg_get(23)) {
        fprintf(stderr,"XT660 invalid PT1 pulse fixture; not started\n"); *v=0;
      } else {
        pulse_count=0; pulse_low=false; pulse_left=cfg_get(19);
        cfg_set(12,cfg_get(12)|2u);
        observed_outputs=gpio(0xe0);
        trace("input",1,1);
        timer_tick(0);
      }
    }
  }
  return cell->get();
}
unsigned xt_boot_hw::gpio(unsigned a) {
  unsigned base=a, dir, fixture;
  if (a==0 || a==1) { dir=a+2; fixture=a+9; }
  else if (a==8) { dir=9; fixture=11; }
  else {
    base=a&~1;
    dir=base+2;
    fixture=base==0xe0 ? 12 : base==0xe8 ? 13 : 14;
  }
  unsigned direction=regs[dir]->get();
  if (a==8) direction &= 0xfc; // PE0/PE1 are input-only.
  unsigned pins=(regs[base]->get()&direction) | (cfg_get(fixture)&~direction);
  // PTI registers observe the driven pin level too, including output pins.
  if (base==0xe0) pins=timer_pins(pins);
  return pins & 255;
}
void xt_boot_hw::adc_flags(void) {
  unsigned ctl=regs[0x82]->get()&~1;
  if ((ctl&2) && (regs[0x86]->get()&0x80)) ctl|=1;
  regs[0x82]->set(ctl);
}
void xt_boot_hw::adc_start(bool fresh) {
  if (fresh) {
    regs[0x86]->set(regs[0x86]->get()&7);
    regs[0x8b]->set(0); adc_armed=0;
    adc_flags();
  }
  adc_done=0;
  adc_length=(regs[0x83]->get()>>3)&15;
  if (adc_length==0 || adc_length>8) adc_length=8;
  if (!(regs[0x83]->get()&4)) adc_slot=0;
  regs[0x86]->set((regs[0x86]->get()&0xf8)|adc_slot);
  unsigned ctl4=regs[0x84]->get();
  unsigned divisor=2*((ctl4&31)+1), sample=2+(2<<((ctl4>>5)&3));
  adc_period=(sample+((ctl4&0x80)?8:10))*divisor;
  adc_left=adc_period;
  adc_sample_left=sample*divisor;
  adc_running=regs[0x82]->get()&0x80;
}
void xt_boot_hw::adc_tick(unsigned cycles) {
  while (adc_running && cycles) {
    unsigned elapsed=cycles<adc_left ? cycles : adc_left;
    if (adc_sample_left) {
      if (elapsed>=adc_sample_left) {
        unsigned channel=regs[0x85]->get()&7;
        if (regs[0x85]->get()&0x10) channel=(channel+adc_done)&7;
        adc_sample=cfg_get(channel+1);
        adc_sample_left=0;
      } else adc_sample_left-=elapsed;
    }
    adc_left-=elapsed; cycles-=elapsed;
    if (adc_left) continue;
    unsigned ctl5=regs[0x85]->get(), value=adc_sample;
    bool eight=regs[0x84]->get()&0x80;
    if (eight) value>>=2;
    if (!(ctl5&0x80)) {
      if (ctl5&0x40) value ^= eight ? 0x80 : 0x200;
      value <<= eight ? 8 : 6;
    }
    unsigned bit=1<<adc_slot;
    if (regs[0x8b]->get()&bit)
      regs[0x86]->set(regs[0x86]->get()|0x10); // FIFO overwrite
    regs[0x90+2*adc_slot]->set(value>>8);
    regs[0x91+2*adc_slot]->set(value&255);
    regs[0x8b]->set(regs[0x8b]->get()|bit);
    ++adc_conversions;
    adc_slot=(adc_slot+1)&7;
    if (++adc_done==adc_length) {
      ++adc_sequences;
      regs[0x86]->set(regs[0x86]->get()|0x80);
      adc_flags();
      if (!(regs[0x83]->get()&4)) adc_slot=0;
      if (ctl5&0x20) adc_start(false);
      else adc_running=false;
    } else {
      adc_left=adc_period;
      adc_sample_left=(2+(2<<((regs[0x84]->get()>>5)&3)))*2*((regs[0x84]->get()&31)+1);
    }
    regs[0x86]->set((regs[0x86]->get()&0xf8)|adc_slot);
  }
}
unsigned xt_boot_hw::pending_vector(void) {
  unsigned selected=0, promoted=0xff00|regs[0x1f]->get();
  auto consider=[&](unsigned vector, bool pending) {
    if (pending && (vector==promoted || (selected!=promoted && vector>selected))) selected=vector;
  };
  consider(0xfff0, regs[0x38]->get()&regs[0x37]->get()&0x80);
  for (unsigned n=0;n<8;++n) consider(0xffee - 2*n, regs[0x4c]->get()&regs[0x4e]->get()&(1<<n));
  consider(0xffde, regs[0x4d]->get()&regs[0x4f]->get()&0x80);
  consider(0xffd8, ((regs[0xd8]->get()&0x80) && (regs[0xdb]->get()&0x80)) ||
                    ((regs[0xd8]->get()&0x20) && (regs[0xdb]->get()&0x20)));
  consider(0xffd2, (regs[0x82]->get()&2) && (regs[0x86]->get()&0x80));
  consider(0xffca, regs[0x66]->get()&regs[0x67]->get()&0x80);
  consider(0xffc6, regs[0x38]->get()&regs[0x37]->get()&0x10);
  return selected;
}


unsigned xt_boot_hw::timer_pins(unsigned pins) {
  unsigned connected=regs[0x42]->get()&regs[0x40]->get();
  for (unsigned n=0;n<8;++n) {
    unsigned mode=(regs[n<4?0x49:0x48]->get()>>(2*(n%4)))&3;
    if (mode && (regs[0x40]->get()&(1<<n))) connected|=1<<n;
  }
  return (pins&~connected)|(timer_output&connected);
}
void xt_boot_hw::timer_compare(unsigned n) {
  unsigned bit=1<<n, mode=(regs[n<4?0x49:0x48]->get()>>(2*(n%4)))&3;
  if (!(regs[0x42]->get()&bit)) {
    if (mode==1) timer_output^=bit;
    if (mode==2) timer_output&=~bit;
    if (mode==3) timer_output|=bit;
  }
  if (n==7) {
    unsigned mask=regs[0x42]->get()&regs[0x40]->get();
    timer_output=(timer_output&~mask)|(regs[0x43]->get()&mask);
  }
}
void xt_boot_hw::timer_tick(unsigned cycles) {
  unsigned pins=gpio(0xe0), changed=pins^last_pt;
  if (regs[0x46]->get()&0x80) {
    for (unsigned n=0;n<8;++n) {
      unsigned bit=1<<n, edge=(regs[n<4?0x4b:0x4a]->get()>>(2*(n%4)))&3;
      if (!(regs[0x40]->get()&bit) && (changed&bit) &&
          ((edge==3) || (edge==1 && (pins&bit)) || (edge==2 && !(pins&bit)))) {
        set_word(0x50+2*n,word(0x44));
        regs[0x4e]->set(regs[0x4e]->get()|bit); ++timer_edges;
        trace("capture",n,word(0x44));
      }
    }
    unsigned divisor=1u<<(regs[0x4d]->get()&7);
    timer_phase+=cycles;
    while (timer_phase>=divisor) {
      timer_phase-=divisor;
      unsigned counter=(word(0x44)+1)&65535;
      bool reset7=(regs[0x4d]->get()&8) && (regs[0x40]->get()&0x80);
      if (reset7 && word(0x5e)==0) counter=0;
      if (!counter && !(reset7 && word(0x5e)==0)) {
        regs[0x4f]->set(regs[0x4f]->get()|0x80);
        timer_output ^= regs[0x47]->get()&regs[0x40]->get();
      }
      for (unsigned n=0;n<8;++n) {
        if ((regs[0x40]->get()&(1<<n)) && counter==word(0x50+2*n)) {
          regs[0x4e]->set(regs[0x4e]->get()|(1<<n));
          timer_compare(n); ++timer_matches;
        }
      }
      if (reset7 && counter==word(0x5e)) counter=0;
      set_word(0x44,counter);
    }
  }
  last_pt=pins;
}
void xt_boot_hw::clock_tick(unsigned cycles) {
  // OSCCLK is independent of the PLL-derived bus clock. Keep the rational
  // relationship; no assumed oscillator MHz or invented wall-clock speed.
  unsigned numerator=1, denominator=2;
  if (regs[0x39]->get()&0x80) {
    numerator=(regs[0x34]->get()&0x3f)+1;
    denominator=(regs[0x35]->get()&0x0f)+1;
  }
  osc_phase+=cycles*denominator;
  unsigned clocks=osc_phase/numerator; osc_phase%=numerator;
  unsigned scale=(regs[0x3b]->get()>>4)&7;
  if (scale) {
    unsigned period=((regs[0x3b]->get()&15)+1)*(1u<<(9+scale));
    rti_phase+=clocks;
    while (rti_phase>=period) {
      rti_phase-=period; ++rti_events;
      regs[0x37]->set(regs[0x37]->get()|0x80);
    }
  }
  unsigned rate=regs[0x3c]->get()&7;
  if (rate) {
    static unsigned shifts[]={0,14,16,18,20,22,23,24};
    cop_elapsed+=clocks;
    if (cop_elapsed>=(1u<<shifts[rate])) unsupported(0x3f,"COP timeout reset request");
  }
}
void xt_boot_hw::spi_begin(unsigned value) {
  unsigned baud=regs[0xda]->get();
  spi_tx=value&255;
  spi_left=8*(((baud>>4)&7)+1)*(2u<<(baud&7));
  regs[0xdb]->set(regs[0xdb]->get()|0x20);
}
void xt_boot_hw::spi_tick(unsigned cycles) {
  while (spi_left && cycles) {
    unsigned elapsed=cycles<spi_left ? cycles : spi_left;
    spi_left-=elapsed; cycles-=elapsed;
    if (!spi_left) {
      unsigned value=cfg_get(18)==1 ? spi_tx : cfg_get(17);
      ++spi_count;
      if (!(regs[0xdb]->get()&0x80)) {
        regs[0xdd]->set(value);
        regs[0xdb]->set(regs[0xdb]->get()|0x80);
      } else ++spi_dropped; // Unread receive buffer retains its first byte.
      if (spi_queued) { spi_queued=false; spi_begin(spi_pending); }
    }
  }
}

class xt_sim: public cl_sim {
public:
  xt_sim(cl_app *app): cl_sim(app) {}
  cl_uc *mk_controller(void) { return new xt_cpu(this); }
};

// Application lifecycle follows uCsim's sm68hc12.cc (Daniel Drotos, GPL-2.0+).
int main(int argc, char **argv) {
  app_start_at=dnow(); cpus=cpus_m68hc12;
  application=new cl_app(); application->set_name("xt660_boot");
  application->init(argc, argv);
  cl_sim *sim=new xt_sim(application);
  if (sim->init()) sim->state|=SIM_QUIT;
  application->set_simulator(sim);
  int result=application->run();
  application->done(); delete application;
  return result;
}
