// SPDX-License-Identifier: GPL-2.0-or-later
// XT660 peripheral harness for uCsim 0.9.12. This is NOT a full ECU.
// Device semantics: MC9S12T64 Rev 1.1.1, CRG, ECT, PIM and ATD chapters.
#include <cstdio>
#include <deque>
#include <algorithm>
#include <functional>
#include <stdexcept>
#include "globals.h"
#include "utils.h"
#include "m68hc12cl.h"
#include "simcl.h"
#include "newcmdcl.h"
#include "fiocl.h"

class xt_cpu;
class xt_boot_hw: public cl_hw {
public:
  // These are the same backing bytes used by uCsim's memory cells, not a
  // register cache. CPU reads/writes still go through all hardware hooks.
  struct register_byte {
    cl_memory_cell *cell=nullptr; unsigned char *value=nullptr;
    register_byte &operator=(cl_memory_cell *c) {
      if(c->get_width()!=8 || c->get_mask()!=255 || c->get_flag(CELL_READ_ONLY))
        throw std::runtime_error("Unexpected MCU register storage");
      cell=c;value=static_cast<unsigned char*>(c->get_data());return *this;
    }
    register_byte *operator->(){return this;}
    unsigned get() const{return *value;}
    void set(unsigned v){*value=v&255;}
  };
  xt_cpu *xt;
  cl_address_space *eeprom;
  bool ee_selected, ee_enabled;
  unsigned ee_command, ee_bytes, ee_data, ee_busy, ee_reads, ee_writes;
  void ee_select(bool selected);
  unsigned ee_transfer(unsigned value);
  register_byte regs[0x200];
  u32_t *config_values[42]{};
  t_mem cfg_get(t_addr n){return *config_values[n];}
  void cfg_set(t_addr n,t_mem v){*config_values[n]=v;}
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
  unsigned vss_left, vss_count;
  unsigned coil_feedback_left;
  unsigned observed_pa, observed_pp;
  bool vss_low;
  bool reference_ticks = false;
  std::function<void(const char *,unsigned,unsigned,unsigned long long,unsigned)> event_sink;
  struct serial_state {
    unsigned tx_left, tx_value, tx_pending, rx_left, idle_left, armed, sent, received, dropped;
    bool tx_queued, idle_eligible;
    std::deque<unsigned> rx;
  } sci[2];
  struct flash_state { unsigned status, protection, address, data, written, command, left, programs, erases; } flash[2];
  unsigned cfg_size(void) { return 42; }
  void flash_store(unsigned address, unsigned value);
  void flash_register(unsigned address, t_mem *value);
  void flash_tick(unsigned cycles);
  bool flash_protected(unsigned address);
  void flash_sync(void);

  void sci_tick(unsigned cycles);
  void sci_begin(unsigned channel, unsigned value);
  unsigned sci_period(unsigned channel);
  void sci_receive(unsigned channel, unsigned value);

