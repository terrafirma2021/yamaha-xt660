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
  unsigned cfg_size(void) { return 17; }
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
  // Explicit, deterministic raw input fixtures; no inferred temperature/RPM.
  for (unsigned n=1; n<=8; ++n) cfg_set(n,512);
  for (unsigned n=9; n<=16; ++n) cfg_set(n,0);
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
    || a==0x34 || a==0x35 || a==0x37 || a==0x39 || a==0x3a || a==0x3c
    || a==0x46 || a==0x4d || a==0x66 || a==0x67 || a==0x76 || a==0x77
    || (a>=0xc8 && a<=0xcb) || a==0xee || a==0xf8 || a==0x100;
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
  if (a==0 || a==1 || a==8 || a==0xe0 || a==0xe1 || a==0xe8 || a==0xe9 || a==0xf0 || a==0xf1)
    return gpio(a);
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
  if (a>=0x82 && a<=0x84) {
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
  adc_tick(cycles);
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
  return 0;
}
void xt_boot_hw::print_info(cl_console_base *con) {
  con->dd_printf("XT660 partial peripherals; not a full engine model\n");
  con->dd_printf("PLL_LOCK=%u MCCNT=%u MC_LOAD=%u MCZF=%u FAULT=%u\n",
    (regs[0x37]->get()>>3)&1, count, load, (regs[0x67]->get()>>7)&1, fault);
  con->dd_printf("ADC_BUSY=%u ADC_SLOT=%u ADC_CONVERSIONS=%u ADC_SEQUENCES=%u SCF=%u CCF=%02x IRQ_COUNT=%u IRQ_VECTOR=%04x\n",
    adc_running, adc_slot, adc_conversions, adc_sequences, (regs[0x86]->get()>>7)&1,
    unsigned(regs[0x8b]->get()), irq_count, irq_vector);
}


const char *xt_boot_hw::cfg_help(t_addr a) {
  if (a>=1 && a<=8) return "Raw ADC channel 0..7: integer 0..1023";
  if (a>=9) return "Driven GPIO input byte: PA, PB, PE, PT, PS, PP, reserved, PTAD";
  return "XT660 fixture configuration";
}
t_mem xt_boot_hw::conf_op(cl_memory_cell *cell, t_addr a, t_mem *v) {
  if (v && a) {
    unsigned max= a<=8 ? 1023 : 255;
    if (*v>max) {
      fprintf(stderr,"XT660 fixture input %u outside 0..%u; unchanged\n",unsigned(a),max);
      *v=cell->get();
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
  bool atd=(regs[0x82]->get()&2) && (regs[0x86]->get()&0x80);
  bool modulus=(regs[0x66]->get()&0x80) && (regs[0x67]->get()&0x80);
  // HPRIO may promote a pending source; otherwise the higher vector wins.
  unsigned highest=regs[0x1f]->get();
  if (highest==0xca && modulus) return 0xffca;
  if (atd) return 0xffd2;
  return modulus ? 0xffca : 0;
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
