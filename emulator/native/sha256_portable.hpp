// SPDX-License-Identifier: GPL-2.0-or-later
// SHA-256 for browser builds, following FIPS 180-4. Used for integrity, not secrets.
#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <vector>
inline std::string sha256_portable(const std::vector<unsigned char>& input) {
  constexpr uint32_t k[]={
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
  std::array<uint32_t,8> h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  auto bytes=input;uint64_t bits=uint64_t(bytes.size())*8;bytes.push_back(128);
  while(bytes.size()%64!=56)bytes.push_back(0);
  for(int n=56;n>=0;n-=8)bytes.push_back(static_cast<unsigned char>(bits>>n));
  auto r=[](uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));};
  for(size_t offset=0;offset<bytes.size();offset+=64) {
    uint32_t w[64];for(unsigned n=0;n<16;++n){w[n]=0;for(unsigned j=0;j<4;++j)w[n]=(w[n]<<8)|bytes[offset+n*4+j];}
    for(unsigned n=16;n<64;++n){auto a=w[n-15],b=w[n-2];w[n]=w[n-16]+(r(a,7)^r(a,18)^(a>>3))+w[n-7]+(r(b,17)^r(b,19)^(b>>10));}
    auto v=h;
    for(unsigned n=0;n<64;++n) {
      uint32_t t1=v[7]+(r(v[4],6)^r(v[4],11)^r(v[4],25))+((v[4]&v[5])^(~v[4]&v[6]))+k[n]+w[n];
      uint32_t t2=(r(v[0],2)^r(v[0],13)^r(v[0],22))+((v[0]&v[1])^(v[0]&v[2])^(v[1]&v[2]));
      for(unsigned j=7;j>0;--j)v[j]=v[j-1];v[4]+=t1;v[0]=t1+t2;
    }
    for(unsigned n=0;n<8;++n)h[n]+=v[n];
  }
  std::string out;const char* hex="0123456789abcdef";
  for(auto v:h)for(int n=28;n>=0;n-=4)out+=hex[(v>>n)&15];return out;
}
