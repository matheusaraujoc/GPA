import math, subprocess, os, tempfile, json
BASE=r"c:\Users\Matheus\Documents\Projetos\GPA"; EXE=os.path.join(BASE,"main_test.exe"); USX=os.path.join(BASE,"unishox","usx.exe"); W=tempfile.mkdtemp()
PRIMER=open(os.path.join(BASE,"primer.bin"),"rb").read()
def squash(x):
    if x>20:return 0.999999
    if x<-20:return 1e-6
    return 1/(1+math.exp(-x))
def stretch(p): return math.log(p/(1-p))
MAXV=0xFFFFFFFF; HALF=0x80000000; Q1=0x40000000; Q3=0xC0000000
class Enc:
    def __init__(s): s.low=0;s.high=MAXV;s.pend=0;s.out=bytearray();s.bb=0;s.bc=0
    def _wb(s,b):
        s.bb=((s.bb<<1)|b)&0xFF;s.bc+=1
        if s.bc==8: s.out.append(s.bb);s.bb=0;s.bc=0
    def _em(s,b):
        s._wb(b)
        while s.pend>0: s._wb(b^1);s.pend-=1
    def enc(s,lc,hc,tot):
        r=s.high-s.low+1; s.high=s.low+(r*hc)//tot-1; s.low=s.low+(r*lc)//tot
        while True:
            if s.high<HALF: s._em(0)
            elif s.low>=HALF: s._em(1);s.low-=HALF;s.high-=HALF
            elif s.low>=Q1 and s.high<Q3: s.pend+=1;s.low-=Q1;s.high-=Q1
            else: break
            s.low=(s.low<<1)&MAXV; s.high=((s.high<<1)|1)&MAXV
    def fin(s):
        s.pend+=1
        s._em(0 if s.low<Q1 else 1)
        if s.bc>0: s.out.append((s.bb<<(8-s.bc))&0xFF)
        return bytes(s.out)
class Dec:
    def __init__(s,d): s.d=d;s.p=0;s.low=0;s.high=MAXV;s.v=0
    def _rb(s):
        bp=s.p>>3
        if bp>=len(s.d): s.p+=1; return 0
        b=(s.d[bp]>>(7-(s.p&7)))&1; s.p+=1; return b
    def init(s):
        for _ in range(32): s.v=((s.v<<1)|s._rb())&MAXV
    def tgt(s,tot):
        r=s.high-s.low+1; return ((s.v-s.low+1)*tot-1)//r
    def dec(s,lc,hc,tot):
        r=s.high-s.low+1; s.high=s.low+(r*hc)//tot-1; s.low=s.low+(r*lc)//tot
        while True:
            if s.high<HALF: pass
            elif s.low>=HALF: s.low-=HALF;s.high-=HALF;s.v-=HALF
            elif s.low>=Q1 and s.high<Q3: s.low-=Q1;s.high-=Q1;s.v-=Q1
            else: break
            s.low=(s.low<<1)&MAXV;s.high=((s.high<<1)|1)&MAXV;s.v=((s.v<<1)|s._rb())&MAXV
def p1(p): return min(max(int(p*4096+0.5),1),4095)
def eb(e,p,bit):
    c=4096-p1(p)
    if bit==0: e.enc(0,c,4096)
    else: e.enc(c,4096,4096)
def db(d,p):
    c=4096-p1(p); 
    if d.tgt(4096)<c: d.dec(0,c,4096); return 0
    d.dec(c,4096,4096); return 1
