// SPDX-License-Identifier: GPL-2.0-or-later
// Stock R/X gearing from 5VK1-AE1; tyre rollouts supplied in Gearing Commander
// screenshots on 2026-11-05. The 20-edge sensor is a simulation assumption.
#pragma once
#include <array>
#include <cmath>
#include <cstdint>

struct Transmission {
  static constexpr double pi=3.14159265358979323846,clock_hz=16000000;
  static constexpr double primary=75.0/36,final_drive=45.0/15;
  static constexpr double pulses_per_shaft_turn=20; // Not measured hardware.
  static constexpr std::array<double,6> gears={0,30.0/12,26.0/16,23.0/20,20.0/22,20.0/26};
  bool trail=false;
  double circumference_mm()const{return trail?2010.0:1959.7;}
  double wheel_radius()const{return circumference_mm()/1000/(2*pi);}
  static double ratio(int gear){return primary*gears.at(gear)*final_drive;}
  double kmh(double rpm,int gear)const{return gear?rpm/ratio(gear)*circumference_mm()*60/1000000:0;}
  static double shaft_pulses_hz(double rpm,int gear){return gear?rpm/(primary*gears.at(gear))*pulses_per_shaft_turn/60:0;}
  static double wheel_pulses_hz(double wheel_omega){return wheel_omega/(2*pi)*final_drive*pulses_per_shaft_turn;}
  double pulse_speed_kmh(unsigned pulses,uint64_t cycles)const {
    return cycles?pulses*circumference_mm()*.0036*clock_hz/(pulses_per_shaft_turn*final_drive*cycles):0;
  }
};