  void advance(unsigned cycles);
  unsigned next_event(unsigned limit);
  void pulse_tick(void);
  void vss_tick(void);
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
#ifndef XT660_EMBEDDED
    cl_uc::mk_hw_elements();
#endif
    device= new xt_boot_hw(this);
    init_add_hw(device);
  }
  bool interrupts_masked(void) { return rCC & flagI; }
  int run_instruction() {
    // Continuous execution does not need the CLI's instruction history.
    // Keep pre/post hooks, fault and breakpoint processing, and IRQ delivery.
    if(device->reference_ticks) return do_inst();
    int result=resGO;
    if(state==stGO) {
      pre_inst(); instPC=PC; result=exec_inst();
      if(result==resINV_INST) PC=instPC;
    }
    post_inst();
    if((result==resGO || result==resNOT_DONE) && !device->fault) {
      int irq=do_interrupt(); if(irq!=resGO)result=irq;
    }
    return device->fault ? resHALT : result;
  }
  int tick_hw(int cycles) {
    if (device->reference_ticks || hws->count!=1) return cl_uc::tick_hw(cycles);
    // The ECU peripheral model advances to exact event boundaries internally.
    // All other uCsim devices retain their original one-cycle callbacks.
    device->tick(cycles);
    do_extra_hw(cycles);
    return 0;
  }
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
  for(unsigned n=0;n<42;++n) config_values[n]=static_cast<u32_t*>(cfg->get_cell(n)->get_data());
  eeprom=new cl_address_space("eeprom",0,512,8);
  eeprom->init(); uc->address_spaces->add(eeprom);
  cl_memory_chip *chip=new cl_chip8("eeprom_chip",512,8);
  chip->init(); uc->memchips->add(chip);
  cl_address_decoder *decoder=new cl_address_decoder(eeprom,chip,0,511,0);
  decoder->init(); eeprom->decoders->add(decoder); decoder->activate(0);
  for (unsigned a=0;a<512;++a) eeprom->set(a,255);
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
  for (unsigned a=0xb4; a<=0xc3; ++a) regs[a]->set(255); // PWM period/duty reset
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
  ee_selected=ee_enabled=false; ee_command=ee_bytes=ee_data=ee_busy=ee_reads=ee_writes=0;
  bus_cycles=0; pulse_left=pulse_count=trace_count=observed_outputs=0; pulse_low=false;
  vss_left=vss_count=0; vss_low=false;
  coil_feedback_left=0;
  observed_pa=observed_pp=0;
  regs[0xdb]->set(0x20); // SPTEF
  regs[0xd4]->set(0xc0); // SCI1 idle; no external serial traffic
  cfg_set(17,255); cfg_set(18,0); // Unconnected/pulled-high MISO, no EEPROM invented.
  // Explicit, deterministic raw input fixtures; no inferred temperature/RPM.
  for (unsigned n=1; n<=8; ++n) cfg_set(n,512);
  for (unsigned n=9; n<=16; ++n) cfg_set(n,0);
  cfg_set(19,51200); cfg_set(20,25600); cfg_set(21,11); cfg_set(22,2);
  cfg_set(23,132); cfg_set(24,0); cfg_set(25,0);
  regs[0xcc]->set(0xc0);
  for (unsigned n=0;n<2;++n) {
    sci[n]=serial_state();
    cfg_set(26+n,0); cfg_set(28+n,n ? 64:104);
    cfg_set(30+n,0); cfg_set(32+n,0);
  }
  cfg_set(34,0);
  for (unsigned n=35;n<42;++n) cfg_set(n,0);
  for (unsigned n=0;n<2;++n) {
    flash[n]=flash_state(); flash[n].status=0xc0;
    flash[n].protection=uc->rom->get(n ? 0xff0c:0xff0d);
  }
  regs[0x101]->set(uc->rom->get(0xff0f)); flash_sync();
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
  return a<=3 || a==8 || a==9 || a==0x12 || a==0xc4 || a==0x1e || a==0x1f || (a>=0x20 && a<=0x27)
    || (a>=0x82 && a<=0x86) || a==0x8b || a==0x8d || a==0x8f
    || (a>=0x90 && a<=0x9f) || (a>=0xac && a<=0xc3)
    || a==0xe0 || a==0xe1 || a==0xe2 || a==0xe8 || a==0xe9 || a==0xea
    || a==0xf0 || a==0xf1 || a==0xf2
    || (a>=0x32 && a<=0x35) || (a>=0x37 && a<=0x3c) || a==0x3f
    || (a>=0x40 && a<=0x5f) || a==0x66 || a==0x67 || a==0x76 || a==0x77
    || (a>=0xc8 && a<=0xd7) || (a>=0xd8 && a<=0xdb) || a==0xdd || a==0xee || a==0xf8 || (a>=0x100 && a<=0x106);
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
  if (a>=0x1800) {
    if (flash[a<0x8000?1:0].left) unsupported(a,"read from busy flash bank");
    return cell->get();
  }
  if (!supported(a)) { unsupported(a, "read"); return cell->get(); }
  if (a==0x32) return ((regs[0x32]->get()&regs[0x33]->get()) | (cfg_get(15)&~regs[0x33]->get()))&0x80;
  if (a==0x3f || a==0x41) return 0;
  if (a==0 || a==1 || a==8 || a==0xe0 || a==0xe1 || a==0xe8 || a==0xe9 || a==0xf0 || a==0xf1)
    return gpio(a);
  if ((a==0x44 || a==0x45) && (regs[0x46]->get()&0x10)) regs[0x4f]->set(0);
  if (a>=0x50 && a<=0x5f && (regs[0x46]->get()&0x10) && !(regs[0x40]->get()&(1<<((a-0x50)/2))))
    regs[0x4e]->set(regs[0x4e]->get()&~(1<<((a-0x50)/2)));
  if (a>=0xc8 && a<=0xd7) {
    unsigned n=(a-0xc8)/8, offset=(a-0xc8)%8, base=0xc8+8*n;
    if (offset==4) sci[n].armed |= cell->get();
    if (offset==7) {
      regs[base+4]->set(regs[base+4]->get()&~(sci[n].armed&0x3f));
      sci[n].armed &= 0xc0;
    }
  }
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
  if (a>=0x1800) {
    if (!cfg_get(34)) unsupported(a,"CPU flash write");
    else flash_store(a,*v);
    *v=cell->get(); return;
  }
  if (!supported(a)) { unsupported(a, "write"); *v=cell->get(); return; }
  unsigned old= cell->get();
  if (a>=0x100 && a<=0x106) { flash_register(a,v); return; }
  if (a==0xc4 && *v) { unsupported(a,"PWM channel enable"); *v=old; return; }
  // T64 PWM registers, datasheet pp.347-350: disabled counters do not run;
  // any counter write clears it, and period/duty writes latch immediately.
  // Enabled PWM remains explicitly unsupported, never silently simulated.
  if (a>=0xac && a<=0xb3) { *v=0; return; }
  if (a==0x12 && *v!=0x11 && *v!=1) { unsupported(a,"alternate CALRAM mapping"); *v=old; return; }
  if (a==0xf0 && cfg_get(18)==2) ee_select((*v&8)!=0);
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
  } else if (a>=0xc8 && a<=0xd7) {
    unsigned n=(a-0xc8)/8, offset=(a-0xc8)%8, base=0xc8+8*n;
    serial_state &ch=sci[n];
    if (offset==0) *v &= 0x1f;
    if (offset==2 && (*v&0x93)) { unsupported(a,"SCI parity/9-bit/loop framing"); *v=old; }
    if (offset==3) {
      if (*v&1) { unsupported(a,"SCI transmit break"); *v=old; }
      if ((*v&4) && !(old&4)) ch.idle_left=sci_period(n);
      if ((*v&2) && !(old&2)) ch.idle_left=sci_period(n);
    }
    if (offset==4 || offset==5 || offset==6) *v=old;
    if (offset==7) {
      if (regs[base+4]->get()&ch.armed&128) {
        if (!sci_period(n)) { unsupported(a,"SCI transmit with zero divisor"); *v=old; return; }
        ch.armed &= ~0xc0u;
        regs[base+4]->set(regs[base+4]->get()&~0xc0u);
        if (!ch.tx_left && (regs[base+3]->get()&8)) sci_begin(n,*v);
        else { ch.tx_pending=*v; ch.tx_queued=true; }
      }
      *v=old; // Receive register and transmit holding register share the address.
    }
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
  if (reference_ticks && (cfg_get(24) || cfg_get(25) || cfg_get(36) || cfg_get(41))) {
    for (int n=0;n<cycles && !fault;++n) {
      advance(1);
      pulse_tick();
      vss_tick();
      observe_outputs();
    }
  } else if (cfg_get(24) || cfg_get(25) || cfg_get(36) || cfg_get(41)) {
    while (cycles>0 && !fault) {
      unsigned span=next_event(cycles+1);
      if(span>unsigned(cycles)) {
        advance(cycles);
        if(cfg_get(24) && pulse_left) pulse_left-=cycles;
        if(cfg_get(36) && vss_left) vss_left-=cycles;
        if(coil_feedback_left) coil_feedback_left-=cycles;
        break;
      }
      // The last cycle retains the original advance -> crank -> VSS ->
      // output/coil-feedback order. Nothing observable happens in the prefix.
      if (span>1) {
        advance(span-1);
        if (cfg_get(24) && pulse_left) pulse_left-=span-1;
        if (cfg_get(36) && vss_left) vss_left-=span-1;
        if (coil_feedback_left) coil_feedback_left-=span-1;
      }
      advance(1); pulse_tick(); vss_tick(); observe_outputs();
      cycles-=span;
    }
  } else advance(cycles);
  return 0;
}
unsigned xt_boot_hw::next_event(unsigned limit) {
  auto due=[&](unsigned n) { if(n) limit=std::min(limit,n); };
  // GPIO writes can have changed an output before this instruction's clocks.
  if (gpio(0)!=observed_pa || gpio(0xf0)!=observed_pp || gpio(0xe0)!=observed_outputs) return 1;
  if(cfg_get(24)) due(pulse_left);
  if(cfg_get(36)) { if(!vss_left)return 1; due(vss_left); }
  due(coil_feedback_left); due(ee_busy); due(pll_delay);
  if(adc_running) { due(adc_left); due(adc_sample_left); }
  due(spi_left);
  for(unsigned n=0;n<2;++n) {
    due(flash[n].left); due(sci[n].tx_left); due(sci[n].rx_left); due(sci[n].idle_left);
    if((sci[n].tx_queued && !sci[n].tx_left) || (!sci[n].rx.empty() && !sci[n].rx_left)) return 1;
  }
  // Preserve every timer increment (and its capture/compare ordering).
  if(regs[0x46]->get()&0x80) due((1u<<(regs[0x4d]->get()&7))-timer_phase);
  if(counting && (regs[0x66]->get()&4)) due(prescaler-phase);
  return std::max(1u,limit);
}
void xt_boot_hw::advance(unsigned cycles) {
  bus_cycles+=cycles;
  ee_busy=cycles>=ee_busy ? 0 : ee_busy-cycles;
  adc_tick(cycles);
  timer_tick(cycles);
  spi_tick(cycles);
  sci_tick(cycles);
  flash_tick(cycles);
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
  if(event_sink) { event_sink(kind,channel,value,bus_cycles,unsigned(uc->instPC)); return; }
  if (!cfg_get(25)) return;
  if (++trace_count>20000) { unsupported(0xffff,"event trace limit"); return; }
  printf("XT_EVENT cycle=%llu kind=%s channel=%u value=%u pc=%04x\n",
         bus_cycles,kind,channel,value,unsigned(uc->instPC));
}
void xt_boot_hw::observe_outputs(void) {
  unsigned pa=gpio(0), pp=gpio(0xf0);
  if ((pa^observed_pa)&regs[2]->get()&4) trace("port_a",2,(pa>>2)&1);
  for (unsigned n=0;n<8;++n)
    if ((pp^observed_pp)&regs[0xf2]->get()&0x17&(1u<<n)) trace("port_p",n,(pp>>n)&1);
  observed_pa=pa; observed_pp=pp;
  unsigned pins=gpio(0xe0), changed=(pins^observed_outputs)&regs[0x40]->get();
  for (unsigned n=0;n<8;++n) if (changed&(1<<n)) trace("output",n,(pins>>n)&1);
  if (coil_feedback_left && !--coil_feedback_left) {
    cfg_set(12,cfg_get(12)|32u); timer_tick(0);
  }
  if (cfg_get(41) && (changed&8) && !(pins&8)) {
    // External ignition-driver acknowledgement pulse after coil release.
    // Feed the input pin, allowing the ECT to set its own capture flag.
    cfg_set(12,cfg_get(12)&~32u); coil_feedback_left=128;
    trace("input",5,0); timer_tick(0);
  }
  observed_outputs=pins;
}
void xt_boot_hw::pulse_tick(void) {
  if (!cfg_get(24) || !pulse_left || --pulse_left) return;
  pulse_low=!pulse_low;
  cfg_set(12,pulse_low ? cfg_get(12)&~2u : cfg_get(12)|2u);
  trace("input",1,pulse_low ? 0 : 1);
  timer_tick(0); // Capture the edge at this counter value, without an extra tick.
  if (pulse_low) { ++pulse_count; pulse_left=cfg_get(20); }
  else if (!cfg_get(37) && pulse_count>=cfg_get(23)) cfg_set(24,0);
  else {
    // Apply a live external tooth interval at a completed pulse, preserving
    // the gap index and phase. No MCU memory or output state is written.
    if (cfg_get(35)) {
      cfg_set(19,cfg_get(35)); cfg_set(20,cfg_get(35)/2);
      cfg_set(35,0);
    }
    unsigned interval=cfg_get(19);
    if (cfg_get(21) && ((pulse_count+1)%cfg_get(21)==0)) interval*=cfg_get(22);
    pulse_left=interval-cfg_get(20);
  }
}
void xt_boot_hw::vss_tick(void) {
  if (!cfg_get(36)) return;
  if (vss_left && --vss_left) return;
  vss_low=!vss_low;
  cfg_set(12,vss_low ? cfg_get(12)&~4u : cfg_get(12)|4u);
  if (vss_low) { ++vss_count; cfg_set(38,vss_count); }
  trace("input",2,vss_low ? 0 : 1);
  timer_tick(0);
  vss_left=cfg_get(36)/2;
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
  for (unsigned n=0;n<2;++n) con->dd_printf("FLASH%u_PROGRAMS=%u FLASH%u_ERASES=%u FLASH%u_STATUS=%02x\n",
    n,flash[n].programs,n,flash[n].erases,n,flash[n].status);
  for (unsigned n=0;n<2;++n) con->dd_printf("SCI%u_TX=%u SCI%u_RX=%u SCI%u_DROPPED=%u SCI%u_DIVISOR=%u\n",
    n,sci[n].sent,n,sci[n].received,n,sci[n].dropped,n,word(0xc8+n*8)&8191);
  con->dd_printf("EEPROM_READS=%u EEPROM_WRITES=%u EEPROM_BUSY=%u\n",ee_reads,ee_writes,ee_busy);
  con->dd_printf("BUS_CYCLES=%llu PULSES=%u PULSE_RUNNING=%u\n",bus_cycles,pulse_count,unsigned(cfg_get(24)));
  con->dd_printf("VSS_PULSES=%u VSS_INTERVAL=%u\n",vss_count,unsigned(cfg_get(36)));
}


