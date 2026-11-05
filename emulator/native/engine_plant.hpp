// SPDX-License-Identifier: GPL-2.0-or-later
// External single-cylinder plant. No ECU memory, limiter values or target RPM.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>

struct EnginePlant {
  static constexpr double pi=3.14159265358979323846,clock_hz=16000000;
  // Fixture assumptions, NOT measured XT660 parameters. See emulator/README.md.
  static constexpr double crank_inertia=.10,loaded_mass=260,wheel_radius=.3119;
  static constexpr double first_ratio=(75.0/36)*(30.0/12)*(45.0/15);
  double omega=0,angle=0,burn_angle=pi,burn_work=0;
  double travel=0,load=0;
  bool starter=false,run=true,coil_high=false,injector_low=false;
  uint64_t last_cycle=0,coil_on=0,last_spark=0,injector_on=0,last_fuel=0,fuel_number=0,consumed_fuel=0;
  uint64_t firings=0,sparks=0,injections=0,missed=0;
  int64_t last_power_cycle=-1;
  double last_injection_ms=0;
  double rpm()const{return omega*60/(2*pi);}
  double inertia()const{return crank_inertia+load*loaded_mass*std::pow(wheel_radius/first_ratio,2);}
  static double drag(double rpm){return 4+.002*rpm;}
  static double envelope(double rpm) {
    // Yamaha's 2004 R/X peak torque and peak power bound a nominal envelope;
    // the plateau / constant-power continuation is not a measured torque curve.
    return std::min(58.4,35300/std::max(1.0,rpm*2*pi/60));
  }
  void advance(uint64_t cycle) {
    if(!last_cycle){last_cycle=cycle;return;}
    double remaining=double(cycle-last_cycle)/clock_hz;last_cycle=cycle;
    while(remaining>0) {
      double dt=std::min(remaining,.00025);remaining-=dt;
      double speed=rpm(),dtheta=omega*dt;
      // Distribute one combustion's work over 180 crank degrees. The integral
      // is burn_work; there is one eligible power stroke per 720 degrees.
      double end=std::min(pi,burn_angle+dtheta);
      double work=burn_work*.5*(std::cos(burn_angle)-std::cos(end));burn_angle=end;
      double road_speed=omega*wheel_radius/first_ratio;
      double road_torque=load*(.015*loaded_mass*9.80665+.5*1.225*.65*road_speed*road_speed)*wheel_radius/first_ratio;
      double starter_torque=starter?24*std::max(0.0,1-speed/900):0;
      double torque=starter_torque-drag(speed)-road_torque;
      // Energy integration preserves combustion work; torque integration lets
      // the starter accelerate from rest without a fabricated initial speed.
      double coasting=std::max(0.0,omega+torque/inertia()*dt);
      double next=std::sqrt(coasting*coasting+2*work/inertia());
      angle+=(omega+next)*.5*dt;omega=next;
    }
  }
  void output(unsigned channel,unsigned value,uint64_t cycle,int64_t revolution) {
    advance(cycle);
    if(channel==6) {
      // Normal primary injection: C5C8..C60B (early) programs clear-low,
      // then set-high after B72 timer ticks. Idle-high is NOT fuel delivery.
      if(!value){injector_low=true;injector_on=cycle;}
      else if(injector_low){injector_low=false;last_fuel=cycle;++fuel_number;++injections;last_injection_ms=(cycle-injector_on)*1000.0/clock_hz;}
    }
    if(channel!=3)return;
    if(value){coil_high=true;coil_on=cycle;return;}
    if(!coil_high)return;coil_high=false;last_spark=cycle;++sparks;
    auto power_cycle=revolution/2;
    // The pressure fixture reaches its intake minimum after the first turn;
    // compression/firing belongs to the second. Later BINs use this pressure
    // cycle identification to stop wasting sparks. Physical TDC is unknown.
    // Use the emitted CPS pattern's turn count, not rounded-period integration
    // or spark counts: neither timer quantization nor cuts can shift phase.
    if(!(revolution&1)||power_cycle==last_power_cycle)return;
    last_power_cycle=power_cycle;
    double fuel_age=double(cycle-last_fuel)/clock_hz;
    bool fuel=fuel_number!=consumed_fuel&&last_fuel&&fuel_age<120/std::max(100.0,rpm());
    consumed_fuel=fuel_number;
    if(!run||!fuel){++missed;return;}
    // Presence of a completed injector pulse gates combustion. Injector flow,
    // AFR and absolute spark phase are not calibrated, so this is not a dyno.
    double air=std::clamp(travel/100+(1-travel/100)*150/std::max(600.0,rpm()),0.0,1.0);
    burn_work=4*pi*(envelope(rpm())+drag(rpm()))*air;burn_angle=0;++firings;
  }
};