ORD=[(1,16),(2,18),(3,18),(4,18)]; MASKS=[(1<<b)-1 for _,b in ORD]
class M:
    def __init__(s):
        s.tabs=[[0.5]*(1<<b) for _,b in ORD]; s.o0=[0.5]*256
        s.NM=len(ORD)+2; s.w=[[0.3]*s.NM for _ in range(256)]; s.LR=0.01; s.R=1/30
        s.mm={}; s.mptr=-1; s.mlen=0; s.cont=0.96
    def ctx(s,data,pos):
        bh=[]
        for (o,_) in ORD:
            h=0
            for k in range(max(0,pos-o),pos): h=(h*0x9E3779B1+data[k]+1)&0xFFFFFFFF
            bh.append(h)
        pb=data[s.mptr] if (s.mlen>0 and 0<=s.mptr<pos) else None
        return bh,pb
    def pred(s,bh,pb,bp,c0):
        inp=[];ctx=[]
        for idx,((o,_),mask,h) in enumerate(zip(ORD,MASKS,bh)):
            ci=((h*257)^(c0*0x6789DBB5))&mask; ctx.append(ci); inp.append(stretch(min(max(s.tabs[idx][ci],1e-6),1-1e-6)))
        inp.append(stretch(min(max(s.o0[c0],1e-6),1-1e-6)))
        if pb is not None: pbit=(pb>>(7-bp))&1; st=min(s.mlen,32)*0.45; inp.append(st if pbit else -st)
        else: inp.append(0.0)
        sel=c0&255; z=sum(s.w[sel][i]*inp[i] for i in range(s.NM)); pm=min(max(squash(z),1e-6),1-1e-6)
        s._i=inp;s._c=ctx;s._s=sel;s._pm=pm;s._c0=c0; return pm
    def upd(s,bit):
        err=bit-s._pm
        for i in range(s.NM): s.w[s._s][i]+=s.LR*err*s._i[i]
        for idx,ci in enumerate(s._c): s.tabs[idx][ci]+=(bit-s.tabs[idx][ci])*s.R
        s.o0[s._c0]+=(bit-s.o0[s._c0])*s.R
    def after(s,data,pos,byte):
        pb=data[s.mptr] if (s.mlen>0 and 0<=s.mptr<pos) else None
        if pb is not None and pb==byte: s.mlen+=1;s.mptr+=1
        else: s.mlen=0;s.mptr=-1
        if pos>=3:
            h=0
            for k in range(pos-3,pos+1): h=(h*0x9E3779B1+data[k]+1)&0xFFFFFFFF
            if s.mlen==0:
                pv=s.mm.get(h,-1)
                if pv>=0: s.mptr=pv;s.mlen=1
            s.mm[h]=pos+1
    def upc(s,bit): s.cont+=(bit-s.cont)*0.05
def prime(m,data,plen):
    for pos in range(plen):
        bh,pb=m.ctx(data,pos); byte=data[pos]; c0=1
        for bp in range(8):
            bit=(byte>>(7-bp))&1; m.pred(bh,pb,bp,c0); m.upd(bit); c0=(c0<<1)|bit
        m.after(data,pos,byte)
def encode(msg,primer):
    data=bytearray(primer); data.extend(msg); plen=len(primer); m=M(); prime(m,data,plen); e=Enc()
    for pos in range(plen,len(data)):
        eb(e,m.cont,1); m.upc(1)
        bh,pb=m.ctx(data,pos); byte=data[pos]; c0=1
        for bp in range(8):
            bit=(byte>>(7-bp))&1; p=m.pred(bh,pb,bp,c0); eb(e,p,bit); m.upd(bit); c0=(c0<<1)|bit
        m.after(data,pos,byte)
    eb(e,m.cont,0); m.upc(0); return e.fin()
def decode(pay,primer):
    data=bytearray(primer); plen=len(primer); m=M(); prime(m,data,plen); d=Dec(pay); d.init()
    while True:
        if db(d,m.cont)==0: m.upc(0); break
        m.upc(1); pos=len(data); bh,pb=m.ctx(data,pos); c0=1; byte=0
        for bp in range(8):
            p=m.pred(bh,pb,bp,c0); bit=db(d,p); m.upd(bit); byte=(byte<<1)|bit; c0=(c0<<1)|bit
        data.append(byte); m.after(data,pos,byte)
    return bytes(data[plen:])
def gpa(Mz):
    i=os.path.join(W,"i");o=os.path.join(W,"o");open(i,"wb").write(Mz);subprocess.run([EXE,"cp",i,o],capture_output=True);return os.path.getsize(o)
def usx(Mz):
    i=os.path.join(W,"i");o=os.path.join(W,"o");open(i,"wb").write(Mz);subprocess.run([USX,"c",i,o],capture_output=True);return os.path.getsize(o)
tests={
 'Telemetria':b'{"device":"A23","ts":1700044556,"status":"OK","temp":27.1}',
 'JSON':b'{"name":"item","id":4521,"status":"active","price":19.99}',
 'URL':b'https://www.example.com/products/v2/88123',
 'Email':b'support.lima42@data.cloud',
 'Ingles':b'the government said people would have more time to work',
 'Frase PT':b'Bom dia, como vai voce hoje?',
 'texto 1KB':open(os.path.join(BASE,"spec.md"),"rb").read()[:1024],
}
print(f"{'caso':<12}{'orig':>5}{'CM-real':>8}{'rt':>4}{'GPA-prim':>9}{'Unishox':>8}")
for name,Mz in tests.items():
    c=encode(Mz,PRIMER); ok=decode(c,PRIMER)==Mz
    print(f"{name:<12}{len(Mz):>5}{len(c):>8}{'OK' if ok else 'X!':>4}{gpa(Mz):>9}{usx(Mz):>8}")