const char *xt_boot_hw::cfg_help(t_addr a) {
  if (a>=1 && a<=8) return "Raw ADC channel 0..7: integer 0..1023";
  if (a==17) return "SPI external MISO byte (default 255: pulled-high disconnected bus)";
  if (a==18) return "SPI fixture: 0 external byte, 1 loopback, 2 observed external storage";
  if (a==19) return "PT1 fixture: ordinary falling-edge interval in bus cycles";
  if (a==20) return "PT1 fixture: low pulse width in bus cycles";
  if (a==21) return "PT1 fixture: every Nth interval is long; 0 means uniform";
  if (a==22) return "PT1 fixture: long-interval multiplier";
  if (a==23) return "PT1 fixture: number of falling edges";
  if (a==24) return "PT1 fixture: 1 starts, 0 stops; no firmware/RAM edits";
  if (a==25) return "Emit bounded input/capture/output/IRQ event trace";
  if (a==34) return "Enable simulated flash commands (source BIN never modified)";
  if (a==35) return "Pending PT1 interval: 0 or 12800..128000 bus cycles, applied between pulses";
  if (a==36) return "PT2 external speed input: 0 stops, otherwise 1000..16000000 bus cycles per pulse";
  if (a==37) return "Continuous external PT1 fixture; 0 retains finite pulse count";
  if (a==38) return "External PT2 falling-edge count (read-only)";
  if (a==39) return "External intake pressure ripple amplitude in ADC counts; 0 disables";
  if (a==40) return "External relay fixture: ADC4 supply follows PA2 command; 0 independent";
  if (a==41) return "External coil-driver acknowledgement on PT5 after PT3 release";
  if (a==26 || a==27) return "Queue an external 8N1 byte for SCI0 / SCI1 (0..255)";
  if (a==28 || a==29) return "External SCI0 / SCI1 peer baud divisor in bus-clock units";
  if (a==30 || a==31) return "Completed SCI0 / SCI1 transmit byte count (read-only)";
  if (a==32 || a==33) return "Last SCI0 / SCI1 transmitted byte (read-only)";
  if (a>=9) return "Driven GPIO input byte: PA, PB, PE, PT, PS, PP, PK7, PTAD";
  return "XT660 fixture configuration";
}
t_mem xt_boot_hw::conf_op(cl_memory_cell *cell, t_addr a, t_mem *v) {
  if (v && a) {
    if ((a>=30 && a<=33) || a==38) { *v=cell->get(); return cell->get(); }
    if (a>=35) {
      unsigned limit=a==35 ? 128000 : a==36 ? 16000000 : a==39 ? 255 : 1;
      unsigned minimum=a==35 ? 12800 : a==36 ? 1000 : 0;
      if (*v>limit || (*v && *v<minimum)) { *v=cell->get(); return cell->get(); }
      if (a==36 && !*v) {
        vss_left=0; vss_low=false;
        cfg_set(12,cfg_get(12)|4u); timer_tick(0);
      }
      if (a==36 && *v && !cell->get()) {
        vss_left=*v; vss_low=false;
        cfg_set(12,cfg_get(12)|4u); timer_tick(0);
      }
      if (a==41) { coil_feedback_left=0; cfg_set(12,cfg_get(12)|32u); timer_tick(0); }
      return cell->get();
    }
    unsigned max= a<=8 ? 1023 : (a==28 || a==29) ? 8191 : (a==26 || a==27) ? 255 : a==18 ? 2 : (a==24 || a==25 || a==34) ? 1 :
                  (a==19 || a==20) ? 1000000 : a==21 ? 64 : a==22 ? 8 : a==23 ? 4096 : 255;
    if (*v>max) {
      fprintf(stderr,"XT660 fixture input %u outside 0..%u; unchanged\n",unsigned(a),max);
      *v=cell->get();
    }
    if (a==26 || a==27) {
      serial_state &ch=sci[a-26];
      if (ch.rx.size()>=4096) { fprintf(stderr,"XT660 serial input queue full\n"); *v=cell->get(); }
      else ch.rx.push_back(*v&255);
    }
    if (a>=19 && a<=23 && cfg_get(24)) {
      fprintf(stderr,"XT660 stop the PT1 fixture before changing its timing\n"); *v=cell->get();
    }
    if (a==25 && *v && !cell->get()) { observed_outputs=gpio(0xe0); trace_count=0; }
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
  if (base==0xe8 && cfg_get(18)==2 && ee_selected) pins=(pins&~16u)|(ee_busy?0:16);
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
        if (channel==4 && cfg_get(40) && !(gpio(0)&4)) adc_sample=0;
        if (channel==1 && cfg_get(39) && cfg_get(24)) {
          // Deliberate external intake waveform: a triangular pressure dip
          // once per two crank revolutions. It is not a combustion model.
          unsigned phase=pulse_count%22;
          unsigned dip=cfg_get(39)*(phase<11 ? phase : 22-phase)/11;
          adc_sample=adc_sample>dip ? adc_sample-dip : 0;
        }
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
  for (unsigned n=0;n<2;++n) {
    unsigned base=0xc8+n*8, control=regs[base+3]->get(), status=regs[base+4]->get();
    consider(n?0xffd4:0xffd6, (control&status&0xc0) || ((control&0x20)&&(status&0x28)) || (control&status&0x10));
  }
  consider(0xffd2, (regs[0x82]->get()&2) && (regs[0x86]->get()&0x80));
  consider(0xffca, regs[0x66]->get()&regs[0x67]->get()&0x80);
  consider(0xffc6, regs[0x38]->get()&regs[0x37]->get()&0x10);
  return selected;
}


unsigned xt_boot_hw::timer_pins(unsigned pins) {
  // Collapse each nonzero two-bit OM/OL field into its channel bit.
  unsigned modes=regs[0x49]->get()|(regs[0x48]->get()<<8);
  modes=(modes|(modes>>1))&0x5555;
  modes=(modes|(modes>>1))&0x3333;
  modes=(modes|(modes>>2))&0x0f0f;
  modes=(modes|(modes>>4))&0xff;
  unsigned connected=(modes|regs[0x42]->get())&regs[0x40]->get();
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
    for (unsigned n=0;changed && n<8;++n) {
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
      unsigned value=cfg_get(18)==1 ? spi_tx : cfg_get(18)==2 ? ee_transfer(spi_tx) : cfg_get(17);
      ++spi_count;
      if (!(regs[0xdb]->get()&0x80)) {
        regs[0xdd]->set(value);
        regs[0xdb]->set(regs[0xdb]->get()|0x80);
      } else ++spi_dropped; // Unread receive buffer retains its first byte.
      if (spi_queued) { spi_queued=false; spi_begin(spi_pending); }
    }
  }
}

