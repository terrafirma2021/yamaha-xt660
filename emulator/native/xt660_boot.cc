// SPDX-License-Identifier: GPL-2.0-or-later
// XT660 startup harness for uCsim 0.9.12. This is deliberately NOT a full ECU.
// Device semantics: MC9S12T64 Rev 1.1.1, CRG and ECT chapters.
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
  const char *id_string(void) { return "XT660 startup model (partial MC9S12T64)"; }
  void make_cpu_hw(void) { cl_uc::make_cpu_hw(); }
  void mk_hw_elements(void) {
    // Exclude generic HC12 page registers and inherited 6800 CIA/PIA devices:
    // those addresses overlap T64 clock registers and the ECU's program flash.
    cl_uc::mk_hw_elements();
    device= new xt_boot_hw(this);
    init_add_hw(device);
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
  return 0;
}
void xt_boot_hw::reset(void) {
  for (unsigned a=0; a<0x200; ++a) regs[a]->set(0);
  regs[0x37]->set(0x40); // CRGFLG.PORLVDRF
  regs[0x3a]->set(0xf1); // PLLCTL reset value
  regs[0x76]->set(0xff); regs[0x77]->set(0xff);
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
  // Storage-only GPIO/configuration writes used before the application entry.
  // They do not claim a transceiver, sensor or actuator simulation.
  return a==0 || a==2 || a==0x1e || (a>=0x20 && a<=0x27)
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
  if (!xt->executing) return cell->get(); // debugger reads have no side effects
  if (a>=0x1800) return cell->get();
  if (!supported(a)) { unsupported(a, "read"); return cell->get(); }
  if (a==0x76 || a==0x77) {
    unsigned value= (regs[0x66]->get()&0x20) ? load : count;
    if (regs[0x46]->get()&0x10) regs[0x67]->set(regs[0x67]->get()&~0x80);
    return a==0x76 ? value>>8 : value&0xff;
  }
  return cell->get();
}
void xt_boot_hw::write(cl_memory_cell *cell, t_mem *v) {
  unsigned a= address(cell);
  if (!xt->executing) return; // fixture/debugger memory setup, never an ECU write
  if (a>=0x1800) { unsupported(a, "CPU flash write"); *v=cell->get(); return; }
  if (!supported(a)) { unsupported(a, "write"); *v=cell->get(); return; }
  unsigned old= cell->get();
  if (a==0x37) { // LOCK/TRACK read-only; interrupt flags write-one-to-clear
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
  con->dd_printf("XT660 startup only; runtime peripherals and interrupts incomplete\n");
  con->dd_printf("PLL_LOCK=%u MCCNT=%u MC_LOAD=%u MCZF=%u FAULT=%u\n",
    (regs[0x37]->get()>>3)&1, count, load, (regs[0x67]->get()>>7)&1, fault);
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