// Functional normal-mode flash command state. Timings are deterministic fixtures.
void xt_boot_hw::flash_sync(void) {
  flash_state &f=flash[regs[0x103]->get()&1];
  regs[0x104]->set(f.protection); regs[0x105]->set(f.status); regs[0x106]->set(f.command);
}
bool xt_boot_hw::flash_protected(unsigned address) {
  unsigned bank=address<0x8000?1:0, p=flash[bank].protection, relative=address&0x7fff;
  return !(p&128) || (!(p&32) && relative>=0x8000-(0x800u<<((p>>3)&3))) ||
    (!(p&4) && relative<(0x200u<<(p&3)));
}
void xt_boot_hw::flash_store(unsigned address, unsigned value) {
  unsigned bank=regs[0x103]->get()&1;
  flash_state &f=flash[bank];
  if (!(regs[0x100]->get()&128) || bank!=(address<0x8000?1:0) || !(f.status&128) || f.command ||
      (f.written && (f.written!=1 || address!=f.address+1)) || (!f.written && (address&1))) {
    f.status|=16; f.written=0; flash_sync(); return;
  }
  if (flash_protected(address)) { f.status|=32; flash_sync(); return; }
  if (!f.written) { f.address=address; f.data=value<<8; f.written=1; }
  else { f.data|=value; f.written=2; }
}
void xt_boot_hw::flash_register(unsigned a, t_mem *v) {
  unsigned bank=regs[0x103]->get()&1;
  flash_state &f=flash[bank];
  if (a==0x100) {
    if (regs[a]->get()&128) *v=regs[a]->get();
    else *v=(*v&0x7f)|128;
    return;
  }
  if (a==0x101 || a==0x102) { *v=regs[a]->get(); return; }
  if (f.written && a!=0x106 && !(a==0x105 && f.command)) {
    f.status|=16; f.written=0;
  }
  if (a==0x103) {
    if (*v&0xe0) { unsupported(a,"flash IRQ/key-access mode"); *v=regs[a]->get(); return; }
    *v &= 1; regs[a]->set(*v); flash_sync(); return;
  }
  if (a==0x104) {
    unsigned p=f.protection, value=*v;
    if (!(p&32)) value=(value&~0x18u)|(p&0x18);
    if (!(p&4)) value=(value&~3u)|(p&3);
    f.protection=(value&~0xe4u)|(p&value&0xa4)|(p&64);
  }
  if (a==0x106) {
    if (f.command || f.written!=2 || (*v!=0x20 && *v!=0x40)) { f.status|=16; f.written=0; }
    else f.command=*v;
  }
  if (a==0x105) {
    f.status &= ~(*v&0x30);
    if (*v&0x30) { f.written=0; f.command=0; }
    if (*v&128) {
      if ((flash[0].status|flash[1].status)&0x30) { /* locked by an error */ }
      else if (f.written!=2 || !f.command || f.left) { f.status|=16; f.written=0; f.command=0; }
      else { f.status&=~0xc0u; f.left=f.command==0x40 ? 1024:40; }
    }
    if (!*v) { f.status|=16; f.written=0; f.command=0; }
  }
  flash_sync(); *v=regs[a]->get();
}
void xt_boot_hw::flash_tick(unsigned cycles) {
  for (unsigned bank=0;bank<2;++bank) {
    flash_state &f=flash[bank];
    if (!f.left) continue;
    if (cycles<f.left) { f.left-=cycles; continue; }
    f.left=0;
    if (f.command==0x40) {
      unsigned first=f.address&~511u;
      for (unsigned a=first;a<first+512;++a) uc->rom->set(a,255);
      ++f.erases; trace("flash_erase",bank,first);
    } else {
      unsigned old=uc->rom->get(f.address)*256+uc->rom->get(f.address+1);
      // Programming can only clear bits; firmware readback detects an unerased word.
      uc->rom->set(f.address,(old&f.data)>>8); uc->rom->set(f.address+1,(old&f.data)&255);
      ++f.programs;
    }
    f.status|=0xc0; f.written=0; f.command=0;
  }
  flash_sync();
}

// SCI functional 8N1 shift/data registers, baud timing and external byte source.
unsigned xt_boot_hw::sci_period(unsigned n) { return (word(0xc8+8*n)&8191)*160; }
void xt_boot_hw::sci_begin(unsigned n, unsigned value) {
  sci[n].tx_value=value&255; sci[n].tx_left=sci_period(n);
  regs[0xcc+8*n]->set((regs[0xcc+8*n]->get()|128)&~64u);
}
void xt_boot_hw::sci_receive(unsigned n, unsigned value) {
  serial_state &ch=sci[n]; unsigned base=0xc8+n*8;
  if (!(regs[base+3]->get()&4) || (regs[base+3]->get()&2)) { ++ch.dropped; return; }
  if (regs[base+4]->get()&0x22) { // An unread byte is retained; framing error blocks further reception.
    if (regs[base+4]->get()&0x20) regs[base+4]->set(regs[base+4]->get()|8);
    ++ch.dropped; return;
  }
  unsigned error=(cfg_get(28+n)!=(word(base)&8191)) ? 2:0;
  regs[base+7]->set(value); regs[base+4]->set(regs[base+4]->get()|0x20|error);
  ++ch.received; ch.idle_eligible=true;
  trace("serial_rx",n,value);
}
void xt_boot_hw::sci_tick(unsigned cycles) {
  for (unsigned n=0;n<2;++n) {
    serial_state &ch=sci[n]; unsigned base=0xc8+n*8, left=cycles;
    while(left) {
      if (!ch.tx_left && ch.tx_queued && (regs[base+3]->get()&8)) { ch.tx_queued=false; sci_begin(n,ch.tx_pending); }
      if (!ch.rx_left && !ch.rx.empty()) {
        ch.rx_left=cfg_get(28+n)*160;
        if (!ch.rx_left) { unsupported(base,"zero external serial divisor"); return; }
      }
      bool receiving=ch.rx_left!=0;
      unsigned span=left;
      if(ch.tx_left)span=std::min(span,ch.tx_left);
      if(ch.rx_left)span=std::min(span,ch.rx_left);
      else if(ch.idle_left)span=std::min(span,ch.idle_left);
      left-=span;
      if(ch.tx_left) {
        ch.tx_left-=span;
        if(!ch.tx_left) {
          ++ch.sent; cfg_set(30+n,ch.sent); cfg_set(32+n,ch.tx_value);
          trace("serial_tx",n,ch.tx_value);
          if(ch.tx_queued && (regs[base+3]->get()&8)) { ch.tx_queued=false; sci_begin(n,ch.tx_pending); }
          else regs[base+4]->set(regs[base+4]->get()|0xc0);
        }
      }
      if(receiving) {
        ch.rx_left-=span;
        if(!ch.rx_left) {
          unsigned byte=ch.rx.front(); ch.rx.pop_front(); sci_receive(n,byte);
          ch.idle_left=sci_period(n);
        }
      } else if(ch.idle_left) {
        ch.idle_left-=span;
        if(!ch.idle_left && (regs[base+3]->get()&4)) {
          if((regs[base+3]->get()&2) && !(regs[base+2]->get()&8)) regs[base+3]->set(regs[base+3]->get()&~2u);
          else if(ch.idle_eligible) { regs[base+4]->set(regs[base+4]->get()|16); ch.idle_eligible=false; }
        }
      }
    }
  }
}

// Byte command protocol observed in the firmware's SPI + PP3 storage routines.
// This models that interface, not a claimed physical chip identification.
void xt_boot_hw::ee_select(bool selected) {
  if (selected==ee_selected) return;
  if (!selected && ee_bytes>=3 && (ee_command&0xfe00)==0x0a00 && ee_enabled) {
    if (ee_busy) { unsupported(0xdd,"storage write while busy"); return; }
    eeprom->set(ee_command&511,ee_data); ++ee_writes;
    ee_busy=1024; // deterministic fixture latency, not measured write time
    trace("storage_write",ee_command&511,ee_data);
  }
  ee_selected=selected;
  if (selected) { ee_command=ee_bytes=ee_data=0; }
}
unsigned xt_boot_hw::ee_transfer(unsigned value) {
  if (!ee_selected || ee_busy) return 255;
  ++ee_bytes;
  if (ee_bytes<=2) {
    ee_command=((ee_command<<8)|value)&65535;
    if (ee_bytes==2) {
      if (ee_command==0x0980) ee_enabled=true;
      else if (ee_command==0x0800) ee_enabled=false;
      else if ((ee_command&0xfe00)!=0x0c00 && (ee_command&0xfe00)!=0x0a00)
        unsupported(0xdd,"unsupported storage command");
    }
    return 255;
  }
  if ((ee_command&0xfe00)==0x0c00) {
    unsigned address=(ee_command+ee_bytes-3)&511;
    ++ee_reads; return eeprom->get(address);
  }
  ee_data=value;
  return 255;
}

class xt_sim: public cl_sim {
public:
  xt_sim(cl_app *app): cl_sim(app) {}
  cl_uc *mk_controller(void) { return new xt_cpu(this); }
};

class xt_app: public cl_app {
public:
  int run_nogo(void) {
    // The stock interactive console polls idle input every 100 ms. Our local
    // request/reply bridge needs 1 ms responsiveness. This changes host sleep
    // only: paused MCU time and all simulated instruction clocks are unchanged.
    commander->check();
    int done=commander->input_avail() ? commander->proc_input() : (msleep(1),0);
    if (sim->uc) sim->uc->touch();
    return done;
  }
};

// Application lifecycle follows uCsim's sm68hc12.cc (Daniel Drotos, GPL-2.0+).
#ifndef XT660_EMBEDDED
int main(int argc, char **argv) {
  app_start_at=dnow(); cpus=cpus_m68hc12;
  application=new xt_app(); application->set_name("xt660_boot");
  application->init(argc, argv);
  cl_sim *sim=new xt_sim(application);
  if (sim->init()) sim->state|=SIM_QUIT;
  application->set_simulator(sim);
  int result=application->run();
  application->done(); delete application;
  return result;
}
#endif
